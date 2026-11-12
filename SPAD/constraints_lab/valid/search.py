"""Hard search with a valid-bit term (copy of the search loops in spad/training/train_stream.py).

Valid-bit measure D: detection rate on real-return pixels of the best no-new-logic readout
(confidence >= k for k = 1..15, or a state bit or its inverse) whose false-alarm rate on
background-only pixels is within --fa-limit. Background-only pixels for scoring mutants are built
from the same design split as the real pixels: half uniform over the 672 bins, half drawn from the
split's per-capture return-removed profiles (constraints_lab/valid/background.py). Selection uses
the validation split (its own uniform and residual backgrounds; the false-alarm limit must hold on
both).

--objective accuracy: per generation, table and wire mutants; keep the best score
    range Huber loss + police + search_area_weight * estimated area + valid_weight * (1 - D).
    Selection on validation: highest D_val among circuits whose validation MAE is within
    --accuracy-tolerance of the start.
--objective area: smallest real (Yosys) area such that the range loss stays within
    --accuracy-tolerance of the anchor and the valid penalty (1 - D) is no more than the anchor's
    plus --valid-slack (on the search pixels and again on fresh pixels from both design splits).
    Selection: smallest area with validation MAE within tolerance and D_val >= anchor D_val - slack.
"""
import argparse
from dataclasses import asdict
import json
from pathlib import Path
import time

import torch

from spad import ROOT
from spad.core.stream_model import StreamConfig, input_names, pack_circuit, unpack_circuit
from spad.dataset.photons import load_rays, sample_conditions
from spad.hardware.area_model import MODEL_PATH, AreaModel
from spad.training.baselines import BIN_METERS, metrics
from spad.training.police import Police, measure_pulse
from spad.training.train_stream import Validator, mutate

from constraints_lab.valid.background import (capture_groups, capture_groups_clean, residual_profiles,
                                              residual_streams, uniform_streams)
from constraints_lab.valid.common import run_full
from constraints_lab.valid.sim import simulate_population_full

LEVELS = torch.arange(1, 16)


def readout_names(state_bits):
    return [f"conf>={k}" for k in LEVELS.tolist()] + [f"{p}state{i}" for i in range(state_bits) for p in ("", "~")]


def readout_matrix(conf, state):
    """[..., rays] confidence and [..., rays, S] state -> booleans [..., readouts, rays]."""
    c = conf[..., None, :] >= LEVELS.to(conf.device)[:, None]
    s = state.transpose(-1, -2) == 1                                  # [..., S, rays]
    pairs = torch.stack((s, ~s), -2).flatten(-3, -2)                  # state0, ~state0, state1, ...
    return torch.cat((c, pairs), -2)


def detection_at_limit(det, fa, limit):
    """Detection at the false-alarm limit, [..., readouts] -> [...]: (hard, smooth).

    hard: best single readout whose false-alarm rate is within the limit.
    smooth: the same, but the confidence ROC (thresholds k = 1..15, plus "never") is linearly
    interpolated to exactly the limit, so the score does not jump when one threshold crosses it.
    Used to score and select; reports always give the hard number as well.
    """
    ok = fa <= limit
    hard = torch.where(ok, det, torch.zeros_like(det)).max(-1).values
    n = len(LEVELS)
    zero = torch.zeros_like(det[..., :1])
    d = torch.cat((det[..., :n], zero), -1)
    f = torch.cat((fa[..., :n], zero), -1)
    d_hi, d_lo, f_hi, f_lo = d[..., :-1], d[..., 1:], f[..., :-1], f[..., 1:]
    frac = ((limit - f_lo) / (f_hi - f_lo).clamp_min(1e-12)).clamp(0, 1)
    value = torch.where(f_lo <= limit, d_lo + (d_hi - d_lo) * frac, torch.zeros_like(d_lo))
    smooth = torch.maximum(value.max(-1).values, hard)
    return hard, smooth


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data", type=Path, default=ROOT/"data")
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--init-circuit", type=Path, required=True)
    parser.add_argument("--objective", choices=("accuracy", "area"), default="accuracy")
    parser.add_argument("--valid-weight", type=float, default=4., help="loss (bins) per unit of missed detection")
    parser.add_argument("--fa-limit", type=float, default=.01)
    parser.add_argument("--valid-slack", type=float, default=.02,
                        help="area objective: allowed drop in detection at the false-alarm limit")
    parser.add_argument("--anchor-circuit", type=Path, default=None,
                        help="area objective: circuit whose error and valid score set the limits (default: start)")
    parser.add_argument("--accuracy-tolerance", type=float, default=.05)
    parser.add_argument("--synth-candidates", type=int, default=3)
    parser.add_argument("--synth-workers", type=int, default=1)
    parser.add_argument("--police-search-weight", type=float, default=4.)
    parser.add_argument("--search-area-weight", type=float, default=.05)
    parser.add_argument("--generations", type=int, default=300)
    parser.add_argument("--population", type=int, default=128)
    parser.add_argument("--search-rays", type=int, default=2048)
    parser.add_argument("--background-rays", type=int, default=2048)
    parser.add_argument("--validate-every", type=int, default=20)
    parser.add_argument("--range-tolerance", type=float, default=None,
                        help="accuracy objective: reject mutants whose range loss exceeds the start's by this fraction")
    parser.add_argument("--residual-min-bin", type=int, default=0,
                        help="drop bins below this from the design-split residual profiles (48: residual_far)")
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--threads", type=int, default=1)
    args = parser.parse_args()
    torch.set_num_threads(args.threads)
    torch.manual_seed(args.seed)
    args.out.mkdir(parents=True, exist_ok=True)
    log_path = args.out/"history.jsonl"
    log_path.write_text("")
    conditions = (16, 256, .6)
    train = load_rays(args.data, "train", clean_only=True)[:2]
    routing = load_rays(args.data, "architecture", clean_only=True)[:2]
    validation = load_rays(args.data, "validation")[:2]
    profiles = {"train": residual_profiles(*train, capture_groups_clean(args.data, "train"), min_bin=args.residual_min_bin),
                "architecture": residual_profiles(*routing, capture_groups_clean(args.data, "architecture"),
                                                  min_bin=args.residual_min_bin)}
    groups = {"train": capture_groups_clean(args.data, "train"), "architecture": capture_groups_clean(args.data, "architecture")}
    pulse, zero = measure_pulse(train[0])
    police = Police(pulse, zero)
    validator = Validator(train, validation, conditions, 3, police)
    generator = torch.Generator().manual_seed(args.seed)
    # Validation backgrounds for selection: two sets each (22,020 rays per kind).
    vgen = torch.Generator().manual_seed(4321 + 17)
    vgroups = capture_groups(args.data, "validation")
    vprof = residual_profiles(*validation, vgroups, min_bin=args.residual_min_bin)
    val_bg = {"uniform": torch.cat([uniform_streams(len(vgroups), generator=vgen)[0] for _ in range(2)]),
              "residual": torch.cat([residual_streams(vprof, vgroups, generator=vgen)[0] for _ in range(2)])}

    template = json.loads(args.init_circuit.read_text())
    config = StreamConfig(**template["config"])
    base_bits = len(input_names(config))
    names = readout_names(config.state_bits)
    area_model = AreaModel(MODEL_PATH, "cpu")
    synthesized = {}

    def real_area(circuit):
        from spad.hardware.synth import synthesize
        from spad.hardware.verilog import stream_verilog
        key = json.dumps(circuit["layers"], separators=(",", ":"))
        if key not in synthesized:
            synthesized[key] = synthesize(stream_verilog(circuit), "photon_core", args.data)["area"] or 0.
        return synthesized[key]

    def batch(split, name):
        pick = torch.randint(len(split[1]), (args.search_rays,), generator=generator)
        photons = sample_conditions(split[0][pick], *conditions, generator)[0]
        half = args.background_rays // 2
        u = uniform_streams(half, generator=generator)[0]
        gpick = groups[name][torch.randint(len(groups[name]), (args.background_rays - half,), generator=generator)]
        r = residual_streams(profiles[name], gpick, generator=generator)[0]
        return torch.cat((photons, u, r)), split[1][pick], police.evidence(photons)

    def scores(inputs, codes, data):
        """Per member: (range loss incl. police, valid penalty 1 - D, readout index)."""
        photons, targets, evidence = data
        n = len(targets)
        cand, conf, state = simulate_population_full(config, inputs, codes, photons)
        prediction = cand[:, :n].float()
        error = prediction - targets[None]
        error = error - error.median(-1, keepdim=True).values
        loss = torch.nn.functional.huber_loss(error, torch.zeros_like(error), delta=4., reduction="none").mean(-1)
        loss = loss + args.police_search_weight*police.violations(prediction, evidence)["physics"].float().mean(-1)
        bits = readout_matrix(conf, state)
        half = n + args.background_rays // 2
        # The false-alarm limit must hold on uniform and on residual background separately.
        fa = torch.maximum(bits[..., n:half].float().mean(-1), bits[..., half:].float().mean(-1))
        det = bits[..., :n].float().mean(-1)
        _, smooth = detection_at_limit(det, fa, args.fa_limit)
        return loss, 1 - smooth, None

    def validate(circuit):
        cand, conf, state = run_full(circuit, validator.photons)
        offset = validator.offset(circuit)
        m = metrics(cand.float() - offset, validator.targets)
        real = readout_matrix(conf, state)
        fa = torch.zeros(len(names))
        for p in val_bg.values():
            _, c2, s2 = run_full(circuit, p)
            fa = torch.maximum(fa, readout_matrix(c2, s2).float().mean(-1))
        det = real.float().mean(-1)
        ok = fa <= args.fa_limit
        best = int(torch.where(ok, det, torch.zeros_like(det)).argmax())
        hard, smooth = detection_at_limit(det, fa, args.fa_limit)
        return {"mae_m": m["mae_m"], "recall_3": m["recall_3_bins"], "valid_detect": float(smooth),
                "valid_detect_hard": float(hard), "readout": names[best] if ok[best] else None,
                "readout_fa": float(fa[best]) if ok[best] else None}

    started = time.monotonic()

    def log(row):
        row["elapsed_seconds"] = round(time.monotonic() - started, 1)
        with log_path.open("a") as handle:
            handle.write(json.dumps(row)+"\n")
        print({k: v for k, v in row.items() if k != "circuit"}, flush=True)

    anchor_circuit = json.loads(args.anchor_circuit.read_text()) if args.anchor_circuit else template
    anchor = pack_circuit(anchor_circuit)
    current = pack_circuit(template)
    start_val = validate(template)
    anchor_val = validate(anchor_circuit) if args.anchor_circuit else start_val
    start_area = real_area(template)
    best = {"circuit": template, "val": start_val, "area": start_area,
            "score": start_val["mae_m"]/BIN_METERS + args.valid_weight*(1 - start_val["valid_detect"])}
    log({"phase": "start", **start_val, "area_um2": start_area, "anchor": anchor_val, "circuit": template})
    current_area = start_area

    third = max(args.population//3, 3)
    half = max(args.population//2, 2)
    accepted, last = 0, {}
    for generation in range(1, args.generations + 1):
        if args.objective == "accuracy":
            options = []
            for kind, split, name in (("table", train, "train"), ("wire", routing, "architecture")):
                inputs, codes = mutate(*current, half, kind, base_bits, generator)
                inputs[0], codes[0] = current
                if args.range_tolerance is not None:
                    inputs[1], codes[1] = anchor
                loss, penalty, _ = scores(inputs, codes, batch(split, name))
                total = loss + args.valid_weight*penalty + args.search_area_weight*area_model.estimate(config, inputs, codes)
                if args.range_tolerance is not None:
                    # Hard limit: range loss within tolerance of the start circuit on the same pixels.
                    total = torch.where(loss <= loss[1]*(1 + args.range_tolerance), total, torch.full_like(total, float("inf")))
                delta = total - total[0]
                delta[:2 if args.range_tolerance is not None else 1] = float("inf")
                i = int(delta.argmin())
                options.append((float(delta[i]), (inputs[i], codes[i])))
            delta, member = min(options, key=lambda x: x[0])
            if delta <= 0:
                # Winner's curse: the best of many mutants on one sample is often lucky, so it must
                # also score no worse than the current circuit on fresh pixels from both design splits.
                ok = True
                for split, name in ((train, "train"), (routing, "architecture")):
                    pair = (torch.stack((current[0], member[0], anchor[0])), torch.stack((current[1], member[1], anchor[1])))
                    loss, penalty, _ = scores(*pair, batch(split, name))
                    total = loss + args.valid_weight*penalty + args.search_area_weight*area_model.estimate(config, *pair)
                    last = {"range_loss": loss.tolist(), "valid_penalty": penalty.tolist()}
                    if total[1] > total[0] or (args.range_tolerance is not None
                                               and loss[1] > loss[2]*(1 + args.range_tolerance)):
                        ok = False
                        break
                if ok:
                    current = member
                    accepted += 1
        else:
            candidates = []
            for kind, split, name in (("table", train, "train"), ("wire", routing, "architecture"), ("prune", train, "train")):
                inputs, codes = mutate(*current, third, kind, base_bits, generator)
                inputs[0], codes[0] = current
                inputs[1], codes[1] = anchor
                loss, penalty, _ = scores(inputs, codes, batch(split, name))
                estimate = area_model.estimate(config, inputs, codes)
                feasible = (loss <= loss[1]*(1 + args.accuracy_tolerance)) & (penalty <= penalty[1] + args.valid_slack)
                feasible[:2] = False
                for i in torch.nonzero(feasible).flatten().tolist():
                    candidates.append((float(estimate[i]), float(loss[i]), inputs[i], codes[i]))
            candidates.sort(key=lambda x: (x[0], x[1]))

            def holds_up(choice):
                for split, name in ((train, "train"), (routing, "architecture")):
                    pair = (torch.stack((anchor[0], choice[0])), torch.stack((anchor[1], choice[1])))
                    loss, penalty, _ = scores(*pair, batch(split, name))
                    if loss[1] > loss[0]*(1 + args.accuracy_tolerance) or penalty[1] > penalty[0] + args.valid_slack:
                        return False
                return True

            shortlist = candidates[:args.synth_candidates]
            areas = [real_area(unpack_circuit(template, x[2], x[3])) for x in shortlist]
            for i in sorted(range(len(shortlist)), key=lambda i: (areas[i], shortlist[i][1])):
                if areas[i] > current_area:
                    break
                if holds_up((shortlist[i][2], shortlist[i][3])):
                    current, current_area = (shortlist[i][2], shortlist[i][3]), areas[i]
                    break
        if generation % args.validate_every == 0 or generation == args.generations:
            circuit = unpack_circuit(template, *current)
            val = validate(circuit)
            area = real_area(circuit) if args.objective == "accuracy" else current_area
            if args.objective == "accuracy":
                # Best valid bit among circuits whose validation MAE stays within tolerance of the start.
                if (val["mae_m"] <= start_val["mae_m"]*(1 + args.accuracy_tolerance)
                        and (val["valid_detect"], -val["mae_m"]) > (best["val"]["valid_detect"], -best["val"]["mae_m"])):
                    best = {"circuit": circuit, "val": val, "area": area, "score": None}
            else:
                allowed = (val["mae_m"] <= anchor_val["mae_m"]*(1 + args.accuracy_tolerance)
                           and val["valid_detect"] >= anchor_val["valid_detect"] - args.valid_slack)
                if allowed and area <= best["area"]:
                    best = {"circuit": circuit, "val": val, "area": area, "score": None}
            log({"phase": "hard", "generation": generation, **val, "accepted": accepted, "last_check": last, "area_um2": area,
                 "best_area_um2": best["area"], "best_mae_m": best["val"]["mae_m"],
                 "best_valid_detect": best["val"]["valid_detect"], "circuit": circuit})
    circuit = dict(best["circuit"])
    circuit["offset_bins"] = validator.offset(circuit)
    circuit["valid_readout"] = best["val"]["readout"]
    (args.out/"circuit.json").write_text(json.dumps(circuit)+"\n")
    summary = {"arguments": {k: str(v) if isinstance(v, Path) else v for k, v in vars(args).items()},
               "start": {**start_val, "area_um2": start_area}, "anchor": anchor_val,
               "selected": {**best["val"], "area_um2": best["area"]}, "seconds": time.monotonic() - started}
    (args.out/"summary.json").write_text(json.dumps(summary, indent=1)+"\n")
    print(json.dumps(summary["selected"]), flush=True)


if __name__ == "__main__":
    main()
