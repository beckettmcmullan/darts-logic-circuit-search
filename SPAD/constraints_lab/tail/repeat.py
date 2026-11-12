"""How repeatable are the tail measures? Full validation across photon draws, and 4,096-ray search batches.

Run from SPAD/:
  ../.venv/bin/python -m constraints_lab.slot -- ../.venv/bin/python -m constraints_lab.tail.repeat
"""
import argparse
import json

import torch

from spad.core.stream_model import StreamConfig, pack_circuit, simulate_population_packed
from spad.dataset.photons import sample_conditions
from spad.training.train_stream import Validator, simulate_stream

from constraints_lab.tail.common import CONDITIONS, OUT, REFERENCES, load_circuit, setup, tail_stats


def huber(error, delta=4.):
    return float(torch.nn.functional.huber_loss(error, torch.zeros_like(error), delta=delta))


def summarize(rows):
    keys = rows[0].keys()
    stack = {k: torch.tensor([r[k] for r in rows], dtype=torch.float64) for k in keys}
    return {k: {"mean": float(v.mean()), "sd": float(v.std()), "min": float(v.min()), "max": float(v.max())}
            for k, v in stack.items()}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--draws", type=int, default=8)
    parser.add_argument("--batches", type=int, default=30)
    parser.add_argument("--rays", type=int, default=4096)
    args = parser.parse_args()
    torch.set_num_threads(1)
    train, routing, validation, police = setup()
    circuits = {name: load_circuit(path) for name, path in REFERENCES.items()}
    names = list(circuits)
    result = {"validation_draws": {}, "search_batches": {}}

    # (a) Full validation, different photon draws (each a fresh Validator: its own fit photons too).
    per = {n: [] for n in names}
    for draw in range(args.draws):
        validator = Validator(train, validation[:2], CONDITIONS, 3, police, seed=1234 + draw)
        for name, circuit in circuits.items():
            prediction = simulate_stream(circuit, validator.photons).float() - validator.offset(circuit)
            per[name].append(tail_stats(prediction - validator.targets.float()))
    result["validation_draws"] = {n: summarize(per[n]) for n in names}
    result["validation_rays_per_draw"] = len(validator.targets)
    # Paired differences against the final design across draws.
    result["validation_draws_paired"] = {
        n: summarize([{k: a[k] - b[k] for k in a} for a, b in zip(per[n], per["final_design"])])
        for n in names if n != "final_design"}

    # (b) Search-sized batches: 4,096 rays from a design split, each circuit with its own batch median offset,
    #     exactly as population_losses scores mutants.
    config = StreamConfig(**circuits["final_design"]["config"])
    packed = [pack_circuit(c) for c in circuits.values()]
    inputs, codes = torch.stack([p[0] for p in packed]), torch.stack([p[1] for p in packed])
    generator = torch.Generator().manual_seed(99)
    for split_name, split in (("train", train), ("architecture", routing)):
        per = {n: [] for n in names}
        for _ in range(args.batches):
            pick = torch.randint(len(split[1]), (args.rays,), generator=generator)
            photons = sample_conditions(split[0][pick], *CONDITIONS, generator)[0]
            prediction = simulate_population_packed(config, inputs, codes, photons).float()
            error = prediction - split[1][pick].float()[None]
            error = error - error.median(-1, keepdim=True).values
            for i, name in enumerate(names):
                per[name].append({**tail_stats(error[i]), "huber4": huber(error[i]), "huber12": huber(error[i], 12.)})
        result["search_batches"][split_name] = {
            "per_circuit": {n: summarize(per[n]) for n in names},
            "paired_vs_final_design": {n: summarize([{k: a[k] - b[k] for k in a} for a, b in zip(per[n], per["final_design"])])
                                       for n in names if n != "final_design"}}
    (OUT/"repeatability.json").write_text(json.dumps(result, indent=1)+"\n")

    keys = ("mae_m", "median_m", "p90_m", "p95_m", "p99_m", "over_1m", "over_3m", "rmse_m")
    print(f"validation, {args.draws} draws of {result['validation_rays_per_draw']} rays: mean +- sd")
    for n in names:
        s = result["validation_draws"][n]
        print(f"  {n:24s}", "  ".join(f"{k} {s[k]['mean']:.4f}+-{s[k]['sd']:.4f}" for k in keys))
    for n, s in result["validation_draws_paired"].items():
        print(f"  paired {n:17s}", "  ".join(f"{k} {s[k]['mean']:+.4f}+-{s[k]['sd']:.4f}" for k in keys))
    for split_name, block in result["search_batches"].items():
        print(f"{split_name}, {args.batches} batches of {args.rays} rays (batch median offset)")
        for n in names:
            s = block["per_circuit"][n]
            print(f"  {n:24s}", "  ".join(f"{k} {s[k]['mean']:.4f}+-{s[k]['sd']:.4f}" for k in keys + ("huber4", "huber12")))
        for n, s in block["paired_vs_final_design"].items():
            print(f"  paired {n:17s}", "  ".join(f"{k} {s[k]['mean']:+.4f}+-{s[k]['sd']:.4f}" for k in keys + ("huber4", "huber12")))


if __name__ == "__main__":
    main()
