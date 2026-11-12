"""Design-split MAE and Huber loss of circuits (to compare with validation). Usage: name=path ..."""
import json, sys
import torch
from spad import ROOT
from spad.dataset.photons import load_rays, sample_conditions
from spad.core.stream_model import StreamConfig, pack_circuit, simulate_population_packed
from spad.training.baselines import BIN_METERS
torch.set_num_threads(1)
splits = {s: load_rays(ROOT/"data", s, clean_only=True)[:2] for s in ("train", "architecture")}
items = [a.split("=", 1) for a in sys.argv[1:]]
cs = [json.loads((ROOT/p).read_text()) for _, p in items]
cfg = StreamConfig(**{k: cs[0]["config"][k] for k in ("state_bits", "width", "layers")})
P = [pack_circuit(c) for c in cs]
inp, cod = torch.stack([p[0] for p in P]), torch.stack([p[1] for p in P])
for split, (h, t) in splits.items():
    g = torch.Generator().manual_seed(11)
    pick = torch.randperm(len(t), generator=g)[:16384]
    ph = sample_conditions(h[pick], 16, 256, .6, g)[0]
    err = simulate_population_packed(cfg, inp, cod, ph).float() - t[pick].float()
    err = err - err.median(-1, keepdim=True).values
    hub = torch.nn.functional.huber_loss(err, torch.zeros_like(err), delta=4., reduction="none").mean(-1)
    for (n, _), m, l in zip(items, err.abs().mean(-1), hub):
        print(f"{split:12s} {n:28s} MAE {float(m)*BIN_METERS:.3f} m  huber {float(l):.2f}")
