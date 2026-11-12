"""Hard search with a settling constraint (copy of the search part of spad/training/train_stream.py).

Settling enters through the answer read after 16, 32 and 64 photons of full 64-photon streams
(same splits as the standard loss, extra ambient 0-0.6), scored with the same Huber loss as the
standard term and the SAME per-member offset (the median error on the standard random-count
batch): one calibration constant for every readout, as a chip would have.

--objective area      keep the smallest circuit (real Yosys area) whose standard loss stays within
                      --accuracy-tolerance of the start and, with --settle-limit, whose settle loss
                      stays within --settle-tolerance of the start (hard limit). --settle-weight adds
                      the settle loss to the standard loss instead (weighted form).
--objective accuracy  minimise standard loss + settle_weight * settle loss + search_area_weight * area,
                      with the estimated area capped at the start's (--area-cap); selection keeps the
                      best validation MAE + settle_weight_m * settle MAE among circuits whose real area
                      is no larger than the start's.
No gradient phase: start from a circuit.
"""
import argparse
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict
import json
from pathlib import Path
import time

import torch

from spad import ROOT
from spad.dataset.photons import load_rays, sample_conditions
from spad.training.police import Police, measure_pulse
from spad.training.train_stream import Validator, mutate
from spad.hardware.area_model import MODEL_PATH, AreaModel
from spad.core.stream_model import (StreamConfig, input_names, pack_circuit, set_search_compile,
                                    simulate_population_packed, unpack_circuit)
from constraints_lab.settle.settle import full_streams, trace_stream, trace_population_packed, curve_metrics

SETTLE_READOUTS = (16, 32, 64)


def huber(error):
    return torch.nn.functional.huber_loss(error, torch.zeros_like(error), delta=4., reduction="none").mean(-1)


def population_terms(config, inputs, codes, data, settle_data, police=None, police_weight=0.):
    """Standard loss [circuits] and settle loss [readouts, circuits] (None without settle data)."""
    photons, targets, evidence = data
    prediction = simulate_population_packed(config, inputs, codes, photons).float()
    error = prediction - targets[None]
    offset = error.median(-1, keepdim=True).values
    loss = huber(error - offset)
    if police is not None and police_weight:
        loss = loss + police_weight*police.violations(prediction, evidence)["physics"].float().mean(-1)
    if settle_data is None:
        return loss, None
    settle_photons, settle_targets = settle_data
    trace = trace_population_packed(config, inputs, codes, settle_photons, SETTLE_READOUTS).float()
    return loss, huber(trace - settle_targets[None, None] - offset[None])


class SettleValidator:
    """Settle score on validation: readouts after 16/32/64 photons of full streams, one offset."""
    def __init__(self, validation, max_background, sets=3, seed=4321):
        g = torch.Generator().manual_seed(seed)
        self.photons = torch.cat([full_streams(validation[0], 64, max_background, g)[0] for _ in range(sets)])
        self.targets = validation[1].repeat(sets)

    def __call__(self, circuit, offset):
        raw = trace_stream(circuit, self.photons, SETTLE_READOUTS)
        rows = {n: curve_metrics(raw[n].float() - offset, self.targets) for n in SETTLE_READOUTS}
        return {"settle_mae_m": sum(r["mae_m"] for r in rows.values())/len(rows),
                "settle_huber_bins": float(sum(huber((raw[n].float() - offset - self.targets)[None])[0]
                                               for n in SETTLE_READOUTS)/len(SETTLE_READOUTS)),
                **{f"mae_m@{n}": r["mae_m"] for n, r in rows.items()},
                **{f"within_3_bins@{n}": r["within_3_bins"] for n, r in rows.items()}}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--data", type=Path, default=ROOT/"data")
    p.add_argument("--out", type=Path, required=True)
    p.add_argument("--init-circuit", type=Path, required=True)
    p.add_argument("--objective", choices=("accuracy", "area"), default="area")
    p.add_argument("--settle-weight", type=float, default=0.)
    p.add_argument("--settle-weight-m", type=float, default=None,
                   help="accuracy selection: weight of validation settle MAE (default: --settle-weight)")
    p.add_argument("--settle-limit", action="store_true", help="area objective: hard limit on settle loss")
    p.add_argument("--settle-tolerance", type=float, default=.05)
    p.add_argument("--settle-rays", type=int, default=2048)
    p.add_argument("--accuracy-tolerance", type=float, default=.05)
    p.add_argument("--area-cap", action="store_true", help="accuracy objective: estimated area <= start's")
    p.add_argument("--recheck", action="store_true",
                   help="accuracy objective: the winner must also improve on fresh pixels from both splits")
    p.add_argument("--synth-candidates", type=int, default=3)
    p.add_argument("--synth-workers", type=int, default=1)
    p.add_argument("--min-photons", type=int, default=16)
    p.add_argument("--max-photons", type=int, default=256)
    p.add_argument("--max-background", type=float, default=.6)
    p.add_argument("--police-search-weight", type=float, default=4.)
    p.add_argument("--search-area-weight", type=float, default=0.05)
    p.add_argument("--generations", type=int, default=500)
    p.add_argument("--population", type=int, default=192)
    p.add_argument("--search-rays", type=int, default=4096)
    p.add_argument("--validate-every", type=int, default=20)
    p.add_argument("--photon-sets", type=int, default=3)
    p.add_argument("--seed", type=int, default=0)
    p.add_argument("--threads", type=int, default=1)
    p.add_argument("--compile-search", choices=("none", "default"), default="none")
    args = p.parse_args()
    if args.settle_weight_m is None:
        args.settle_weight_m = args.settle_weight
    device = torch.device("cpu")
    torch.set_num_threads(args.threads)
    torch.manual_seed(args.seed)
    args.out.mkdir(parents=True, exist_ok=True)
    log_path = args.out/"history.jsonl"
    log_path.write_text("")
    train = load_rays(args.data, "train", clean_only=True)[:2]
    routing = load_rays(args.data, "architecture", clean_only=True)[:2]
    validation = load_rays(args.data, "validation")[:2]
    conditions = (args.min_photons, args.max_photons, args.max_background)
    pulse, zero = measure_pulse(train[0])
    police = Police(pulse, zero)
    validator = Validator(train, validation, conditions, args.photon_sets, police)
    settle_validator = SettleValidator(validation, args.max_background)
    generator = torch.Generator().manual_seed(args.seed)
    template = json.loads(args.init_circuit.read_text())
    config = StreamConfig(**template["config"])
    area_model = AreaModel(MODEL_PATH, device)
    set_search_compile(None if args.compile_search == "none" else args.compile_search)
    use_settle = args.settle_limit or args.settle_weight > 0
    started = time.monotonic()
    synthesized = {}

    def real_area(circuits):
        from spad.hardware.synth import synthesize
        from spad.hardware.verilog import stream_verilog
        keys = [json.dumps(c["layers"], separators=(",", ":")) for c in circuits]
        todo = {k: c for k, c in zip(keys, circuits) if k not in synthesized}
        work = lambda c: synthesize(stream_verilog(c), "photon_core", args.data)["area"] or 0.
        with ThreadPoolExecutor(max(1, args.synth_workers)) as pool:
            for key, area in zip(todo, pool.map(work, todo.values())):
                synthesized[key] = area
        return [synthesized[k] for k in keys]

    def log(row):
        row["elapsed_seconds"] = round(time.monotonic() - started, 1)
        with log_path.open("a") as handle:
            handle.write(json.dumps(row)+"\n")
        print(row, flush=True)

    def evaluate(circuit):
        mae = validator(circuit)["mae_m"]
        settle = settle_validator(circuit, validator.offset(circuit))
        return mae, settle, real_area([circuit])[0]

    start_mae, start_settle, start_area = evaluate(template)
    best = {"circuit": template, "mae": start_mae, "settle": start_settle, "area": start_area,
            "score": start_mae + args.settle_weight_m*start_settle["settle_mae_m"]}
    log({"phase": "start", "validation_mae_m": start_mae, **start_settle, "area_um2": start_area})

    def consider(circuit, row):
        mae, settle, area = evaluate(circuit)
        if args.objective == "area":
            allowed = mae <= start_mae*(1 + args.accuracy_tolerance)
            if args.settle_limit:
                allowed &= settle["settle_huber_bins"] <= start_settle["settle_huber_bins"]*(1 + args.settle_tolerance)
            if allowed and (area < best["area"] or (area == best["area"] and mae < best["mae"])):
                best.update(circuit=circuit, mae=mae, settle=settle, area=area)
        else:
            score = mae + args.settle_weight_m*settle["settle_mae_m"]
            if area <= start_area and score < best["score"]:
                best.update(circuit=circuit, mae=mae, settle=settle, area=area, score=score)
        log({**row, "validation_mae_m": mae, **settle, "area_um2": area, "best_mae": best["mae"],
             "best_area_um2": best["area"]})

    base_bits = len(input_names(config))
    current = pack_circuit(template, device)
    anchor = pack_circuit(template, device)
    start_estimate = area_model.circuit_area(template)

    def batch(split):
        pick = torch.randint(len(split[1]), (args.search_rays,), generator=generator)
        photons = sample_conditions(split[0][pick], *conditions, generator)[0]
        data = (photons, split[1][pick], police.evidence(photons))
        if not use_settle:
            return data, None
        pick = torch.randint(len(split[1]), (args.settle_rays,), generator=generator)
        return data, (full_streams(split[0][pick], 64, args.max_background, generator)[0], split[1][pick])

    def combined(loss, settle):
        return loss if settle is None or not args.settle_weight else loss + args.settle_weight*settle.mean(0)

    def passes(loss, settle, ref):
        """Mutants (all members) against reference member `ref` on the same pixels."""
        ok = combined(loss, settle) <= combined(loss, settle)[ref]*(1 + args.accuracy_tolerance)
        if args.settle_limit:
            s = settle.mean(0)
            ok &= s <= s[ref]*(1 + args.settle_tolerance)
        return ok

    current_area = start_area
    for generation in range(1, args.generations + 1):
        if args.objective == "area":
            third = max(args.population//3, 3)
            candidates = []
            for kind, split in (("table", train), ("wire", routing), ("prune", train)):
                inputs, codes = mutate(*current, third, kind, base_bits, generator)
                inputs[0], codes[0] = current
                inputs[1], codes[1] = anchor
                loss, settle = population_terms(config, inputs, codes, *batch(split), police, args.police_search_weight)
                estimate = area_model.estimate(config, inputs, codes)
                feasible = passes(loss, settle, 1)
                feasible[:2] = False
                score = combined(loss, settle)
                for i in torch.nonzero(feasible).flatten().tolist():
                    candidates.append((float(estimate[i]), float(score[i]), inputs[i], codes[i]))
            candidates.sort(key=lambda x: (x[0], x[1]))

            def holds_up(choice):
                for split in (train, routing):
                    pair = (torch.stack((anchor[0], choice[0])), torch.stack((anchor[1], choice[1])))
                    loss, settle = population_terms(config, *pair, *batch(split), police, args.police_search_weight)
                    if not bool(passes(loss, settle, 0)[1]):
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
                        break
        else:
            half = max(args.population//2, 2)
            deltas, members = [], []
            for kind, split in (("table", train), ("wire", routing)):
                inputs, codes = mutate(*current, half, kind, base_bits, generator)
                inputs[0], codes[0] = current
                loss, settle = population_terms(config, inputs, codes, *batch(split), police, args.police_search_weight)
                estimate = area_model.estimate(config, inputs, codes)
                scores = combined(loss, settle) + args.search_area_weight*estimate
                if args.area_cap:
                    scores = torch.where(estimate <= start_estimate, scores, torch.full_like(scores, float("inf")))
                delta = scores - scores[0]
                delta[0] = float("inf")
                pick = int(delta.argmin())
                deltas.append(float(delta[pick]))
                members.append((inputs[pick], codes[pick]))
            winner = 0 if deltas[0] <= deltas[1] else 1

            def improves(choice):
                # The best of 96 mutants on one sample is biased toward luck (the plain loop drifts
                # worse from a converged start), so it must also score better on fresh pixels
                # from both design splits.
                pair = (torch.stack((current[0], choice[0])), torch.stack((current[1], choice[1])))
                for split in (train, routing):
                    loss, settle = population_terms(config, *pair, *batch(split), police, args.police_search_weight)
                    s = combined(loss, settle) + args.search_area_weight*area_model.estimate(config, *pair)
                    if s[1] > s[0]:
                        return False
                return True

            if deltas[winner] <= 0 and (not args.recheck or improves(members[winner])):
                current = members[winner]
        if generation % args.validate_every == 0 or generation == args.generations:
            search_circuit = unpack_circuit(template, *current)
            (args.out/"search_end_circuit.json").write_text(json.dumps(search_circuit)+"\n")
            consider(search_circuit, {"phase": "hard", "generation": generation, "search_area_um2": current_area})

    circuit = dict(best["circuit"])
    circuit["offset_bins"] = validator.offset(circuit)
    circuit["budget"] = args.max_photons
    circuit["conditions"] = {"min_photons": args.min_photons, "max_photons": args.max_photons,
                             "max_background": args.max_background}
    (args.out/"circuit.json").write_text(json.dumps(circuit)+"\n")
    summary = {"arguments": {k: str(v) if isinstance(v, Path) else v for k, v in vars(args).items()},
               "config": asdict(config), "start": {"validation_mae_m": start_mae, **start_settle, "area_um2": start_area},
               "selected": {"validation_mae_m": best["mae"], **best["settle"], "area_um2": best["area"]},
               "seconds": time.monotonic() - started}
    (args.out/"summary.json").write_text(json.dumps(summary, indent=2)+"\n")
    print(json.dumps(summary["selected"]), flush=True)


if __name__ == "__main__":
    main()
