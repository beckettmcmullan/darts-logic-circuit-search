"""Small first-order bilevel search, hardening, held-out evaluation and export."""
import argparse
from dataclasses import asdict
import json
from pathlib import Path
import random
import time

import numpy as np
import torch
from torch.nn import functional as F

from spad import ROOT
from spad.hardware.costs import core_cost
from spad.core.model import Config, RecurrentLogic, simulate_circuit
from spad.dataset.prepare import BIN_METERS


def load_split(root, name, max_rays=None):
    metadata = json.loads((root / "processed/metadata.json").read_text())
    histograms, targets = [], []
    for capture, info in metadata["captures"].items():
        if info["split"] != name:
            continue
        with np.load(root / "processed" / f"{capture}.npz") as data:
            histograms.append(data["histograms"])
            targets.append(data["target_bins"])
    if not histograms:
        raise ValueError(f"Empty split {name}")
    histograms, targets = np.concatenate(histograms), np.concatenate(targets)
    if max_rays and len(targets) > max_rays:
        indices = np.random.default_rng(42).choice(len(targets), max_rays, replace=False)
        histograms, targets = histograms[indices], targets[indices]
    return torch.from_numpy(histograms.astype(np.int32)), torch.from_numpy(targets)


def sample(split, batch_size, generator, device):
    indices = torch.randint(len(split[0]), (batch_size,), generator=generator)
    return tuple(x[indices].to(device) for x in split)


def depth_loss(scores, target):
    # Linear interpolation between neighboring bin labels avoids premature rounding.
    low = target.floor().long().clamp(0, scores.shape[-1]-1)
    high = (low+1).clamp(max=scores.shape[-1]-1)
    weight = target - low
    logp = scores.log_softmax(-1)
    return -((1-weight)*logp.gather(1, low[:, None]).squeeze(1)
             + weight*logp.gather(1, high[:, None]).squeeze(1)).mean()


def metrics(prediction, targets):
    error = (prediction.float() - targets).abs()
    return {"mae_m": float(error.mean()*BIN_METERS),
            "rmse_m": float(error.square().mean().sqrt()*BIN_METERS),
            "median_m": float(error.median()*BIN_METERS),
            **{f"recall_{n}_bins": float((error <= n).float().mean()) for n in (1, 3, 5)}}


@torch.no_grad()
def evaluate(model, split, device, batch_size, temperature=1.):
    soft, hard = [], []
    saturation, ties = 0, 0
    for start in range(0, len(split[0]), batch_size):
        hist = split[0][start:start+batch_size].to(device)
        soft_scores = model(hist, temperature=temperature)
        hard_scores = model(hist, hard=True)
        soft.append(soft_scores.argmax(-1).cpu())
        hard.append(hard_scores.argmax(-1).cpu())
        ties += int(((hard_scores == hard_scores.max(-1, keepdim=True).values).sum(-1) > 1).sum())
        saturation += int((hist > 2**model.config.count_bits-1).sum())
    targets = split[1]
    return {"rays": len(targets), "soft": metrics(torch.cat(soft), targets),
            "hard": metrics(torch.cat(hard), targets),
            "raw_peak_baseline": metrics(split[0].argmax(-1), targets),
            "encoded_peak_baseline": metrics(split[0].clamp(max=2**model.config.count_bits-1).argmax(-1), targets),
            "hard_max_score_tie_fraction": ties / len(targets),
            "saturated_bin_fraction": saturation / split[0].numel()}


def choose_device(requested):
    if requested != "auto":
        return torch.device(requested)
    if torch.cuda.is_available():
        return torch.device("cuda")
    if torch.backends.mps.is_available():
        return torch.device("mps")
    return torch.device("cpu")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data", type=Path, default=ROOT / "data")
    parser.add_argument("--out", type=Path, default=ROOT / "runs/search")
    parser.add_argument("--steps", type=int, default=200)
    parser.add_argument("--batch-size", type=int, default=8)
    parser.add_argument("--eval-rays", type=int, default=256)
    parser.add_argument("--eval-every", type=int, default=25)
    parser.add_argument("--device", choices=("cpu", "mps", "cuda", "auto"), default="cpu")
    parser.add_argument("--threads", type=int, default=2)
    parser.add_argument("--width", type=int, default=24)
    parser.add_argument("--state-bits", type=int, default=16)
    parser.add_argument("--score-bits", type=int, default=8)
    parser.add_argument("--count-bits", type=int, default=12)
    parser.add_argument("--layers", type=int, default=2)
    parser.add_argument("--truncation", type=int, default=32)
    parser.add_argument("--weight-lr", type=float, default=0.01)
    parser.add_argument("--architecture-lr", type=float, default=0.01)
    parser.add_argument("--area-weight", type=float, default=0.005)
    parser.add_argument("--delay-weight", type=float, default=0.005)
    parser.add_argument("--harden-after", type=float, default=0.75,
                        help="Fraction of search before straight-through Boolean forward passes; 1 disables")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--resume", type=Path)
    parser.add_argument("--evaluate", type=Path, help="Evaluate a checkpoint without updating it")
    args = parser.parse_args()
    if args.steps < 1 or min(args.batch_size, args.eval_rays, args.eval_every) < 1:
        raise ValueError("Steps, batch and evaluation sizes must be positive")
    if not 0 <= args.harden_after <= 1:
        raise ValueError("harden-after must be between 0 and 1")
    torch.set_num_threads(args.threads)
    torch.manual_seed(args.seed)
    np.random.seed(args.seed)
    random.seed(args.seed)
    device = choose_device(args.device)
    args.out.mkdir(parents=True, exist_ok=True)
    costs = json.loads((args.data / "asap7/costs.json").read_text())
    checkpoint = torch.load(args.evaluate or args.resume, map_location="cpu", weights_only=False) if (args.evaluate or args.resume) else None
    data_metadata = json.loads((args.data / "processed/metadata.json").read_text())
    if checkpoint:
        previous_metadata = checkpoint["data_metadata"]
        for key in ("dataset_revision", "calibration", "calibration_values", "bin_offset", "bin_meters"):
            if previous_metadata[key] != data_metadata[key]:
                raise ValueError(f"Checkpoint and current data disagree on {key}")
        if args.resume:
            for key in ("seed", "max_rays", "captures"):
                if previous_metadata[key] != data_metadata[key]:
                    raise ValueError(f"Resumed checkpoint uses a different prepared sample selection: {key}")
            if args.eval_rays != checkpoint["arguments"]["eval_rays"]:
                raise ValueError("Keep --eval-rays unchanged when resuming so best-checkpoint scores stay comparable")
    config = Config(**checkpoint["config"]) if checkpoint else Config(
        count_bits=args.count_bits, state_bits=args.state_bits, score_bits=args.score_bits,
        width=args.width, layers=args.layers, truncation=args.truncation)
    model = RecurrentLogic(config).to(device)
    if checkpoint:
        model.load_state_dict(checkpoint["model"])
    train = load_split(args.data, "train")
    architecture_validation = load_split(args.data, "architecture")
    validation = load_split(args.data, "validation", args.eval_rays)
    weights, architecture = model.weight_parameters(), model.architecture_parameters()
    weight_optimizer = torch.optim.Adam(weights, lr=args.weight_lr)
    architecture_optimizer = torch.optim.Adam(architecture, lr=args.architecture_lr)
    generator = torch.Generator().manual_seed(args.seed)
    with torch.no_grad():
        area_ref, delay_ref = core_cost(model, costs)
        area_ref, delay_ref = float(area_ref), float(delay_ref)
    start_step, best = 0, float("inf")
    if args.resume:
        weight_optimizer.load_state_dict(checkpoint["weight_optimizer"])
        architecture_optimizer.load_state_dict(checkpoint["architecture_optimizer"])
        generator.set_state(checkpoint["sample_rng"])
        start_step, best = checkpoint["step"], checkpoint["best_validation_mae_m"]
        area_ref, delay_ref = checkpoint["cost_normalizers"]
        if not (args.out / "best.pt").exists():
            previous_best = args.resume.parent / "best.pt"
            if not previous_best.exists():
                raise ValueError("Resume needs the sibling best.pt checkpoint to preserve validation selection")
            best_checkpoint = torch.load(previous_best, map_location="cpu", weights_only=False)
            torch.save(best_checkpoint, args.out / "best.pt")
    def save(path, step):
        torch.save({"config": asdict(config), "model": model.state_dict(), "step": step,
                    "weight_optimizer": weight_optimizer.state_dict(),
                    "architecture_optimizer": architecture_optimizer.state_dict(),
                    "sample_rng": generator.get_state(), "best_validation_mae_m": best,
                    "cost_normalizers": (area_ref, delay_ref),
                    "arguments": {k: str(v) if isinstance(v, Path) else v for k,v in vars(args).items()},
                    "data_metadata": data_metadata,
                    "library_costs": costs}, path)
    def objective(hist, target, temperature, ste):
        scores = model(hist, temperature=temperature, ste=ste)
        area, delay = core_cost(model, costs, temperature)
        logits = scores * (12. / (2**config.score_bits-1))
        return (depth_loss(logits, target) + args.area_weight*area/max(area_ref, 1e-12)
                + args.delay_weight*delay/max(delay_ref, 1e-12))
    log = args.out / "history.jsonl"
    started = time.monotonic()
    if not args.evaluate:
        for step in range(start_step, args.steps):
            progress = step / max(args.steps-1, 1)
            temperature = 2. * (0.15 / 2.) ** progress
            ste = progress >= args.harden_after and args.harden_after < 1.
            # First-order bilevel DARTS: validation updates alpha, train updates theta.
            for parameter in weights:
                parameter.requires_grad_(False)
            for parameter in architecture:
                parameter.requires_grad_(True)
            architecture_optimizer.zero_grad(set_to_none=True)
            val_loss = objective(*sample(architecture_validation, args.batch_size, generator, device), temperature, ste)
            val_loss.backward()
            torch.nn.utils.clip_grad_norm_(architecture, 1.)
            architecture_optimizer.step()
            for parameter in weights:
                parameter.requires_grad_(True)
            for parameter in architecture:
                parameter.requires_grad_(False)
            weight_optimizer.zero_grad(set_to_none=True)
            loss = objective(*sample(train, args.batch_size, generator, device), temperature, ste)
            loss.backward()
            torch.nn.utils.clip_grad_norm_(weights, 1.)
            weight_optimizer.step()
            for parameter in architecture:
                parameter.requires_grad_(True)
            if step == 0 or (step+1) % args.eval_every == 0 or step+1 == args.steps:
                report = evaluate(model, validation, device, args.batch_size, temperature)
                row = {"step": step+1, "train_objective": float(loss.detach()),
                       "validation_objective": float(val_loss.detach()), "temperature": temperature,
                       "straight_through": ste, "elapsed_seconds": time.monotonic()-started,
                       "validation": report}
                with log.open("a") as handle:
                    handle.write(json.dumps(row) + "\n")
                score = report["hard"]["mae_m"]
                if score < best:
                    best = score
                    save(args.out / "best.pt", step+1)
                save(args.out / "last.pt", step+1)
                print(f"step {step+1}: loss {float(loss.detach()):.4f}, "
                      f"val hard MAE {score:.3f} m, val peak MAE "
                      f"{report['raw_peak_baseline']['mae_m']:.3f} m", flush=True)
        best_path = args.out / "best.pt"
        selected = torch.load(best_path, map_location=device, weights_only=False)
        model.load_state_dict(selected["model"])
    else:
        selected = checkpoint
    if not args.evaluate:
        # Training never scores test rays; use --evaluate once a design is frozen.
        print(f"Selected step {selected['step']}; run --evaluate for held-out scores")
        return
    test = load_split(args.data, "test")
    result = evaluate(model, test, device, args.batch_size)
    with torch.no_grad():
        area, delay = core_cost(model, costs, hard=True)
    result.update({"device": str(device), "core_area_liberty_units": float(area),
                   "core_delay_proxy_ps": float(delay), "cost_limitations": costs["limitations"],
                   "protocol": "custom projected-ray metrics, not official point-cloud benchmark metrics",
                   "evaluation_scope": "all test rays",
                   "selected_checkpoint_step": selected["step"],
                   "best_validation_mae_m": selected["best_validation_mae_m"],
                   "data_revision": data_metadata["dataset_revision"],
                   "calibration_assumption": data_metadata["calibration_status"],
                   "convergence_claim": "none; inspect history and compare hard inference to baselines"})
    circuit = model.circuit()
    examples = test[0][:min(args.batch_size, len(test[0]))]
    if not torch.equal(simulate_circuit(circuit, examples), model(examples.to(device), hard=True).cpu().long()):
        raise RuntimeError("Exported integer circuit disagrees with hard PyTorch model")
    (args.out / "circuit.json").write_text(json.dumps(circuit, indent=2) + "\n")
    (args.out / "metrics.json").write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
