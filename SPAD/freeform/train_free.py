"""Train the free-form core: gradients first, then exact mutation search.

Same data, splits and randomized conditions as the other SPAD models (truth tables
on the train split, wiring on the architecture split, circuits chosen on the
validation split, held-out captures never loaded), but the circuit starts with no
datapath at all: see free_model.py.

Phase 1 (gradient): soft gates and soft wiring, annealed, then straight-through
binary. Phase 2 (hard search): copies of the best exact circuit each get one to
three random edits (flip a truth-table bit or rewire an input); the best copy on
a sample of pixels replaces the parent if it is no worse.

Three aids, each switchable, change how training runs, not what the circuit is:
  curriculum   each phase starts with many photons and no added background and
               reaches the full conditions (16-256 photons, ambient 0-0.6) partway
               through. Validation always uses the full conditions.
  readouts     the answer is also scored after photons 16, 32, 64 and 128, not only
               at the end, so partial progress is rewarded (both phases). The gradient
               phase also scores each output bit (Brier score), a denser signal than
               the single 10-bit number.
  samples      the search scores mutants on larger pixel samples and keeps a sample
               for several generations, so an accepted change is a real gain more
               often than sampling noise.

Usage (from SPAD/):
  ../.venv/bin/python -m freeform.train_free --out runs/freeform-test --steps 300 --generations 200
"""
import argparse
from dataclasses import asdict
import json
import math
from pathlib import Path
import time

import torch

from spad import ROOT
from spad.dataset.photons import load_rays, sample_conditions
from spad.training.baselines import metrics
from freeform.free_model import (FreeConfig, FreeCore, live_gates, pack_circuit, pack_photons, simulate_free,
                                 simulate_population_packed, unpack_circuit)


def centred_loss(prediction, targets, delta=4.):
    """Huber loss after removing a constant offset (a calibration constant, as in the other models)."""
    error = prediction - targets
    error = error - error.median(-1, keepdim=True).values.detach()
    return torch.nn.functional.huber_loss(error, torch.zeros_like(error), delta=delta, reduction="none").mean(-1)


class Validator:
    """Fixed validation photons under randomized conditions; offset fitted on train pixels."""
    def __init__(self, train, validation, conditions, sets, seed=7):
        device = train[0].device
        generator = torch.Generator(device=device).manual_seed(seed)
        pick = torch.randperm(len(train[1]), generator=generator, device=device)[:8000]
        self.fit_targets = train[1][pick]
        self.fit_photons = sample_conditions(train[0][pick], *conditions, generator)[0]
        draws = [sample_conditions(validation[0], *conditions, generator) for _ in range(sets)]
        self.photons, self.counts, self.background = (torch.cat(x) for x in zip(*draws))
        self.targets = validation[1].repeat(sets)

    def offset(self, circuit):
        return float((simulate_free(circuit, self.fit_photons).float() - self.fit_targets).median())

    def __call__(self, circuit):
        return metrics(simulate_free(circuit, self.photons).float() - self.offset(circuit), self.targets)

    def reference(self):
        """What a circuit that ignores the photons would score: always the median training range."""
        constant = self.fit_targets.median()
        return metrics(constant.expand(len(self.targets)), self.targets)

    def audit(self, circuit, shift=24):
        raw = simulate_free(circuit, self.photons).float()
        prediction = raw - self.offset(circuit)
        report = {"overall": metrics(prediction, self.targets)}
        for low, high in ((16, 32), (32, 64), (64, 128), (128, 257)):
            keep = (self.counts >= low) & (self.counts < high)
            if keep.any():
                row = metrics(prediction[keep], self.targets[keep])
                row["median_signed_bins"] = float((prediction[keep] - self.targets[keep]).median())
                report[f"photons_{low}-{min(high, 256)}"] = row
        # A range estimator must move with the photons. A circuit that memorized typical
        # ranges instead of measuring fails this: delay every photon and see if the answer follows.
        latest = self.photons.max(1).values
        movable = (latest + shift < 672) & (latest >= 0)
        moved = torch.where(self.photons >= 0, self.photons + shift, self.photons)[movable]
        change = simulate_free(circuit, moved).float() - raw[movable]
        report["time_shift_test"] = {"shift_bins": shift, "rays": int(movable.sum()),
                                     "median_change_bins": float(change.median()),
                                     "moves_with_photons_within_1_bin": float(((change - shift).abs() <= 1).float().mean()),
                                     "moves_with_photons_within_8_bins": float(((change - shift).abs() <= 8).float().mean())}
        return report


def readout_loss(values, targets, readouts, weight):
    """Final-answer loss plus `weight` times the mean loss of the answers after `readouts` photons.

    values: [steps or readouts + 1, ..., rays], last row final. Returns [...] losses.
    """
    final = centred_loss(values[-1], targets)
    if not weight or len(values) == 1:
        return final
    early = torch.stack([centred_loss(v, targets) for v in values[:-1]]).mean(0)
    return (final + weight * early) / (1 + weight)


def bit_loss(bits, values, targets, arrival_bits):
    """Brier score of each output bit against the target's bits, after the circuit's own offset.

    Bits are weighted by 2^(i/2): high bits matter more, low bits still count.
    """
    offset = (values[-1] - targets).median().round().detach()
    goal = (targets.round() + offset).clamp(0, 2 ** arrival_bits - 1).long()
    shifts = torch.arange(arrival_bits, device=targets.device)
    goal_bits = ((goal[:, None] >> shifts) & 1).float()
    weights = 2. ** (shifts / 2.)
    return ((bits - goal_bits).square() @ (weights / weights.sum())).mean()


def mutate(config, inputs, codes, count, generator):
    """`count` copies of a circuit, each with one to three random edits."""
    device = inputs.device
    inputs = inputs[None].repeat(count, 1, 1, 1)
    codes = codes[None].repeat(count, 1, 1)
    members = torch.arange(count, device=device)
    rand = lambda n: torch.rand(n, generator=generator, device=device)
    randint = lambda high, n: torch.randint(high, (n,), generator=generator, device=device)
    for edit, chance in enumerate((1., .4, .15)):
        chosen = members if edit == 0 else members[rand(count) < chance]
        n = len(chosen)
        layer, gate = randint(config.layers, n), randint(config.width, n)
        table = rand(n) < .5
        flipped = codes[chosen, layer, gate] ^ (1 << randint(4, n)).int()
        codes[chosen, layer, gate] = torch.where(table, flipped, codes[chosen, layer, gate])
        port = randint(2, n)
        sources = config.base_bits + config.width * layer
        pick = (rand(n) * sources).long()
        inputs[chosen, layer, gate, port] = torch.where(table, inputs[chosen, layer, gate, port], pick)
    return inputs, codes


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--data", type=Path, default=ROOT/"data")
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--device", default="cuda" if torch.cuda.is_available() else "cpu")
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--state-bits", type=int, default=32)
    parser.add_argument("--width", type=int, default=48)
    parser.add_argument("--layers", type=int, default=4)
    parser.add_argument("--init", choices=("residual", "random"), default="residual")
    parser.add_argument("--min-photons", type=int, default=16)
    parser.add_argument("--max-photons", type=int, default=256)
    parser.add_argument("--max-background", type=float, default=.6)
    parser.add_argument("--curriculum", type=float, default=.5,
                        help="fraction of each phase spent ramping from easy to full conditions (0 = off)")
    parser.add_argument("--easy-min-photons", type=int, default=128, help="fewest photons at the start of the curriculum")
    parser.add_argument("--readouts", default="16,32,64,128", help="also score the answer after these photons ('' = off)")
    parser.add_argument("--readout-weight", type=float, default=1.)
    parser.add_argument("--bit-weight", type=float, default=50.,
                        help="weight of the per-bit Brier score in the gradient phase (0 = off)")
    parser.add_argument("--resample-every", type=int, default=4, help="search generations per pixel sample")
    parser.add_argument("--steps", type=int, default=1500, help="gradient steps (0 skips phase 1)")
    parser.add_argument("--ste-fraction", type=float, default=.5, help="last part of phase 1 run straight-through")
    parser.add_argument("--batch-size", type=int, default=512)
    parser.add_argument("--lr", type=float, default=.02)
    parser.add_argument("--architecture-lr", type=float, default=.02)
    parser.add_argument("--start-temperature", type=float, default=2.)
    parser.add_argument("--end-temperature", type=float, default=.2)
    parser.add_argument("--generations", type=int, default=3000, help="hard-search generations (0 skips phase 2)")
    parser.add_argument("--population", type=int, default=512)
    parser.add_argument("--search-rays", type=int, default=4096)
    parser.add_argument("--validate-every", type=int, default=50)
    parser.add_argument("--validation-sets", type=int, default=2)
    parser.add_argument("--max-seconds", type=float, default=0, help="stop cleanly after this long (0 = no limit)")
    args = parser.parse_args()

    started = time.time()
    out_of_time = lambda: args.max_seconds and time.time() - started > args.max_seconds
    torch.manual_seed(args.seed)
    device = torch.device(args.device)
    args.out.mkdir(parents=True, exist_ok=True)
    config = FreeConfig(args.state_bits, args.width, args.layers)
    conditions = (args.min_photons, args.max_photons, args.max_background)
    readouts = tuple(int(x) for x in args.readouts.split(",") if x)

    def schedule(progress):
        """Training conditions at `progress` (0-1) through a phase: easy first, then full."""
        r = 1. if not args.curriculum else min(progress / args.curriculum, 1.)
        easy, hard = math.log(args.easy_min_photons), math.log(args.min_photons)
        return (math.exp(easy + (hard - easy) * r), args.max_photons, args.max_background * r)
    train, routing, validation = ([x.to(device) for x in load_rays(args.data, split)[:2]]
                                  for split in ("train", "architecture", "validation"))
    generator = torch.Generator(device=device).manual_seed(args.seed)
    validator = Validator(train, validation, conditions, args.validation_sets)
    reference = validator.reference()
    print(f"{device}: train {len(train[1])} rays, architecture {len(routing[1])}, validation {len(validator.targets)}; "
          f"{config.layers} x {config.width} gates, {config.state_bits} flip-flops", flush=True)
    print(f"reference (ignores photons, always the median range): MAE {reference['mae_m']:.3f} m", flush=True)

    model = FreeCore(config, args.init).to(device)
    history = []
    best = {"circuit": model.circuit(), "mae": None, "where": None}

    def consider(circuit, where):
        score = validator(circuit)
        history.append({**where, **score, "seconds": time.time() - started})
        if best["mae"] is None or score["mae_m"] < best["mae"]:
            best.update(circuit=circuit, mae=score["mae_m"], where=where)
            (args.out/"circuit.json").write_text(json.dumps(circuit) + "\n")
        return score["mae_m"]

    def batch(split, rays, progress):
        pick = torch.randint(len(split[1]), (rays,), generator=generator, device=device)
        return sample_conditions(split[0][pick], *schedule(progress), generator)[0], split[1][pick]

    consider(model.circuit(), {"phase": "start"})
    print(f"start: validation MAE {best['mae']:.3f} m", flush=True)

    # ---------------------------------------------------------------- phase 1: gradients
    weights, architecture = model.weight_parameters(), model.architecture_parameters()
    weight_optimizer = torch.optim.Adam(weights, lr=args.lr)
    architecture_optimizer = torch.optim.Adam(architecture, lr=args.architecture_lr)
    skipped = 0
    for step in range(1, args.steps + 1):
        if args.max_seconds and time.time() - started > .35 * args.max_seconds:   # leave time for the search
            print(f"gradient phase stopped at step {step} to leave time for the search", flush=True)
            break
        progress = step / args.steps
        temperature = args.start_temperature * (args.end_temperature / args.start_temperature) ** progress
        ste = progress > 1 - args.ste_fraction
        for split, optimizer, active, frozen in ((routing, architecture_optimizer, architecture, weights),
                                                 (train, weight_optimizer, weights, architecture)):
            for p in frozen:
                p.requires_grad_(False)
            photons, targets = batch(split, args.batch_size, progress)
            values, bits = model(photons, temperature, ste, trajectory=True)
            marks = [k - 1 for k in readouts if k < len(values)]
            loss = readout_loss(values[marks + [-1]], targets, readouts, args.readout_weight)
            if args.bit_weight:
                loss = loss + args.bit_weight * bit_loss(bits[marks + [-1]], values, targets, config.arrival_bits)
            optimizer.zero_grad()
            loss.backward()
            if all(torch.isfinite(p.grad).all() for p in active if p.grad is not None):
                torch.nn.utils.clip_grad_norm_(active, 1.)
                optimizer.step()
            else:
                skipped += 1
            for p in frozen:
                p.requires_grad_(True)
        if step % 50 == 0 or step == args.steps:
            mae = consider(model.circuit(), {"phase": "gradient", "step": step, "temperature": temperature,
                                             "straight_through": ste, "loss": float(loss.detach())})
            print(f"step {step:5d}  T {temperature:.2f}  {'ste ' if ste else 'soft'}  loss {float(loss.detach()):8.2f}  "
                  f"hard validation MAE {mae:.3f} m (best {best['mae']:.3f})  {time.time() - started:.0f} s", flush=True)
    gradient_best = best["mae"]

    # ---------------------------------------------------------------- phase 2: exact search
    inputs, codes = pack_circuit(best["circuit"], device)
    template = best["circuit"]
    accepted = improved = generation = 0
    for generation in range(1, args.generations + 1):
        if out_of_time():
            break
        if (generation - 1) % args.resample_every == 0:
            sample = (generation - 1) // args.resample_every
            photons, targets = batch(train if sample % 2 == 0 else routing, args.search_rays,
                                     generation / args.generations)
            packed = pack_photons(photons, config.arrival_bits)
        new_inputs, new_codes = mutate(config, inputs, codes, args.population, generator)
        all_inputs, all_codes = torch.cat((inputs[None], new_inputs)), torch.cat((codes[None], new_codes))
        prediction = simulate_population_packed(config, all_inputs, all_codes, packed, len(photons),
                                                readouts=readouts or None).float()
        if not readouts:
            prediction = prediction[None]
        scores = readout_loss(prediction, targets[None], readouts, args.readout_weight)
        winner = int(scores[1:].argmin()) + 1
        if scores[winner] <= scores[0]:
            accepted += 1
            improved += int(scores[winner] < scores[0])
            inputs, codes = all_inputs[winner], all_codes[winner]
        if generation % args.validate_every == 0 or generation == args.generations:
            mae = consider(unpack_circuit(template, inputs, codes),
                           {"phase": "hard", "generation": generation, "sample_loss": float(scores[0])})
            print(f"generation {generation:5d}  sample loss {float(scores[0]):8.2f}  validation MAE {mae:.3f} m "
                  f"(best {best['mae']:.3f})  accepted {accepted} improved {improved}  {time.time() - started:.0f} s",
                  flush=True)

    circuit = best["circuit"]
    summary = {"format": circuit["format"], "config": asdict(config), "arguments": {k: str(v) for k, v in vars(args).items()},
               "validation": validator(circuit), "chosen_at": best["where"], "offset_bins": validator.offset(circuit),
               "reference_ignoring_photons": reference, "gradient_best_validation_mae_m": gradient_best,
               "generations_run": generation, "accepted": accepted, "improved": improved,
               "skipped_nonfinite_steps": skipped, "gates": live_gates(circuit), "audit": validator.audit(circuit),
               "seconds": time.time() - started}
    (args.out/"summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    (args.out/"history.json").write_text(json.dumps(history) + "\n")
    shift = summary["audit"]["time_shift_test"]
    print(json.dumps({"validation": summary["validation"], "reference_mae_m": reference["mae_m"],
                      "gates": summary["gates"], "time_shift_test": shift}, indent=2))


if __name__ == "__main__":
    main()
