"""Hard search from a trained circuit, scoring mutants on a mix of clean and perturbed streams.

A copy of the hard-search loops in spad/training/train_stream.py (no gradient phase), with one
change: every search batch is replayed as usual, then a `--share` of its rays get a random
sensor perturbation (constraints_lab/sensor/perturb.py: pile-up k uniform in 1..--max-k, then
Gaussian jitter sigma uniform in [0, --max-sigma]). The loss is the trainer's Huber loss after ONE
constant offset per mutant over the whole mixed batch, so an offset that moves with the sensor
effect is penalized, not hidden. --share 0 is the clean control.

--objective accuracy: the trainer's accuracy search (table and wire edits, loss + area weight x
estimated whole-core area, accept a mutant only if it lowers the score).
--objective area: the trainer's area search (table / wire / prune, smallest synthesized area whose
loss stays within --accuracy-tolerance of the start). With --clean-limit the clean rays of the same
batch must ALSO stay within tolerance on their own (a hard limit on clean accuracy, free: same
simulation). Selection uses validation photons with the same mixture, fixed.

Never loads test splits. Example (from SPAD/):
../.venv/bin/python -m constraints_lab.slot -- ../.venv/bin/python -m constraints_lab.sensor.search \
  --out runs/2026-11-11_constraints-lab/sensor/acc-mix-s0 --objective accuracy --share .5 --threads 1
"""
import argparse
import json
from pathlib import Path
import time

import torch

from spad import ROOT
from spad.dataset.photons import load_rays, sample_conditions
from spad.hardware.area_model import MODEL_PATH, AreaModel
from spad.training.baselines import metrics
from spad.core.stream_model import (StreamConfig, input_names, pack_circuit, simulate_population_packed,
                                    unpack_circuit)
from spad.training.train_stream import mutate
from constraints_lab.sensor.perturb import randomized

FINAL = ROOT/"runs/2026-11-10_kaggle-t4_batch3_fused-larger-search/random-s4-seed0/circuit.json"


def huber_after_offset(prediction, targets, keep=None):
    error = prediction - targets[None]
    if keep is not None:
        error = error[:, keep]
    error = error - error.median(-1, keepdim=True).values
    return torch.nn.functional.huber_loss(error, torch.zeros_like(error), delta=4., reduction="none").mean(-1)


class MixValidator:
    """Fixed validation photons with the training mixture; offset fitted on mixed train photons."""
    def __init__(self, train, validation, conditions, sets, share, max_k, max_sigma, seed=7):
        generator = torch.Generator().manual_seed(seed)
        pick = torch.randperm(len(train[1]), generator=generator)[:8000]
        self.fit_targets = train[1][pick]
        photons, _, background = sample_conditions(train[0][pick], *conditions, generator)
        self.clean_fit_photons = photons
        self.fit_photons = randomized(photons, train[0][pick], background, generator, share, max_k, max_sigma)
        draws = [sample_conditions(validation[0], *conditions, generator) for _ in range(sets)]
        photons, _, background = (torch.cat(x) for x in zip(*draws))
        self.clean_photons = photons
        self.photons = randomized(photons, validation[0].repeat(sets, 1), background, generator, share, max_k, max_sigma)
        self.targets = validation[1].repeat(sets)

    def __call__(self, config, circuit, clean=False):
        """Validation MAE on the mixture; with clean=True also on the same photons unperturbed."""
        inputs, codes = pack_circuit(circuit)
        run = lambda p: simulate_population_packed(config, inputs[None], codes[None], p)[0].float()
        offset = float((run(self.fit_photons) - self.fit_targets).median())
        mix = metrics(run(self.photons) - offset, self.targets)["mae_m"]
        if not clean:
            return mix
        offset = float((run(self.clean_fit_photons) - self.fit_targets).median())
        return mix, metrics(run(self.clean_photons) - offset, self.targets)["mae_m"]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data", type=Path, default=ROOT/"data")
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--init-circuit", type=Path, default=FINAL)
    parser.add_argument("--objective", choices=("accuracy", "area"), default="accuracy")
    parser.add_argument("--share", type=float, default=.5, help="fraction of rays perturbed (0 = clean control)")
    parser.add_argument("--max-k", type=int, default=4)
    parser.add_argument("--max-sigma", type=float, default=2.)
    parser.add_argument("--clean-limit", action="store_true", help="area: clean rays must also stay within tolerance")
    parser.add_argument("--accuracy-tolerance", type=float, default=.05)
    parser.add_argument("--search-area-weight", type=float, default=.05)
    parser.add_argument("--synth-candidates", type=int, default=3)
    parser.add_argument("--generations", type=int, default=300)
    parser.add_argument("--population", type=int, default=192)
    parser.add_argument("--search-rays", type=int, default=4096)
    parser.add_argument("--validate-every", type=int, default=20)
    parser.add_argument("--photon-sets", type=int, default=3)
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--threads", type=int, default=1)
    args = parser.parse_args()
    torch.set_num_threads(args.threads)
    torch.manual_seed(args.seed)
    args.out.mkdir(parents=True, exist_ok=True)
    started = time.monotonic()
    train = load_rays(args.data, "train", clean_only=True)[:2]
    routing = load_rays(args.data, "architecture", clean_only=True)[:2]
    validation = load_rays(args.data, "validation")[:2]
    conditions = (16, 256, .6)
    template = json.loads(args.init_circuit.read_text())
    config = StreamConfig(**template["config"])
    area_model = AreaModel(MODEL_PATH, "cpu")
    validator = MixValidator(train, validation, conditions, args.photon_sets, args.share, args.max_k, args.max_sigma)
    generator = torch.Generator().manual_seed(args.seed)
    base_bits = len(input_names(config))
    synthesized = {}

    def real_area(circuits):
        from spad.hardware.synth import synthesize
        from spad.hardware.verilog import stream_verilog
        out = []
        for c in circuits:
            key = json.dumps(c["layers"], separators=(",", ":"))
            if key not in synthesized:
                synthesized[key] = synthesize(stream_verilog(c), "photon_core", args.data)["area"] or 0.
            out.append(synthesized[key])
        return out

    def batch(split):
        pick = torch.randint(len(split[1]), (args.search_rays,), generator=generator)
        photons, _, background = sample_conditions(split[0][pick], *conditions, generator)
        chosen = torch.rand(len(pick), generator=generator) < args.share
        k = torch.where(chosen, torch.randint(1, args.max_k + 1, (len(pick),), generator=generator), 1)
        sigma = torch.where(chosen, torch.rand(len(pick), generator=generator) * args.max_sigma, 0.)
        from constraints_lab.sensor.perturb import jitter, pile_up
        photons = jitter(pile_up(photons, split[0][pick], background, k, generator), sigma, generator)
        return photons, split[1][pick], ~chosen

    def losses(inputs, codes, data):
        photons, targets, clean = data
        prediction = simulate_population_packed(config, inputs, codes, photons).float()
        return huber_after_offset(prediction, targets), huber_after_offset(prediction, targets, clean)

    log_path = args.out/"history.jsonl"
    log_path.write_text("")
    def log(row):
        row["elapsed_seconds"] = round(time.monotonic() - started, 1)
        with log_path.open("a") as handle:
            handle.write(json.dumps(row)+"\n")
        print(row, flush=True)

    anchor = pack_circuit(template)
    current = anchor
    anchor_mae, anchor_clean = validator(config, template, clean=True)
    current_area = start_area = real_area([template])[0] if args.objective == "area" else None
    best = {"circuit": template, "mae": anchor_mae, "area": current_area, "clean_mae": anchor_clean}
    log({"generation": 0, "validation_mix_mae_m": anchor_mae, "validation_clean_mae_m": anchor_clean,
         "area_um2": current_area})
    third, half = max(args.population//3, 3), max(args.population//2, 2)
    for generation in range(1, args.generations + 1):
        if args.objective == "area":
            candidates = []
            for kind, split in (("table", train), ("wire", routing), ("prune", train)):
                inputs, codes = mutate(*current, third, kind, base_bits, generator)
                inputs[0], codes[0] = current
                inputs[1], codes[1] = anchor
                mixed, clean = losses(inputs, codes, batch(split))
                estimate = area_model.estimate(config, inputs, codes)
                feasible = mixed <= mixed[1]*(1 + args.accuracy_tolerance)
                if args.clean_limit:
                    feasible &= clean <= clean[1]*(1 + args.accuracy_tolerance)
                feasible[:2] = False
                for i in torch.nonzero(feasible).flatten().tolist():
                    candidates.append((float(estimate[i]), float(mixed[i]), inputs[i], codes[i]))
            candidates.sort(key=lambda x: (x[0], x[1]))

            def holds_up(choice):
                for split in (train, routing):
                    pair = (torch.stack((anchor[0], choice[0])), torch.stack((anchor[1], choice[1])))
                    mixed, clean = losses(*pair, batch(split))
                    if mixed[1] > mixed[0]*(1 + args.accuracy_tolerance):
                        return False
                    if args.clean_limit and clean[1] > clean[0]*(1 + args.accuracy_tolerance):
                        return False
                return True

            shortlist = candidates[:args.synth_candidates]
            if shortlist:
                areas = real_area([unpack_circuit(template, x[2], x[3]) for x in shortlist])
                for i in sorted(range(len(shortlist)), key=lambda i: (areas[i], shortlist[i][1])):
                    if areas[i] > current_area:
                        break
                    if holds_up((shortlist[i][2], shortlist[i][3])):
                        current, current_area = (shortlist[i][2], shortlist[i][3]), areas[i]
                        break
        else:
            deltas, members = [], []
            for kind, split in (("table", train), ("wire", routing)):
                inputs, codes = mutate(*current, half, kind, base_bits, generator)
                inputs[0], codes[0] = current
                inputs[1], codes[1] = anchor
                mixed, clean = losses(inputs, codes, batch(split))
                scores = mixed + args.search_area_weight*area_model.estimate(config, inputs, codes)
                delta = scores - scores[0]
                delta[:2] = float("inf")
                if args.clean_limit:   # hard limit: clean rays no worse than the start circuit's, plus tolerance
                    delta[clean > clean[1]*(1 + args.accuracy_tolerance)] = float("inf")
                pick = int(delta.argmin())
                deltas.append(float(delta[pick]))
                members.append((inputs[pick], codes[pick]))
            winner = 0 if deltas[0] <= deltas[1] else 1
            if deltas[winner] <= 0:
                current = members[winner]
        if generation % args.validate_every == 0 or generation == args.generations:
            circuit = unpack_circuit(template, *current)
            (args.out/"checkpoints").mkdir(exist_ok=True)
            (args.out/"checkpoints"/f"gen{generation:04d}.json").write_text(json.dumps(circuit)+"\n")
            mae, clean_mae = validator(config, circuit, clean=True)
            clean_ok = not args.clean_limit or clean_mae <= anchor_clean*(1 + args.accuracy_tolerance)
            if args.objective == "area":
                if clean_ok and mae <= anchor_mae*(1 + args.accuracy_tolerance) and (
                        current_area < best["area"] or (current_area == best["area"] and mae < best["mae"])):
                    best = {"circuit": circuit, "mae": mae, "area": current_area, "clean_mae": clean_mae}
            elif clean_ok and mae < best["mae"]:
                best = {"circuit": circuit, "mae": mae, "area": None, "clean_mae": clean_mae}
            log({"generation": generation, "validation_mix_mae_m": mae, "validation_clean_mae_m": clean_mae,
                 "search_area_um2": current_area, "best_mae": best["mae"], "best_area_um2": best["area"]})
    final = unpack_circuit(template, *current)
    (args.out/"search_end_circuit.json").write_text(json.dumps(final)+"\n")
    (args.out/"circuit.json").write_text(json.dumps(best["circuit"])+"\n")
    (args.out/"summary.json").write_text(json.dumps({
        "arguments": {k: str(v) if isinstance(v, Path) else v for k, v in vars(args).items()},
        "start_validation_mix_mae_m": anchor_mae, "start_area_um2": start_area,
        "start_validation_clean_mae_m": anchor_clean, "selected_validation_clean_mae_m": best["clean_mae"],
        "selected_validation_mix_mae_m": best["mae"], "selected_area_um2": best["area"],
        "seconds": time.monotonic() - started}, indent=2)+"\n")


if __name__ == "__main__":
    main()
