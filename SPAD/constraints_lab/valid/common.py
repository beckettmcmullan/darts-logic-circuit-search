"""Shared helpers for the valid-bit track: data, reference circuits, readouts and the ROC measure."""
import json
from pathlib import Path

import torch

from spad import ROOT
from spad.dataset.photons import load_rays
from spad.training.police import Police, measure_pulse
from spad.training.train_stream import Validator

from constraints_lab.valid.background import (capture_groups, residual_profiles, residual_streams,
                                               uniform_streams, pixel_streams)
from constraints_lab.valid.sim import simulate_stream_full

DATA = ROOT/"data"
CONDITIONS = (16, 256, .6)
BUCKETS = ((16, 32), (32, 64), (64, 128), (128, 257))
REFERENCES = {
    "final-design": ROOT/"runs/2026-11-10_kaggle-t4_batch3_fused-larger-search/random-s4-seed0/circuit.json",
    "area-tol5": ROOT/"runs/2026-11-11_local-cpu_area-objective/final-design-tol5/circuit.json",
    "search-end-20um2": ROOT/"runs/2026-11-11_local-cpu_area-objective/final-design-tol5_no-recheck/search_end_circuit.json",
}


def load_circuit(path):
    return json.loads(Path(path).read_text())


def design_data():
    train = load_rays(DATA, "train", clean_only=True)[:2]
    routing = load_rays(DATA, "architecture", clean_only=True)[:2]
    validation = load_rays(DATA, "validation")[:2]
    return train, routing, validation


def standard_validator(train, validation, seed=1234):
    pulse, zero = measure_pulse(train[0])
    return Validator(train, validation, CONDITIONS, 3, Police(pulse, zero), seed=seed)


def validation_backgrounds(validation, sets=3, seed=4321):
    """Background-only streams for reporting, built from the validation split only."""
    g = torch.Generator().manual_seed(seed)
    rays = len(validation[1])
    groups = capture_groups(DATA, "validation")
    assert len(groups) == rays
    profiles = residual_profiles(validation[0], validation[1], groups)
    far = residual_profiles(validation[0], validation[1], groups, min_bin=48)
    out = {"uniform": [], "residual": [], "residual_far": [], "pixel": []}
    for _ in range(sets):
        out["uniform"].append(uniform_streams(rays, generator=g))
        p, n, _ = residual_streams(profiles, groups, generator=g)
        out["residual"].append((p, n))
        p, n, _ = residual_streams(far, groups, generator=g)
        out["residual_far"].append((p, n))
        p, n, _, _ = pixel_streams(validation[0], validation[1], generator=g)
        out["pixel"].append((p, n))
    return {k: (torch.cat([x[0] for x in v]), torch.cat([x[1] for x in v])) for k, v in out.items()}


def readouts(confidence, state):
    """Every no-new-logic valid bit: confidence >= k (k = 1..15) and each state bit or its inverse."""
    out = {f"conf>={k}": confidence >= k for k in range(1, 16)}
    for i in range(state.shape[-1]):
        out[f"state{i}"] = state[..., i] == 1
        out[f"~state{i}"] = state[..., i] == 0
    return out


def detection_at_limit(real_bits, background_bits, limit=.01):
    """Best detection over the readouts whose false-alarm rate is within the limit."""
    best = (0., None, 0.)
    for name, bits in real_bits.items():
        fa = float(background_bits[name].float().mean())
        det = float(bits.float().mean())
        if fa <= limit and det > best[0]:
            best = (det, name, fa)
    return best


def run_full(circuit, photons, chunk=12000):
    parts = [simulate_stream_full(circuit, photons[i:i+chunk]) for i in range(0, len(photons), chunk)]
    return tuple(torch.cat(x) for x in zip(*parts))
