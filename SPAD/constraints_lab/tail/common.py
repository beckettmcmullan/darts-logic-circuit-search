"""Shared pieces for the tail track: tail measures, reference circuits, data setup."""
import json
from pathlib import Path

import torch

from spad import ROOT
from spad.dataset.photons import load_rays
from spad.dataset.prepare import BIN_METERS
from spad.training.police import Police, measure_pulse

CONDITIONS = (16, 256, .6)
ONE_METRE_BINS = 1./BIN_METERS          # 8.9 bins
THREE_METRE_BINS = 3./BIN_METERS
REFERENCES = {
    "final_design": ROOT/"runs/2026-11-10_kaggle-t4_batch3_fused-larger-search/random-s4-seed0/circuit.json",
    "area_tol5": ROOT/"runs/2026-11-11_local-cpu_area-objective/final-design-tol5/circuit.json",
    "search_end_no_recheck": ROOT/"runs/2026-11-11_local-cpu_area-objective/final-design-tol5_no-recheck/search_end_circuit.json",
}
OUT = ROOT/"runs/2026-11-11_constraints-lab/tail"


def load_circuit(path):
    return json.loads(Path(path).read_text())


def tail_stats(error_bins):
    """Tail of |error| (error in bins, after offset): percentiles in metres and shares over 1 m / 3 m."""
    a = error_bins.float().abs()
    q = torch.quantile(a, torch.tensor([.5, .9, .95, .99], dtype=a.dtype))*BIN_METERS
    return {"mae_m": float(a.mean()*BIN_METERS), "median_m": float(q[0]), "p90_m": float(q[1]),
            "p95_m": float(q[2]), "p99_m": float(q[3]), "rmse_m": float(a.square().mean().sqrt()*BIN_METERS),
            "over_1m": float((a > ONE_METRE_BINS).float().mean()),
            "over_3m": float((a > THREE_METRE_BINS).float().mean())}


def setup(data=ROOT/"data"):
    """Same splits and police as train_stream.main: clean train/architecture, all validation labels."""
    train = list(load_rays(data, "train", clean_only=True)[:2])
    routing = list(load_rays(data, "architecture", clean_only=True)[:2])
    validation = list(load_rays(data, "validation"))
    pulse, zero = measure_pulse(train[0])
    return train, routing, validation, Police(pulse, zero)
