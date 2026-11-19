"""Search a streaming controller: bilevel DARTS, then batched hard search.

Truth tables train on the train split and routing on the architecture split.
Checkpoints are chosen on the validation split. Test splits are never loaded.
Hard search optimizes the exact discrete circuit that gradients only approximate.
Runs resume from state.pt, so a job can stop at --max-seconds and continue later.

Every sample draws its own photon count and extra-ambient level, so the circuit
cannot tune itself to one exposure. The physics police (police.py, training only)
penalizes ranges the photons themselves do not support; it never sees labels.
Its violation rate and a time-shift test are reported as audits, not used for
checkpoint selection.

--objective area turns the search toward the smallest chip: every circuit's whole-core
area is estimated with spad/hardware/area_model.py (fitted to Yosys + ASAP7 synthesis,
including the datapath parts synthesis removes when nothing reads them), and the search
keeps the smallest circuit whose error stays within --accuracy-tolerance of the circuit
it started from. Start it from a trained circuit with --init circuit --init-circuit PATH.
"""
import argparse
from dataclasses import asdict
import json
import os
from pathlib import Path
import sys
import time

import torch

from spad.training.baselines import metrics
from spad import ROOT
from spad.dataset.photons import load_rays, sample_conditions
from spad.training.police import Police, measure_pulse
from spad.hardware.area_model import MODEL_PATH, AreaModel
from spad.core.stream_model import (StreamConfig, StreamCore, input_names, pack_circuit, rule_circuit,
                          set_search_compile, simulate_population_packed, simulate_stream, unpack_circuit)


def range_loss(prediction, target, delta=4.):
    return torch.nn.functional.huber_loss(prediction, target, delta=delta)


def expected_area(model, costs):
    device = model.layers[0].routes.device
    tables = torch.tensor([[float((code >> i) & 1) for i in range(4)] for code in range(16)], device=device)
    areas = torch.tensor([x["area"] for x in costs], device=device)
    total = 0.
    for layer in model.layers:
        truth = layer.table_logits.sigmoid()
        total = total + (torch.where(tables[None] > 0, truth[:, None], 1-truth[:, None]).prod(-1) @ areas).sum()
    return total


class Validator:
    """Scores circuits with a train-fitted offset on fixed photon samples under randomized conditions."""
    def __init__(self, train, validation, conditions, sets, police, seed=7):
        generator = torch.Generator(device=train[0].device).manual_seed(seed)
        pick = torch.randperm(len(train[1]), generator=generator, device=train[0].device)[:8000]
        self.fit_targets = train[1][pick]
        self.fit_photons = sample_conditions(train[0][pick], *conditions, generator)[0]
        draws = [sample_conditions(validation[0], *conditions, generator) for _ in range(sets)]
        self.photons, self.counts, self.background = (torch.cat(x) for x in zip(*draws))
        self.targets = validation[1].repeat(sets)
        self.police = police
        self.evidence = police.evidence(self.photons) if police else None

    def offset(self, circuit):
        return float((simulate_stream(circuit, self.fit_photons).float() - self.fit_targets).median())

    def __call__(self, circuit):
        prediction = simulate_stream(circuit, self.photons).float() - self.offset(circuit)
        return metrics(prediction, self.targets)

    def audit(self, circuit, shift=24):
        """Hidden-inspector report: never used to pick a circuit."""
        raw = simulate_stream(circuit, self.photons).float()
        prediction = raw - self.offset(circuit)
        report = {"overall": metrics(prediction, self.targets)}
        if self.police:
            flags = self.police.violations(raw, self.evidence)
            report["police_violation_rate"] = {k: float(v.float().mean()) for k, v in flags.items()}
        rows = {}
        for low, high in ((16, 32), (32, 64), (64, 128), (128, 257)):
            keep = (self.counts >= low) & (self.counts < high)
            rows[f"photons_{low}-{min(high, 256)}"] = keep
        for low, high in ((0, .2), (.2, .4), (.4, 1.01)):
            rows[f"extra_background_{low}-{min(high, 1)}"] = (self.background >= low) & (self.background < high)
        for name, keep in rows.items():
            if keep.any():
                row = metrics(prediction[keep], self.targets[keep])
                row["median_signed_bins"] = float((prediction[keep] - self.targets[keep]).median())
                if self.police:
                    row["police_violation_rate"] = float(flags["physics"][keep].float().mean())
                report[name] = row
        # A range estimator must move with the photons: delay every arrival by `shift`
        # bins and the answer should move by the same amount.
        latest = self.photons.max(1).values
        movable = (latest + shift < 672) & (latest >= 0)
        moved = torch.where(self.photons >= 0, self.photons + shift, self.photons)[movable]
        change = simulate_stream(circuit, moved).float() - raw[movable]
        report["time_shift_test"] = {"shift_bins": shift, "rays": int(movable.sum()),
                                     "moves_with_photons_within_1_bin": float(((change - shift).abs() <= 1).float().mean())}
        return report


def mutate(inputs, codes, count, kind, base_bits, generator):
    """Return `count` copies of a circuit, each with one or two random edits."""
    device = inputs.device
    inputs = inputs[None].repeat(count, 1, 1, 1)
    codes = codes[None].repeat(count, 1, 1)
    members = torch.arange(count, device=device)
    layers, width = codes.shape[1:]
    randint = lambda high, size=(count,): torch.randint(high, size, generator=generator, device=device)
    for edit in range(2):
        chosen = members if edit == 0 else members[torch.rand(count, generator=generator, device=device) < .3]
        n = len(chosen)
        layer, gate = randint(layers, (n,)), randint(width, (n,))
        if kind == "table":
            codes[chosen, layer, gate] ^= (1 << randint(4, (n,))).int()
        elif kind == "prune":
            # Remove logic: constant 0, or a plain wire from input a (code 12) or b (code 10).
            options = torch.tensor([0, 12, 10], device=device, dtype=codes.dtype)
            codes[chosen, layer, gate] = options[randint(3, (n,))]
        else:
            sources = base_bits + width*(layer > 0).long()
            pick = (torch.rand(n, generator=generator, device=device) * sources).long()
            inputs[chosen, layer, gate, randint(2, (n,))] = pick
    return inputs, codes


def population_losses(config, inputs, codes, data, police=None, police_weight=0.):
    """Huber loss after each member's own constant offset, plus police violations (no area)."""
    photons, targets, evidence = data
    prediction = simulate_population_packed(config, inputs, codes, photons).float()
    error = prediction - targets[None]
    error = error - error.median(-1, keepdim=True).values
    loss = torch.nn.functional.huber_loss(error, torch.zeros_like(error), delta=4., reduction="none").mean(-1)
    if police is not None and police_weight:
        loss = loss + police_weight*police.violations(prediction, evidence)["physics"].float().mean(-1)
    return loss


def population_scores(config, inputs, codes, data, areas, area_weight, police=None, police_weight=0., area_model=None):
    """Huber loss after each member's own constant offset, plus area and police violations.

    With an area model, area is the whole-core estimate in µm²; without, the old sum of
    controller truth-table areas.
    """
    if area_model is not None:
        return (population_losses(config, inputs, codes, data, police, police_weight)
                + area_weight*area_model.estimate(config, inputs, codes))
    photons, targets, evidence = data
    prediction = simulate_population_packed(config, inputs, codes, photons).float()
    error = prediction - targets[None]
    error = error - error.median(-1, keepdim=True).values
    loss = torch.nn.functional.huber_loss(error, torch.zeros_like(error), delta=4., reduction="none").mean(-1)
    if police is not None and police_weight:
        loss = loss + police_weight*police.violations(prediction, evidence)["physics"].float().mean(-1)
    return loss + area_weight*areas[codes.long()].sum((1, 2))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data", type=Path, default=ROOT/"data")
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--device", default="cpu")
    parser.add_argument("--init", choices=("random", "rule", "circuit"), default="random")
    parser.add_argument("--init-circuit", type=Path, help="circuit.json to start from (with --init circuit)")
    parser.add_argument("--objective", choices=("accuracy", "area"), default="accuracy",
                        help="area: smallest whole-core area within --accuracy-tolerance of the start")
    parser.add_argument("--synth-candidates", type=int, default=3,
                        help="area objective: smallest-estimated mutants synthesized with Yosys per generation; "
                             "a change is accepted only if real synthesis confirms it is smaller (0 = model only)")
    parser.add_argument("--synth-workers", type=int, default=3)
    parser.add_argument("--accuracy-tolerance", type=float, default=.05,
                        help="area objective: allowed relative increase in loss and validation MAE")
    parser.add_argument("--area-model", type=Path, default=MODEL_PATH,
                        help="fitted whole-core area model; 'none' falls back to controller gates only")
    parser.add_argument("--rule-window", type=int, default=8)
    parser.add_argument("--min-photons", type=int, default=16, help="Per-sample photon count is log-uniform in [min, max]")
    parser.add_argument("--max-photons", type=int, default=256)
    parser.add_argument("--max-background", type=float, default=.6,
                        help="Per-sample probability, uniform in [0, this], that a photon is replaced by ambient")
    parser.add_argument("--police-weight", type=float, default=1., help="Gradient hinge weight (bins); 0 disables")
    parser.add_argument("--police-search-weight", type=float, default=4.,
                        help="Hard-search penalty per unit violation rate; 0 disables")
    parser.add_argument("--state-bits", type=int, default=4)
    parser.add_argument("--width", type=int, default=16)
    parser.add_argument("--layers", type=int, default=3)
    parser.add_argument("--steps", type=int, default=1500)
    parser.add_argument("--batch-size", type=int, default=256)
    parser.add_argument("--weight-lr", type=float, default=0.01)
    parser.add_argument("--architecture-lr", type=float, default=0.01)
    parser.add_argument("--start-temperature", type=float, default=2.)
    parser.add_argument("--end-temperature", type=float, default=.15)
    parser.add_argument("--sharpness", type=float, default=4.)
    parser.add_argument("--area-weight", type=float, default=0.002,
                        help="gradient phase: loss per unit of controller gate area. Search: loss per µm² of "
                             "whole-core area when an area model is loaded")
    parser.add_argument("--search-area-weight", type=float, default=0.05,
                        help="accuracy objective search: loss (bins) per µm² of estimated whole-core area")
    parser.add_argument("--harden-after", type=float, default=0.3)
    parser.add_argument("--eval-every", type=int, default=100)
    parser.add_argument("--rollback-factor", type=float, default=1.25,
                        help="Restore the best gradient state when hard MAE exceeds best times this; 0 disables")
    parser.add_argument("--generations", type=int, default=1000)
    parser.add_argument("--population", type=int, default=128)
    parser.add_argument("--search-rays", type=int, default=1024)
    parser.add_argument("--validate-every", type=int, default=20)
    parser.add_argument("--photon-sets", type=int, default=3)
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--threads", type=int, default=2)
    parser.add_argument("--compile", choices=("none", "default", "reduce-overhead"), default="none",
                        help="torch.compile the per-photon gradient step; pick with bench_stream on the target device")
    parser.add_argument("--compile-search", choices=("none", "default", "reduce-overhead"), default="default",
                        help="torch.compile the exact search's per-photon step (identical results)")
    parser.add_argument("--resume", action="store_true", help="Continue from state.pt in --out if present")
    parser.add_argument("--max-seconds", type=float, default=0, help="Save and stop after this long (0 = no limit)")
    args = parser.parse_args()
    device = torch.device(args.device)
    torch.set_num_threads(args.threads)
    torch.manual_seed(args.seed)
    args.out.mkdir(parents=True, exist_ok=True)
    state_path, log_path = args.out/"state.pt", args.out/"history.jsonl"
    costs = json.loads((args.data/"asap7/costs.json").read_text())["truth_table_costs"]
    areas = torch.tensor([x["area"] for x in costs], device=device)
    train = [x.to(device) for x in load_rays(args.data, "train", clean_only=True)[:2]]
    routing = [x.to(device) for x in load_rays(args.data, "architecture", clean_only=True)[:2]]
    validation = [x.to(device) for x in load_rays(args.data, "validation")[:2]]
    conditions = (args.min_photons, args.max_photons, args.max_background)
    pulse, zero = measure_pulse(train[0].cpu())   # label-free return shape from training histograms
    police = Police(pulse, zero).to(device) if (args.police_weight or args.police_search_weight) else None
    validator = Validator(train, validation, conditions, args.photon_sets, Police(pulse, zero).to(device))
    generator = torch.Generator(device=device).manual_seed(args.seed)
    start_circuit = None
    if args.init == "circuit":
        start_circuit = json.loads(args.init_circuit.read_text())
        saved_config = start_circuit["config"]
        args.state_bits, args.width, args.layers = (saved_config[k] for k in ("state_bits", "width", "layers"))
    config = StreamConfig(state_bits=args.state_bits, width=args.width, layers=args.layers)
    area_model = None if str(args.area_model) == "none" else AreaModel(args.area_model, device)
    if args.objective == "area" and area_model is None:
        raise ValueError("The area objective needs an area model")
    synthesized_areas = {}

    def real_area(circuits):
        """Yosys + ASAP7 area of each circuit (cached), synthesized in parallel; None without Yosys."""
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

    confirm = args.objective == "area" and args.synth_candidates > 0
    if confirm:
        try:
            real_area([rule_circuit(config)])
        except Exception as error:
            print(f"Yosys not available ({type(error).__name__}); area decisions use the fitted model only", flush=True)
            confirm = False
    circuit_area = (lambda c: real_area([c])[0]) if confirm else (
        lambda c: area_model.circuit_area(c) if area_model is not None else None)
    model = StreamCore(config).to(device).set_compile(None if args.compile == "none" else args.compile)
    set_search_compile(None if args.compile_search == "none" else args.compile_search)
    if args.init == "rule":
        model.load_circuit(rule_circuit(config, args.rule_window), args.sharpness)
    elif start_circuit is not None:
        model.load_circuit(start_circuit, args.sharpness)
    weights, architecture = model.weight_parameters(), model.architecture_parameters()
    weight_optimizer = torch.optim.Adam(weights, lr=args.weight_lr)
    architecture_optimizer = torch.optim.Adam(architecture, lr=args.architecture_lr)
    snapshot = lambda: {k: v.detach().cpu().clone() for k, v in model.state_dict().items()}
    run = {"step": 0, "generation": 0, "best_circuit": model.circuit(), "best_mae": None,
           "search_circuit": None, "gradient_mae": None, "elapsed": 0., "best_model": snapshot(),
           "rollbacks": 0, "anchor_mae": None, "best_area": None}
    resumed = args.resume and state_path.exists()
    if resumed:
        saved = torch.load(state_path, map_location="cpu", weights_only=False)
        if saved["config"] != asdict(config) or saved.get("conditions") != list(conditions):
            raise ValueError("Saved state uses a different configuration or photon conditions")
        model.load_state_dict(saved["model"])
        weight_optimizer.load_state_dict(saved["weight_optimizer"])
        architecture_optimizer.load_state_dict(saved["architecture_optimizer"])
        generator.set_state(saved["generator"].cpu())
        run = saved["run"]
    else:
        log_path.write_text("")
    started = time.monotonic()
    elapsed = lambda: run["elapsed"] + time.monotonic() - started

    def log(row):
        row["elapsed_seconds"] = round(elapsed(), 1)
        with log_path.open("a") as handle:
            handle.write(json.dumps(row)+"\n")
        print(row, flush=True)

    def save():
        payload = {"config": asdict(config), "conditions": list(conditions), "model": model.state_dict(),
                   "weight_optimizer": weight_optimizer.state_dict(),
                   "architecture_optimizer": architecture_optimizer.state_dict(),
                   "generator": generator.get_state(), "run": {**run, "elapsed": elapsed()}}
        temporary = state_path.with_suffix(".tmp")
        torch.save(payload, temporary)
        os.replace(temporary, state_path)

    def out_of_time():
        if args.max_seconds and time.monotonic() - started > args.max_seconds:
            save()
            print(f"Paused at step {run['step']}, generation {run['generation']}; rerun with --resume", flush=True)
            sys.exit(0)

    def consider(circuit, row):
        mae = validator(circuit)["mae_m"]
        area = circuit_area(circuit)
        if args.objective == "area" and run["anchor_mae"] is not None:
            # Smallest circuit whose validation error stays within tolerance of the start.
            allowed = mae <= run["anchor_mae"]*(1 + args.accuracy_tolerance)
            if allowed and (area < run["best_area"] or (area == run["best_area"] and mae < run["best_mae"])):
                run["best_circuit"], run["best_mae"], run["best_area"] = circuit, mae, area
        elif run["best_mae"] is None or mae < run["best_mae"]:
            run["best_circuit"], run["best_mae"], run["best_area"] = circuit, mae, area
            if row["phase"] != "hard":
                run["best_model"] = snapshot()
        log({**row, "validation_mae_m": mae, "area_um2": area, "best": run["best_mae"],
             "best_area_um2": run["best_area"]})
        return mae

    if not resumed:
        consider(model.circuit(), {"phase": "start"})

    def step_on(split, optimizer, active, frozen, temperature, ste):
        for p in frozen:
            p.requires_grad_(False)
        for p in active:
            p.requires_grad_(True)
        pick = torch.randint(len(split[1]), (args.batch_size,), generator=generator, device=device)
        photons = sample_conditions(split[0][pick], *conditions, generator)[0]
        prediction = model(photons, temperature=temperature, ste=ste)
        loss = range_loss(prediction, split[1][pick])
        if police is not None and args.police_weight:
            loss = loss + args.police_weight*police.penalty(prediction, police.evidence(photons))
        loss = loss + args.area_weight*expected_area(model, costs)
        optimizer.zero_grad(set_to_none=True)
        loss.backward()
        norm = torch.nn.utils.clip_grad_norm_(active, 5.)
        if not (torch.isfinite(loss) and torch.isfinite(norm)):
            # One non-finite step turns every weight into NaN; skip it and count it.
            optimizer.zero_grad(set_to_none=True)
            run["skipped_steps"] = run.get("skipped_steps", 0) + 1
            return float("nan")
        optimizer.step()
        return float(loss.detach())

    while run["step"] < args.steps:
        step = run["step"]
        progress = step/max(args.steps-1, 1)
        temperature = args.start_temperature*(args.end_temperature/args.start_temperature)**progress
        ste = progress >= args.harden_after
        step_on(routing, architecture_optimizer, architecture, weights, temperature, ste)
        loss = step_on(train, weight_optimizer, weights, architecture, temperature, ste)
        run["step"] += 1
        if run["step"] % args.eval_every == 0 or run["step"] == args.steps:
            with torch.no_grad():
                sample = validator.photons[:2000]
                soft = metrics(model(sample, temperature=temperature), validator.targets[:2000])["mae_m"]
            mae = consider(model.circuit(), {"phase": "gradient", "step": run["step"], "loss": loss,
                                             "temperature": temperature, "straight_through": ste, "soft_mae_m": soft})
            broken = not all(torch.isfinite(p).all() for p in model.parameters())
            if broken or (ste and args.rollback_factor and mae > args.rollback_factor*run["best_mae"]):
                # Hardened search can fall off a cliff that gradients cannot climb back up.
                model.load_state_dict(run["best_model"])
                weight_optimizer.state.clear()
                architecture_optimizer.state.clear()
                run["rollbacks"] += 1
            save()
            out_of_time()
    if run["gradient_mae"] is None:
        run["gradient_mae"] = run["best_mae"]

    if args.generations:
        template = run["best_circuit"]
        current = pack_circuit(run["search_circuit"] or template, device)
        base_bits = len(input_names(config))
        half = max(args.population//2, 2)
        if args.objective == "area" and run["anchor_mae"] is None:
            run["anchor_mae"], run["best_area"] = run["best_mae"], circuit_area(template)
            run["anchor"] = template
            print(f"area objective: start at {run['best_area']:.2f} µm² "
                  f"({'synthesized' if confirm else 'estimated'}), validation MAE "
                  f"{run['anchor_mae']:.3f} m; keeping MAE within {args.accuracy_tolerance:.0%}", flush=True)
        anchor = pack_circuit(run.get("anchor") or template, device)
        third = max(args.population//3, 3)
        def batch(split):
            pick = torch.randint(len(split[1]), (args.search_rays,), generator=generator, device=device)
            photons = sample_conditions(split[0][pick], *conditions, generator)[0]
            return photons, split[1][pick], police.evidence(photons) if police is not None else None
        current_area = circuit_area(unpack_circuit(template, *current)) if args.objective == "area" else None
        while args.objective == "area" and run["generation"] < args.generations:
            # Each mutant kind is scored on its own pixels, always next to the start circuit (member 1),
            # so the error budget is measured on the same photons as the mutants.
            candidates = []
            for kind, split in (("table", train), ("wire", routing), ("prune", train)):
                inputs, codes = mutate(*current, third, kind, base_bits, generator)
                inputs[0], codes[0] = current
                inputs[1], codes[1] = anchor
                losses = population_losses(config, inputs, codes, batch(split), police, args.police_search_weight)
                estimate = area_model.estimate(config, inputs, codes)
                feasible = losses <= losses[1]*(1 + args.accuracy_tolerance)
                feasible[:2] = False
                for i in torch.nonzero(feasible).flatten().tolist():
                    candidates.append((float(estimate[i]), float(losses[i]), inputs[i], codes[i]))
            candidates.sort(key=lambda x: (x[0], x[1]))

            def holds_up(choice):
                # Picking the smallest of many mutants that passed on one sample favours ones that got
                # lucky on it, so the winner must also pass on fresh pixels from both design splits.
                for split in (train, routing):
                    pair = (torch.stack((anchor[0], choice[0])), torch.stack((anchor[1], choice[1])))
                    check = population_losses(config, *pair, batch(split), police, args.police_search_weight)
                    if check[1] > check[0]*(1 + args.accuracy_tolerance):
                        return False
                return True

            if candidates and confirm:
                # The fitted model proposes, real synthesis decides.
                shortlist = candidates[:args.synth_candidates]
                areas_real = real_area([unpack_circuit(template, x[2], x[3]) for x in shortlist])
                for i in sorted(range(len(shortlist)), key=lambda i: (areas_real[i], shortlist[i][1])):
                    if areas_real[i] > current_area:
                        break
                    if holds_up((shortlist[i][2], shortlist[i][3])):
                        current, current_area = (shortlist[i][2], shortlist[i][3]), areas_real[i]
                        break
            elif candidates and candidates[0][0] <= current_area and holds_up((candidates[0][2], candidates[0][3])):
                current, current_area = (candidates[0][2], candidates[0][3]), candidates[0][0]
            run["generation"] += 1
            run["search_circuit"] = unpack_circuit(template, *current)
            if run["generation"] % args.validate_every == 0 or run["generation"] == args.generations:
                consider(run["search_circuit"], {"phase": "hard", "generation": run["generation"],
                                                 "search_area_um2": current_area})
                save()
                out_of_time()
        while run["generation"] < args.generations:
            deltas, members = [], []
            for kind, split in (("table", train), ("wire", routing)):
                inputs, codes = mutate(*current, half, kind, base_bits, generator)
                inputs[0], codes[0] = current   # member 0 is the unmutated reference
                scores = population_scores(config, inputs, codes, batch(split), areas,
                                           args.search_area_weight if area_model is not None else args.area_weight,
                                           police, args.police_search_weight, area_model)
                delta = scores - scores[0]
                delta[0] = float("inf")
                best = int(delta.argmin())
                deltas.append(float(delta[best]))
                members.append((inputs[best], codes[best]))
            winner = 0 if deltas[0] <= deltas[1] else 1
            if deltas[winner] <= 0:
                current = members[winner]
            run["generation"] += 1
            run["search_circuit"] = unpack_circuit(template, *current)
            if run["generation"] % args.validate_every == 0 or run["generation"] == args.generations:
                consider(run["search_circuit"], {"phase": "hard", "generation": run["generation"]})
                save()
                out_of_time()

    circuit = dict(run["best_circuit"])
    circuit["offset_bins"] = validator.offset(circuit)
    circuit["budget"] = args.max_photons
    circuit["conditions"] = {"min_photons": args.min_photons, "max_photons": args.max_photons,
                             "max_background": args.max_background}
    fresh_validator = Validator(train, validation, conditions, args.photon_sets, validator.police, seed=1234)
    audit = fresh_validator.audit(circuit)
    report = audit["overall"]
    (args.out/"circuit.json").write_text(json.dumps(circuit)+"\n")
    summary = {"arguments": {k: str(v) if isinstance(v, Path) else v for k, v in vars(args).items()},
               "config": asdict(config), "gradient_best_validation_mae_m": run["gradient_mae"], "rollbacks": run["rollbacks"],
               "selection_validation_mae_m": run["best_mae"], "validation_fresh_photons": report,
               "skipped_nonfinite_steps": run.get("skipped_steps", 0),
               "objective": args.objective, "area_um2": run["best_area"],
               "start_area_um2": circuit_area(run["anchor"]) if run.get("anchor") else None,
               "area_source": "yosys" if confirm else "fitted model",
               "start_validation_mae_m": run["anchor_mae"],
               "audit_fresh_photons": audit, "pulse": pulse.tolist(), "seconds": elapsed()}
    try:   # real synthesized area when Yosys is installed (locally; usually not on Kaggle)
        from spad.hardware.synth import synthesize
        from spad.hardware.verilog import stream_verilog
        synthesized = synthesize(stream_verilog(circuit), "photon_core", args.data)
        summary["synthesized"] = {k: v for k, v in synthesized.items() if k != "report"}
    except Exception as error:
        summary["synthesized"] = f"not available: {type(error).__name__}"
    (args.out/"summary.json").write_text(json.dumps(summary, indent=2)+"\n")
    save()
    print(json.dumps(report), flush=True)


if __name__ == "__main__":
    main()
