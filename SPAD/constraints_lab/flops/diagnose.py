"""Drift diagnosis: how much worse than the anchor is a circuit on large design-split and validation samples?

For each circuit: search loss ratio and MAE ratio (circuit / anchor, same pixels) on 4 x 8,192 fresh
pixels from each design split, and validation MAE ratio (seed-7 and seed-1234 photon sets).
"""
import sys
import torch
from spad.core.stream_model import StreamConfig, pack_circuit, simulate_population_packed
from spad.dataset.photons import sample_conditions
from spad.training.train_stream import Validator, population_losses
from constraints_lab.flops.common import CONDITIONS, load_circuit, load_data

torch.set_num_threads(1)
anchor = load_circuit("runs/2026-11-10_kaggle-t4_batch3_fused-larger-search/random-s4-seed0/circuit.json")
train, routing, validation, police, _ = load_data()
validators = [Validator(train, validation, CONDITIONS, 3, police, seed=s) for s in (7, 1234)]
cfg = StreamConfig(**anchor["config"])
pa = pack_circuit(anchor)
g = torch.Generator().manual_seed(99)
draws = {}
for name, split in (("train", train), ("arch", routing)):
    draws[name] = []
    for _ in range(4):
        pick = torch.randint(len(split[1]), (8192,), generator=g)
        photons = sample_conditions(split[0][pick], *CONDITIONS, g)[0]
        draws[name].append((photons, split[1][pick], police.evidence(photons)))
for path in sys.argv[1:]:
    c = load_circuit(path)
    pc = pack_circuit(c)
    ins, cos = torch.stack((pa[0], pc[0])), torch.stack((pa[1], pc[1]))
    row = []
    for name, sets in draws.items():
        loss = torch.stack([population_losses(cfg, ins, cos, d, police, 4.) for d in sets]).sum(0)
        maes = []
        for photons, targets, _ in sets:
            e = simulate_population_packed(cfg, ins, cos, photons).float() - targets[None]
            maes.append((e - e.median(-1, keepdim=True).values).abs().mean(-1))
        mae = torch.stack(maes).sum(0)
        per_draw = [float(m[1] / m[0]) for m in maes]
        row.append(f"{name}: loss x{float(loss[1]/loss[0]):.3f} MAE x{float(mae[1]/mae[0]):.3f} "
                   f"(per 8k draw {min(per_draw):.3f}-{max(per_draw):.3f})")
    val = [v(c)["mae_m"] / v(anchor)["mae_m"] for v in validators]
    print(path.split("flops/")[-1], "|", " | ".join(row), f"| validation MAE x{val[0]:.3f} (seed 7) x{val[1]:.3f} (seed 1234)", flush=True)
