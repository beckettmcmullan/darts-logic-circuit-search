"""Why can validation MAE jump while design-split losses pass? Split validation MAE by the clean flag.

The search scores mutants on clean-only train/architecture pixels; validation includes non-clean
pixels. Usage: python -m constraints_lab.steadiness.diag name=path ...
"""
import json
import sys

import torch

from spad import ROOT
from spad.dataset.photons import load_rays
from spad.core.stream_model import simulate_stream
from spad.training.baselines import metrics
from spad.training.police import Police, measure_pulse
from spad.training.train_stream import Validator


def main():
    torch.set_num_threads(1)
    data = ROOT/"data"
    train = load_rays(data, "train", clean_only=True)[:2]
    histograms, targets, clean = load_rays(data, "validation")
    pulse, zero = measure_pulse(train[0])
    validator = Validator(train, (histograms, targets), (16, 256, .6), 3, Police(pulse, zero), seed=1234)
    clean3 = clean.repeat(3)
    print(f"validation rays per set {len(targets)}, clean share {float(clean.float().mean()):.3f}")
    for item in sys.argv[1:]:
        name, path = item.split("=", 1)
        circuit = json.loads((ROOT/path).read_text())
        prediction = simulate_stream(circuit, validator.photons).float() - validator.offset(circuit)
        a, c, n = (metrics(prediction[m], validator.targets[m])["mae_m"] for m in
                   (torch.ones_like(clean3), clean3, ~clean3))
        print(f"{name:28s} MAE all {a:.3f}  clean {c:.3f}  non-clean {n:.3f}", flush=True)


if __name__ == "__main__":
    main()
