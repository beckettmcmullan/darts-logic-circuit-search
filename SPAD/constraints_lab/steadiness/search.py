"""Area-objective search (copy of the loop in spad/training/train_stream.py) with a steadiness term.

Steadiness = max(photon spread, background spread) of the range offset, measured on the paired
grid of constraints_lab/steadiness/steady.py (fixed photon counts 23/45/91/181, fixed extra
ambient 0.1/0.3/0.5, same pixels in every bucket).

--steady-mode off      the original loop (same random stream as train_stream for the same seed)
--steady-mode limit    hard limit: a change is accepted only if its steadiness <= --steady-limit
                       on a fresh grid sample (design splits), confirmed again on another fresh
                       sample; final selection also needs validation steadiness <= the limit.
--steady-mode penalty  weighted: score = loss + --steady-weight * steadiness where the original
                       compares losses (mutant filter, recheck), within the tolerance of the
                       start's score; mutants are pre-filtered at twice the loss tolerance so
                       better steadiness can buy back some loss. Selection is the original
                       (validation MAE within tolerance). The search loss is about 34 (bins),
                       so weight 1.0 makes 1 bin of extra spread cost about 3% of the loss.

Only the --steady-shortlist smallest-estimated loss-feasible mutants per generation are scored
for steadiness (the grid costs about as much per circuit as the search batch), so the extra cost
is small. Start from a circuit; there is no gradient phase.
"""
import argparse
import json
from pathlib import Path
import time

import torch

from constraints_lab.steadiness.steady import GridSample
from spad import ROOT
from spad.dataset.photons import load_rays, sample_conditions
from spad.hardware.area_model import MODEL_PATH, AreaModel
from spad.core.stream_model import (StreamConfig, input_names, pack_circuit, set_search_compile, unpack_circuit)
from spad.training.police import Police, measure_pulse
from spad.training.train_stream import Validator, mutate, population_losses
from spad.training.baselines import BIN_METERS


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data", type=Path, default=ROOT/"data")
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--init-circuit", type=Path, required=True)
    parser.add_argument("--steady-mode", choices=("off", "limit", "penalty"), default="limit")
    parser.add_argument("--steady-limit", type=float, default=1.0, help="bins, on max(photon, background) spread")
    parser.add_argument("--steady-weight", type=float, default=0.1, help="loss (bins) per bin of spread")
    parser.add_argument("--steady-rays", type=int, default=2048, help="pixels per design-split grid sample")
    parser.add_argument("--steady-shortlist", type=int, default=16)
    parser.add_argument("--synth-candidates", type=int, default=3)
    parser.add_argument("--synth-workers", type=int, default=1)
    parser.add_argument("--accuracy-tolerance", type=float, default=.05)
    parser.add_argument("--area-model", type=Path, default=MODEL_PATH)
    parser.add_argument("--min-photons", type=int, default=16)
    parser.add_argument("--max-photons", type=int, default=256)
    parser.add_argument("--max-background", type=float, default=.6)
    parser.add_argument("--police-search-weight", type=float, default=4.)
    parser.add_argument("--generations", type=int, default=500)
    parser.add_argument("--population", type=int, default=192)
    parser.add_argument("--search-rays", type=int, default=4096)
    parser.add_argument("--validate-every", type=int, default=20)
    parser.add_argument("--photon-sets", type=int, default=3)
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--threads", type=int, default=1)
    parser.add_argument("--compile-search", choices=("none", "default"), default="default")
    args = parser.parse_args()
    device = torch.device("cpu")
    torch.set_num_threads(args.threads)
    torch.manual_seed(args.seed)
    args.out.mkdir(parents=True, exist_ok=True)
    log_path = args.out/"history.jsonl"
    log_path.write_text("")
    train = [x for x in load_rays(args.data, "train", clean_only=True)[:2]]
    routing = [x for x in load_rays(args.data, "architecture", clean_only=True)[:2]]
    validation = [x for x in load_rays(args.data, "validation")[:2]]
    conditions = (args.min_photons, args.max_photons, args.max_background)
    pulse, zero = measure_pulse(train[0])
    police = Police(pulse, zero)
    validator = Validator(train, validation, conditions, args.photon_sets, Police(pulse, zero))
    generator = torch.Generator().manual_seed(args.seed)
    steady_generator = torch.Generator().manual_seed(args.seed + 1000)   # keeps `generator` identical to the original
    validation_grid = GridSample(validation, len(validation[1]), torch.Generator().manual_seed(99))
    start_circuit = json.loads(args.init_circuit.read_text())
    config = StreamConfig(**{k: start_circuit["config"][k] for k in ("state_bits", "width", "layers")})
    area_model = AreaModel(args.area_model, device)
    set_search_compile(None if args.compile_search == "none" else args.compile_search)
    synthesized_areas = {}

    def real_area(circuits):
        from concurrent.futures import ThreadPoolExecutor
        from spad.hardware.synth import synthesize
        from spad.hardware.verilog import stream_verilog
        keys = [json.dumps(c["layers"], separators=(",", ":")) for c in circuits]
        todo = {k: c for k, c in zip(keys, circuits) if k not in synthesized_areas}
        work = lambda c: synthesize(stream_verilog(c), "photon_core", args.data)["area"] or 0.
        with ThreadPoolExecutor(max(1, args.synth_workers)) as pool:
            for key, area in zip(todo, pool.map(work, todo.values())):
                synthesized_areas[key] = area
        return [synthesized_areas[k] for k in keys]

    circuit_area = lambda c: real_area([c])[0]
    started = time.monotonic()
    mode = args.steady_mode
    steadiness_of = lambda ps, bs: torch.maximum(ps, bs)

    def validation_steadiness(circuit):
        inputs, codes = pack_circuit(circuit)
        ps, bs, photon, ambient = validation_grid(config, inputs[None], codes[None])
        return float(steadiness_of(ps, bs)[0]), float(ps[0]), float(bs[0])

    def log(row):
        row["elapsed_seconds"] = round(time.monotonic() - started, 1)
        with log_path.open("a") as handle:
            handle.write(json.dumps(row)+"\n")
        print(row, flush=True)

    run = {"generation": 0, "best_circuit": start_circuit, "best_mae": None, "best_area": None,
           "anchor_mae": None, "anchor_steady": None, "best_steady": None, "accepted": 0, "steady_rejections": 0}

    def consider(circuit, row):
        mae = validator(circuit)["mae_m"]
        steady, ps, bs = validation_steadiness(circuit)
        area = circuit_area(circuit)
        if run["anchor_mae"] is None:
            run.update(best_circuit=circuit, best_mae=mae, best_area=area, anchor_mae=mae, anchor_steady=steady,
                       best_steady=steady)
        else:
            # Selection: validation MAE within tolerance (as the original); the limit mode also needs
            # validation steadiness within the limit. The penalty acts only inside the search.
            allowed = mae <= run["anchor_mae"]*(1 + args.accuracy_tolerance)
            if mode == "limit":
                allowed = allowed and steady <= args.steady_limit
            if allowed and (area < run["best_area"] or (area == run["best_area"] and mae < run["best_mae"])):
                run.update(best_circuit=circuit, best_mae=mae, best_area=area, best_steady=steady)
        log({**row, "validation_mae_m": mae, "validation_steadiness": steady, "photon_spread": ps,
             "background_spread": bs, "area_um2": area, "best": run["best_mae"], "best_area_um2": run["best_area"],
             "best_steadiness": run["best_steady"], "accepted": run["accepted"],
             "steady_rejections": run["steady_rejections"]})

    consider(start_circuit, {"phase": "start"})
    print(f"start {run['best_area']:.2f} µm², MAE {run['anchor_mae']:.3f} m, steadiness {run['anchor_steady']:.2f} bins; "
          f"mode {mode}", flush=True)
    template = start_circuit
    current = pack_circuit(template, device)
    anchor = pack_circuit(template, device)
    base_bits = len(input_names(config))
    third = max(args.population//3, 3)
    design = [torch.cat((train[0], routing[0])), torch.cat((train[1], routing[1]))]

    def batch(split):
        pick = torch.randint(len(split[1]), (args.search_rays,), generator=generator, device=device)
        photons = sample_conditions(split[0][pick], *conditions, generator)[0]
        return photons, split[1][pick], police.evidence(photons)

    def steady_scores(members):
        """Steadiness of [anchor, *members] on one fresh paired grid sample from the design splits."""
        sample = GridSample(design, args.steady_rays, steady_generator)
        inputs = torch.stack([anchor[0]] + [m[0] for m in members])
        codes = torch.stack([anchor[1]] + [m[1] for m in members])
        ps, bs, _, _ = sample(config, inputs, codes)
        return steadiness_of(ps, bs)

    loosen = 2 if mode == "penalty" else 1
    current_area = circuit_area(template)
    while run["generation"] < args.generations:
        candidates = []
        for kind, split in (("table", train), ("wire", routing), ("prune", train)):
            inputs, codes = mutate(*current, third, kind, base_bits, generator)
            inputs[0], codes[0] = current
            inputs[1], codes[1] = anchor
            losses = population_losses(config, inputs, codes, batch(split), police, args.police_search_weight)
            estimate = area_model.estimate(config, inputs, codes)
            feasible = losses <= losses[1]*(1 + loosen*args.accuracy_tolerance)
            feasible[:2] = False
            for i in torch.nonzero(feasible).flatten().tolist():
                candidates.append([float(estimate[i]), float(losses[i]), inputs[i], codes[i], float(losses[1])])
        candidates.sort(key=lambda x: (x[0], x[1]))
        if mode != "off" and candidates:
            short = [c for c in candidates if c[0] <= current_area + 1.][:args.steady_shortlist]
            if short:
                steady = steady_scores([(c[2], c[3]) for c in short])
                kept = []
                for c, s in zip(short, steady[1:].tolist()):
                    if mode == "limit":
                        ok = s <= args.steady_limit
                    else:
                        ok = c[1] + args.steady_weight*s <= (c[4] + args.steady_weight*float(steady[0]))*(1 + args.accuracy_tolerance)
                    if ok:
                        kept.append(c)
                    else:
                        run["steady_rejections"] += 1
                candidates = kept
            else:
                candidates = []

        def holds_up(choice):
            for split in (train, routing):
                pair = (torch.stack((anchor[0], choice[0])), torch.stack((anchor[1], choice[1])))
                check = population_losses(config, *pair, batch(split), police, args.police_search_weight)
                if mode == "penalty":
                    s = steady_scores([choice])
                    check = check + args.steady_weight*s
                if check[1] > check[0]*(1 + args.accuracy_tolerance):
                    return False
            if mode == "limit" and float(steady_scores([choice])[1]) > args.steady_limit:
                run["steady_rejections"] += 1
                return False
            return True

        if candidates:
            shortlist = candidates[:args.synth_candidates]
            areas_real = real_area([unpack_circuit(template, x[2], x[3]) for x in shortlist])
            for i in sorted(range(len(shortlist)), key=lambda i: (areas_real[i], shortlist[i][1])):
                if areas_real[i] > current_area:
                    break
                if holds_up((shortlist[i][2], shortlist[i][3])):
                    current, current_area = (shortlist[i][2], shortlist[i][3]), areas_real[i]
                    run["accepted"] += 1
                    break
        run["generation"] += 1
        if run["generation"] % args.validate_every == 0 or run["generation"] == args.generations:
            consider(unpack_circuit(template, *current), {"phase": "hard", "generation": run["generation"],
                                                          "search_area_um2": current_area})
            (args.out/"search_end_circuit.json").write_text(json.dumps(unpack_circuit(template, *current))+"\n")

    circuit = dict(run["best_circuit"])
    circuit["offset_bins"] = validator.offset(circuit)
    circuit["budget"] = args.max_photons
    circuit["conditions"] = {"min_photons": args.min_photons, "max_photons": args.max_photons,
                             "max_background": args.max_background}
    (args.out/"circuit.json").write_text(json.dumps(circuit)+"\n")
    summary = {"arguments": {k: str(v) if isinstance(v, Path) else v for k, v in vars(args).items()},
               "start_area_um2": circuit_area(start_circuit), "start_validation_mae_m": run["anchor_mae"],
               "start_validation_steadiness": run["anchor_steady"], "area_um2": run["best_area"],
               "selection_validation_mae_m": run["best_mae"], "selection_validation_steadiness": run["best_steady"],
               "accepted_changes": run["accepted"], "steady_rejections": run["steady_rejections"],
               "search_end_area_um2": current_area, "seconds": time.monotonic() - started}
    (args.out/"summary.json").write_text(json.dumps(summary, indent=2)+"\n")
    print(json.dumps(summary), flush=True)


if __name__ == "__main__":
    main()
