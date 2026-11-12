"""Copy of train_stream's hard search (no gradient phase) with tail terms and limits.

Two objectives, both starting from a circuit:
  --objective area      smallest real (Yosys) area whose Huber loss stays within --accuracy-tolerance of the
                        start (as train_stream), optionally also with the share of rays off by more than
                        1 m no worse than the start plus --tail-slack (--tail-limit).
  --objective accuracy  at fixed area (estimate and real area no larger than the start), minimize the search
                        loss --loss: huber (delta 4, as train_stream), capped (Huber capped at --cap-bins,
                        so a ray more than the cap away costs the same however far off it is), or
                        huber+share (Huber + --tail-weight x share over 1 m).

Every accepted change must hold up on fresh pixels of both design splits (as in train_stream).
Selection on validation (seed 7): area: smallest real area with MAE within tolerance (and, with
--tail-limit, share over 1 m no worse than start + --tail-slack-validation); accuracy: lowest
validation share over 1 m with MAE within tolerance. Reported with Validator(seed=1234).audit.

Run from SPAD/ through the slot wrapper, for example:
  ../.venv/bin/python -m constraints_lab.slot -- ../.venv/bin/python -m constraints_lab.tail.search \
      --out runs/2026-11-11_constraints-lab/tail/accuracy-capped --objective accuracy --loss capped ...
"""
import argparse
import json
from pathlib import Path
import time

import torch

from spad import ROOT
from spad.core.stream_model import (StreamConfig, input_names, pack_circuit, set_search_compile,
                                    simulate_population_packed, simulate_stream, unpack_circuit)
from spad.dataset.photons import sample_conditions
from spad.hardware.area_model import MODEL_PATH, AreaModel
from spad.hardware.synth import synthesize, verify
from spad.hardware.verilog import stream_verilog
from spad.training.train_stream import Validator, mutate

from constraints_lab.tail.common import CONDITIONS, ONE_METRE_BINS, load_circuit, setup, tail_stats


def population_terms(config, inputs, codes, data, police, police_weight, cap_bins):
    """Per member: Huber(4) loss + police (as train_stream), capped loss + police, share over 1 m."""
    photons, targets, evidence = data
    prediction = simulate_population_packed(config, inputs, codes, photons).float()
    error = prediction - targets[None]
    error = error - error.median(-1, keepdim=True).values
    each = torch.nn.functional.huber_loss(error, torch.zeros_like(error), delta=4., reduction="none")
    cap = float(torch.nn.functional.huber_loss(torch.tensor(float(cap_bins)), torch.tensor(0.), delta=4.))
    penalty = 0.
    if police is not None and police_weight:
        penalty = police_weight*police.violations(prediction, evidence)["physics"].float().mean(-1)
    return {"huber": each.mean(-1) + penalty, "capped": each.clamp_max(cap).mean(-1) + penalty,
            "over_1m": (error.abs() > ONE_METRE_BINS).float().mean(-1)}


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--data", type=Path, default=ROOT/"data")
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--init-circuit", type=Path, required=True)
    parser.add_argument("--objective", choices=("area", "accuracy"), required=True)
    parser.add_argument("--loss", choices=("huber", "capped", "huber+share"), default="huber",
                        help="accuracy objective: what is minimized. area objective: what the tolerance limits")
    parser.add_argument("--cap-bins", type=float, default=9., help="capped loss: errors beyond this cost the same")
    parser.add_argument("--tail-weight", type=float, default=100., help="huber+share: loss per unit share over 1 m")
    parser.add_argument("--tail-limit", action="store_true", help="area objective: share over 1 m no worse than start")
    parser.add_argument("--tail-slack", type=float, default=0., help="search: allowed absolute rise in share over 1 m")
    parser.add_argument("--tail-slack-validation", type=float, default=0.,
                        help="selection: allowed absolute rise in validation share over 1 m")
    parser.add_argument("--accuracy-tolerance", type=float, default=.05)
    parser.add_argument("--synth-candidates", type=int, default=3)
    parser.add_argument("--police-search-weight", type=float, default=4.)
    parser.add_argument("--generations", type=int, default=500)
    parser.add_argument("--population", type=int, default=192)
    parser.add_argument("--search-rays", type=int, default=4096)
    parser.add_argument("--validate-every", type=int, default=20)
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--threads", type=int, default=1)
    parser.add_argument("--compile-search", choices=("none", "default"), default="default")
    args = parser.parse_args()
    torch.set_num_threads(args.threads)
    torch.manual_seed(args.seed)
    args.out.mkdir(parents=True, exist_ok=True)
    log_path = args.out/"history.jsonl"
    log_path.write_text("")
    started = time.monotonic()
    train, routing, validation, police = setup(args.data)
    validator = Validator(train, validation[:2], CONDITIONS, 3, police)          # seed 7: selection
    generator = torch.Generator().manual_seed(args.seed)
    template = load_circuit(args.init_circuit)
    config = StreamConfig(**template["config"])
    area_model = AreaModel(MODEL_PATH, torch.device("cpu"))
    set_search_compile(None if args.compile_search == "none" else args.compile_search)
    base_bits = len(input_names(config))
    limited_name = "huber" if args.loss == "huber+share" else args.loss   # area objective: the limited loss
    third = max(args.population//3, 3)
    synthesized = {}

    def real_area(circuit):
        key = json.dumps(circuit["layers"], separators=(",", ":"))
        if key not in synthesized:
            synthesized[key] = synthesize(stream_verilog(circuit), "photon_core", args.data)["area"] or 0.
        return synthesized[key]

    def batch(split):
        pick = torch.randint(len(split[1]), (args.search_rays,), generator=generator)
        photons = sample_conditions(split[0][pick], *CONDITIONS, generator)[0]
        return photons, split[1][pick], police.evidence(photons)

    def terms(inputs, codes, data):
        return population_terms(config, inputs, codes, data, police, args.police_search_weight, args.cap_bins)

    def objective(t):
        if args.loss == "huber":
            return t["huber"]
        if args.loss == "capped":
            return t["capped"]
        return t["huber"] + args.tail_weight*t["over_1m"]

    def validation_score(circuit):
        prediction = simulate_stream(circuit, validator.photons).float() - validator.offset(circuit)
        return tail_stats(prediction - validator.targets.float())

    anchor = pack_circuit(template)
    current = anchor
    start_area = real_area(template)
    start_estimate = float(area_model.estimate(config, anchor[0][None], anchor[1][None])[0])
    current_area = start_area
    start_val = validation_score(template)
    best = {"circuit": template, "area": start_area, "val": start_val, "generation": 0}
    accepted = 0

    def log(row):
        row["elapsed_seconds"] = round(time.monotonic() - started, 1)
        with log_path.open("a") as handle:
            handle.write(json.dumps(row)+"\n")
        print(row, flush=True)

    log({"phase": "start", "area_um2": start_area, "estimate_um2": start_estimate, **start_val})

    def allowed(val):
        ok = val["mae_m"] <= start_val["mae_m"]*(1 + args.accuracy_tolerance)
        if args.tail_limit or args.objective == "accuracy":
            ok = ok and val["over_1m"] <= start_val["over_1m"] + args.tail_slack_validation
        return ok

    def consider(circuit, area, generation):
        val = validation_score(circuit)
        if allowed(val):
            if args.objective == "area":
                better = area < best["area"] or (area == best["area"] and val["mae_m"] < best["val"]["mae_m"])
            else:
                better = val["over_1m"] < best["val"]["over_1m"] or (
                    val["over_1m"] == best["val"]["over_1m"] and val["mae_m"] < best["val"]["mae_m"])
            if better:
                best.update(circuit=circuit, area=area, val=val, generation=generation)
        log({"phase": "hard", "generation": generation, "area_um2": area, "accepted": accepted,
             **{f"val_{k}": v for k, v in val.items()}, "best_area_um2": best["area"],
             "best_val_over_1m": best["val"]["over_1m"], "best_val_mae_m": best["val"]["mae_m"]})

    for generation in range(1, args.generations + 1):
        candidates = []
        for kind, split in (("table", train), ("wire", routing), ("prune", train)):
            inputs, codes = mutate(*current, third, kind, base_bits, generator)
            inputs[0], codes[0] = current
            inputs[1], codes[1] = anchor
            t = terms(inputs, codes, batch(split))
            estimate = area_model.estimate(config, inputs, codes)
            score = objective(t)
            if args.objective == "area":
                feasible = t[limited_name] <= t[limited_name][1]*(1 + args.accuracy_tolerance)
                if args.tail_limit:
                    feasible &= t["over_1m"] <= t["over_1m"][1] + args.tail_slack
                key = estimate
            else:
                feasible = (score < score[0]) & (estimate <= start_estimate)
                key = score
            feasible[:2] = False
            for i in torch.nonzero(feasible).flatten().tolist():
                candidates.append((float(key[i]), float(score[i]), inputs[i].clone(), codes[i].clone()))
        candidates.sort(key=lambda x: (x[0], x[1]))

        def holds_up(choice):
            # Area objective: the winner must also pass the limits on fresh pixels of both design splits.
            for split in (train, routing):
                pair = (torch.stack((anchor[0], choice[0])), torch.stack((anchor[1], choice[1])))
                t = terms(*pair, batch(split))
                limited = t[limited_name]
                if limited[1] > limited[0]*(1 + args.accuracy_tolerance):
                    return False
                if args.tail_limit and t["over_1m"][1] > t["over_1m"][0] + args.tail_slack:
                    return False
            return True

        def improves(choice):
            # Accuracy objective: the mutant must beat the current circuit on fresh pixels of both splits.
            for split in (train, routing):
                pair = (torch.stack((current[0], choice[0])), torch.stack((current[1], choice[1])))
                score = objective(terms(*pair, batch(split)))
                if score[1] >= score[0]:
                    return False
            return True

        shortlist = candidates[:args.synth_candidates]
        if args.objective == "area" and shortlist:
            areas = [real_area(unpack_circuit(template, x[2], x[3])) for x in shortlist]
            for i in sorted(range(len(shortlist)), key=lambda i: (areas[i], shortlist[i][1])):
                if areas[i] > current_area:
                    break
                if holds_up((shortlist[i][2], shortlist[i][3])):
                    current, current_area = (shortlist[i][2], shortlist[i][3]), areas[i]
                    accepted += 1
                    break
        elif shortlist:
            for choice in shortlist:
                if improves((choice[2], choice[3])):
                    area = real_area(unpack_circuit(template, choice[2], choice[3]))
                    if area <= start_area:
                        current, current_area = (choice[2], choice[3]), area
                        accepted += 1
                        break
        if generation % args.validate_every == 0 or generation == args.generations:
            consider(unpack_circuit(template, *current), current_area, generation)

    circuit = dict(best["circuit"])
    circuit["offset_bins"] = validator.offset(circuit)
    fresh = Validator(train, validation[:2], CONDITIONS, 3, police, seed=1234)
    audit = fresh.audit(circuit)
    prediction = simulate_stream(circuit, fresh.photons).float() - fresh.offset(circuit)
    tail = tail_stats(prediction - fresh.targets.float())
    synth = synthesize(stream_verilog(circuit), "photon_core", args.data)
    parity = verify(stream_verilog(circuit), "photon_core", circuit)
    end_circuit = unpack_circuit(template, *current)
    end_prediction = simulate_stream(end_circuit, fresh.photons).float() - fresh.offset(end_circuit)
    summary = {"arguments": {k: str(v) if isinstance(v, Path) else v for k, v in vars(args).items()},
               "start_area_um2": start_area, "start_validation_selection": start_val,
               "chosen_generation": best["generation"], "accepted_changes": accepted,
               "selection_validation": best["val"],
               "audit_fresh_photons": audit, "tail_fresh_photons": tail,
               "synthesized": {k: v for k, v in synth.items() if k != "report"}, "netlist_mismatches": parity,
               "search_end": {"area_um2": current_area, "tail_fresh_photons": tail_stats(end_prediction - fresh.targets.float())},
               "seconds": time.monotonic() - started}
    (args.out/"circuit.json").write_text(json.dumps(circuit)+"\n")
    (args.out/"search_end_circuit.json").write_text(json.dumps(end_circuit)+"\n")
    (args.out/"summary.json").write_text(json.dumps(summary, indent=2)+"\n")
    print(json.dumps({"tail": tail, "synth": summary["synthesized"], "parity": parity}), flush=True)


if __name__ == "__main__":
    main()
