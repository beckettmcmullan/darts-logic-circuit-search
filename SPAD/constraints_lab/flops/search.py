"""Area-objective search with flip-flop constraints (copy of the loop in spad/training/train_stream.py).

Differences from the shared loop:
  --state-cap K     at most K live state bits. Bits are removed greedily (least train-loss increase
                    first) by forcing their next-value gate to constant 0; mutants never edit those
                    gates back, and mutants whose live state bits exceed K are rejected.
  --conf-bits Q     confidence counter width (Q < 4 needs the in-process relaxation in common.py).
  --flop-weight W   the search minimizes area + (W-1) * 0.3645 µm² per flip-flop (the DFF cell),
                    i.e. a flip-flop counts W times its cell area. W = 1 is the plain area objective.
  Repair mode       the error budget is always measured against the uncapped start circuit (the
                    anchor). When the capped start is worse than the anchor, the loop first accepts
                    the mutant that lowers error most (still under the cap) until the circuit is as
                    good as the anchor on fresh pixels from both design splits, or until
                    --repair-fraction of the generations is spent; then it runs the area objective
                    (every step within --accuracy-tolerance of the anchor).
Selection on validation (seed 7 photons, as in the trainer): the smallest weighted area whose MAE
is within the tolerance of the anchor; if none qualifies, the lowest-MAE circuit (reported as such).

Run (from SPAD/), e.g.:
  ../.venv/bin/python -m constraints_lab.slot -- ../.venv/bin/python -m constraints_lab.flops.search \
      --out runs/2026-11-11_constraints-lab/flops/cap2 --state-cap 2
"""
import argparse
import copy
import json
from pathlib import Path
import time

import torch

from spad import ROOT
from spad.core.stream_model import (StreamConfig, input_names, pack_circuit, set_search_compile,
                                    simulate_population_packed, unpack_circuit)
from spad.dataset.photons import sample_conditions
from spad.hardware.area_model import AreaModel, MODEL_PATH
from spad.training.train_stream import Validator, mutate, population_losses
from constraints_lab.flops.common import (CONDITIONS, allow_small_counter, load_circuit, load_data, parity,
                                          short_audit, synth_circuit)
from constraints_lab.flops.structure import structure

FLOP_CELL_AREA = 0.3645     # DFFHQx4_ASAP7_75t_R, the cell Yosys dfflibmap picks
DEFAULT_START = ROOT/"runs/2026-11-10_kaggle-t4_batch3_fused-larger-search/random-s4-seed0/circuit.json"


def kill_state(circuit, bits):
    out = copy.deepcopy(circuit)
    const0 = out["inputs"].index("const0")
    for i in bits:
        out["layers"][-1]["inputs"][i] = [const0, const0]
        out["layers"][-1]["truth_tables"][i] = [0, 0, 0, 0]
    return out


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--init-circuit", type=Path, default=DEFAULT_START)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--state-cap", type=int, default=None)
    parser.add_argument("--conf-bits", type=int, default=None)
    parser.add_argument("--flop-weight", type=float, default=1.)
    parser.add_argument("--accuracy-tolerance", type=float, default=.05)
    parser.add_argument("--generations", type=int, default=300)
    parser.add_argument("--repair-fraction", type=float, default=.5,
                        help="at most this share of generations is spent repairing accuracy under the cap")
    parser.add_argument("--population", type=int, default=96)
    parser.add_argument("--search-rays", type=int, default=2048)
    parser.add_argument("--tie-break", choices=("loss", "ratio"), default="loss",
                        help="order of equal-estimate mutants: raw loss (as the trainer) or loss relative to the anchor")
    parser.add_argument("--anchor-member", type=int, default=1, help="member 1 of each kind is the anchor (as the trainer)")
    parser.add_argument("--mae-check", type=int, default=1, help="also require MAE within tolerance in the recheck")
    parser.add_argument("--check-rays", type=int, default=8192,
                        help="fresh pixels per split for the accept check (a 2,048-ray check let error drift)")
    parser.add_argument("--synth-candidates", type=int, default=3)
    parser.add_argument("--validate-every", type=int, default=20)
    parser.add_argument("--police-search-weight", type=float, default=4.)
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

    def log(row):
        row["elapsed_seconds"] = round(time.monotonic() - started, 1)
        with log_path.open("a") as handle:
            handle.write(json.dumps(row) + "\n")
        print(row, flush=True)

    data = load_data()
    train, routing, validation, police, _ = data
    train_clean = train
    validator = Validator(train_clean, validation, CONDITIONS, 3, police)
    generator = torch.Generator().manual_seed(args.seed)
    area_model = AreaModel(MODEL_PATH)
    set_search_compile(None if args.compile_search == "none" else args.compile_search)

    anchor = load_circuit(args.init_circuit)
    anchor_config = StreamConfig(**anchor["config"])
    anchor_packed = pack_circuit(anchor)
    start = copy.deepcopy(anchor)
    if args.conf_bits is not None and args.conf_bits != anchor_config.conf_bits:
        allow_small_counter()
        start["config"]["conf_bits"] = args.conf_bits
    config = StreamConfig(**start["config"])
    base_bits = len(input_names(config))
    const0 = input_names(config).index("const0")
    cap = config.state_bits if args.state_cap is None else args.state_cap

    def batch(split, rays=None):
        pick = torch.randint(len(split[1]), (rays or args.search_rays,), generator=generator)
        photons = sample_conditions(split[0][pick], *CONDITIONS, generator)[0]
        return photons, split[1][pick], police.evidence(photons)

    def losses_of(cfg, inputs, codes, data_):
        return population_losses(cfg, inputs, codes, data_, police, args.police_search_weight)

    def anchor_loss(data_):
        return float(losses_of(anchor_config, anchor_packed[0][None], anchor_packed[1][None], data_)[0])

    def model_terms(inputs, codes):
        # Live state bits and flip-flops from structural liveness (matches synthesized flop counts on
        # 10 of 11 reference circuits; the area model's activity probe misses some counter reads).
        estimate = area_model.estimate(config, inputs, codes)
        found = [structure(unpack_circuit(start, i, c)) for i, c in zip(inputs, codes)]
        live = torch.tensor([len(f["live_state_bits"]) for f in found], dtype=torch.float32)
        flops = torch.tensor([f["expected_flops"] for f in found], dtype=torch.float32)
        return estimate + (args.flop_weight - 1)*FLOP_CELL_AREA*flops, live

    # ---- choose which state bits to remove for the cap (train split only)
    forced = []
    cap_batch = None
    while True:
        inputs, codes = pack_circuit(kill_state(start, forced))
        _, live = model_terms(inputs[None], codes[None])
        if int(live[0]) <= cap:
            break
        options = [i for i in range(config.state_bits) if i not in forced]
        trial = [pack_circuit(kill_state(start, forced + [i])) for i in options]
        cap_batch = cap_batch or batch(train, args.check_rays)
        trial_loss = losses_of(config, torch.stack([t[0] for t in trial]), torch.stack([t[1] for t in trial]), cap_batch)
        forced.append(options[int(trial_loss.argmin())])
    start = kill_state(start, forced)
    log({"phase": "setup", "forced_state_bits": forced, "state_cap": cap, "conf_bits": config.conf_bits,
         "flop_weight": args.flop_weight})

    synthesized = {}

    def real(circuits):
        out = []
        for c in circuits:
            key = json.dumps([c["config"]["conf_bits"], c["layers"]], separators=(",", ":"))
            if key not in synthesized:
                s = synth_circuit(c)
                synthesized[key] = (s["area"], s["flops"])
            out.append(synthesized[key])
        return out

    weighted = lambda area, flops: area + (args.flop_weight - 1)*FLOP_CELL_AREA*flops
    anchor_mae = validator(anchor)["mae_m"]
    limit_mae = anchor_mae*(1 + args.accuracy_tolerance)
    run = {"chosen": None, "best_mae": None}

    def consider(circuit, row):
        mae = validator(circuit)["mae_m"]
        area, flops = real([circuit])[0]
        w = weighted(area, flops)
        if mae <= limit_mae and (run["chosen"] is None or (w, mae) < (run["chosen"][1], run["chosen"][2])):
            run["chosen"] = (circuit, w, mae)
        if run["best_mae"] is None or mae < run["best_mae"][2]:
            run["best_mae"] = (circuit, w, mae)
        if "generation" in row:
            (args.out/"trace").mkdir(exist_ok=True)
            (args.out/"trace"/f"gen{row['generation']:04d}.json").write_text(json.dumps(circuit) + "\n")
        log({**row, "validation_mae_m": mae, "area_um2": area, "flops": flops, "weighted_area": round(w, 4),
             "within_tolerance": mae <= limit_mae})

    consider(start, {"phase": "start"})
    current = pack_circuit(start)
    current_area, current_flops = real([start])[0]
    third = max(args.population//3, 3)

    def enforce(inputs, codes):
        for i in forced:
            codes[:, -1, i] = 0
            inputs[:, -1, i] = const0
        return inputs, codes

    def mean_abs(cfg, inputs, codes, data_):
        """Mean absolute range error in bins after each circuit's own median offset."""
        photons, targets, _ = data_
        error = simulate_population_packed(cfg, inputs, codes, photons).float() - targets[None]
        return (error - error.median(-1, keepdim=True).values).abs().mean(-1)

    def passes(choice, tolerance):
        """Within `tolerance` of the anchor on fresh pixels from both design splits, both in the search
        loss (Huber + police) and in mean absolute error: the loss alone let validation MAE drift."""
        for split in (train, routing):
            data_ = batch(split, args.check_rays)
            mine = float(losses_of(config, choice[0][None], choice[1][None], data_)[0])
            if mine > anchor_loss(data_)*(1 + tolerance):
                return False
            if not args.mae_check:
                continue
            mine = float(mean_abs(config, choice[0][None], choice[1][None], data_)[0])
            if mine > float(mean_abs(anchor_config, anchor_packed[0][None], anchor_packed[1][None], data_)[0])*(1 + tolerance):
                return False
        return True

    def beats(choice, reference):
        for split in (train, routing):
            pair = losses_of(config, torch.stack((reference[0], choice[0])), torch.stack((reference[1], choice[1])),
                             batch(split, args.check_rays))
            if pair[1] > pair[0]:
                return False
        return True

    # Repair ends when the circuit is as good as the anchor on fresh pixels (no tolerance), or when
    # the repair budget is spent; the area phase then keeps every step within the tolerance.
    repair_budget = int(args.repair_fraction*args.generations)
    # Nothing to repair when the start is the anchor itself (no draws, so the random stream matches the trainer).
    repaired = (not forced and config == anchor_config) or passes(current, 0.)
    log({"phase": "mode", "generation": 0, "repaired": repaired})
    for generation in range(1, args.generations + 1):
        candidates = []
        for kind, split in (("table", train), ("wire", routing), ("prune", train)):
            inputs, codes = enforce(*mutate(*current, third, kind, base_bits, generator))
            inputs[0], codes[0] = current
            if args.anchor_member:     # as the trainer: member 1 holds the anchor and is never a candidate
                inputs[1], codes[1] = anchor_packed
            data_ = batch(split)
            losses = losses_of(config, inputs, codes, data_)
            reference = anchor_loss(data_)
            estimate, live = model_terms(inputs, codes)
            ok = live <= cap
            ok[0] = False
            if args.anchor_member:
                ok[1] = False
            if repaired:
                ok &= losses <= reference*(1 + args.accuracy_tolerance)
            else:
                ok &= losses < losses[0]
            for i in torch.nonzero(ok).flatten().tolist():
                ratio = float(losses[i]/reference)
                candidates.append((float(estimate[i]), float(losses[i]) if args.tie_break == "loss" else ratio,
                                   inputs[i], codes[i], ratio))
        if not repaired and generation > repair_budget:
            repaired = True
            current_area, current_flops = real([unpack_circuit(start, *current)])[0]
            log({"phase": "mode", "generation": generation, "repaired": "budget spent"})
        if not repaired:
            candidates.sort(key=lambda x: x[4])
            if candidates and beats((candidates[0][2], candidates[0][3]), current):
                current = (candidates[0][2], candidates[0][3])
                if passes(current, 0.):
                    repaired = True
                    current_area, current_flops = real([unpack_circuit(start, *current)])[0]
                    log({"phase": "mode", "generation": generation, "repaired": True})
        elif candidates:
            candidates.sort(key=lambda x: (x[0], x[1]))
            shortlist = candidates[:args.synth_candidates]
            found = real([unpack_circuit(start, x[2], x[3]) for x in shortlist])
            order = sorted(range(len(shortlist)), key=lambda i: (weighted(*found[i]), shortlist[i][1]))
            for i in order:
                if weighted(*found[i]) > weighted(current_area, current_flops):
                    break
                if passes((shortlist[i][2], shortlist[i][3]), args.accuracy_tolerance):
                    current = (shortlist[i][2], shortlist[i][3])
                    current_area, current_flops = found[i]
                    break
        if generation % args.validate_every == 0 or generation == args.generations:
            consider(unpack_circuit(start, *current), {"phase": "repair" if not repaired else "area",
                                                       "generation": generation, "search_area_um2": current_area,
                                                       "search_flops": current_flops})

    final_validator = Validator(train_clean, validation, CONDITIONS, 3, police, seed=1234)
    summary = {"arguments": {k: str(v) if isinstance(v, Path) else v for k, v in vars(args).items()},
               "forced_state_bits": forced, "anchor_validation_mae_m": anchor_mae, "limit_mae_m": limit_mae,
               "repaired": repaired, "seconds": round(time.monotonic() - started, 1)}
    picks = {"best_mae": run["best_mae"][0]}
    if run["chosen"] is not None:
        picks["chosen"] = run["chosen"][0]
    for label, circuit in picks.items():
        s = synth_circuit(circuit)
        summary[label] = {"audit": short_audit(final_validator.audit(circuit)), "synth": s,
                          "weighted_area": weighted(s["area"], s["flops"]), "parity_mismatches": parity(circuit),
                          "selection_mae_m": validator(circuit)["mae_m"]}
        (args.out/f"{label}_circuit.json").write_text(json.dumps(circuit) + "\n")
    (args.out/"circuit.json").write_text(json.dumps(picks.get("chosen", picks["best_mae"])) + "\n")
    (args.out/"summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    print(json.dumps({k: summary[k] for k in summary if k != "arguments"}, indent=1), flush=True)


if __name__ == "__main__":
    main()
