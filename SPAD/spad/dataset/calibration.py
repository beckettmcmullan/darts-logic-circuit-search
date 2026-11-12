"""Refine SPAD intrinsics on training captures and write audited range labels.

Released p1/p2 intrinsics leave large alignment errors against the Livox labels.
This searches six global lens numbers (fx, fy, cx, cy, k1, k2) to minimize the
median |histogram peak - projected label| on training captures only. Six global
numbers cannot memorize rays; generalization is checked on the routing and
selection captures. Test captures receive the frozen result and are not scored.

The SPAD peak is the alignment reference, so this self-calibrates the two
sensors. It is not an independent measure of truth, and it gives peak-based
estimators a small home advantage. Original labels stay in {capture}.npz.
"""
import argparse
import json
from pathlib import Path

import numpy as np

from spad import ROOT
from spad.dataset.prepare import BIN_METERS, load_intrinsics, project_ranges

WIDTH, HEIGHT = 256, 192
NAMES = ("fx", "fy", "cx", "cy", "k1", "k2")
STEPS = ((4., 4., 2., 2., .04, .02), (2., 2., 1., 1., .02, .01), (1., 1., .5, .5, .01, .005),
         (.5, .5, .25, .25, .005, .0025))


def edge_free(depth, radius=1, tolerance=0.3):
    """True where labelled neighbours agree, so a small misprojection is harmless."""
    grid = depth.reshape(HEIGHT, WIDTH)
    padded = np.pad(grid, radius, constant_values=np.inf)
    low, high = np.full(grid.shape, np.inf), np.full(grid.shape, -np.inf)
    seen = np.zeros(grid.shape, dtype=int)
    for dy in range(2*radius+1):
        for dx in range(2*radius+1):
            window = padded[dy:dy+HEIGHT, dx:dx+WIDTH]
            finite = np.isfinite(window)
            low = np.where(finite, np.minimum(low, window), low)
            high = np.where(finite, np.maximum(high, window), high)
            seen += finite
    return ((high-low <= tolerance) & (seen >= 2)).reshape(-1)


def project(points, transform, values):
    intrinsics = dict(zip(NAMES[:4], values[:4]))
    return project_ranges(points, transform, intrinsics, values[4], values[5])


def label_error(capture, transform, offsets, values, bin_offset):
    depth = project(capture["points"], transform, values)[capture["pixels"]]
    finite = np.isfinite(depth)
    bins = (depth+offsets[capture["pixels"]])/BIN_METERS + bin_offset
    return float(np.median(np.abs(capture["peak"]-bins)[finite])*BIN_METERS)


def refine(captures, transform, offsets, start, bin_offset):
    values = list(start)
    score = lambda v: float(np.mean([label_error(c, transform, offsets, v, bin_offset) for c in captures]))
    best = score(values)
    for steps in STEPS:
        improved = True
        while improved:
            improved = False
            for i, step in enumerate(steps):
                for sign in (-1, 1):
                    while True:
                        trial = list(values)
                        trial[i] += sign*step
                        result = score(trial)
                        if result >= best:
                            break
                        values, best, improved = trial, result, True
            print(f"step scale {steps[0]}: {np.round(values, 4).tolist()} -> {best:.4f} m", flush=True)
    return values, best


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT/"data")
    args = parser.parse_args()
    root = args.root
    manifest = json.loads((root/"manifest.json").read_text())
    metadata = json.loads((root/"processed/metadata.json").read_text())
    raw = root/"raw"
    transform = np.loadtxt(raw/"config/final_extrinsic_sp_to_livox.txt")
    offsets = np.loadtxt(raw/"config/offset.txt").reshape(-1)
    bin_offset = metadata["bin_offset"]
    splits = manifest["splits"]

    def load(capture):
        with np.load(root/"processed"/f"{capture}.npz") as d:
            hist, pixels = d["histograms"], d["pixel_indices"]
        points = np.loadtxt(raw/f"DepthEstimate/gt/{capture}.csv", delimiter=",", skiprows=1, usecols=(8, 9, 10))
        return {"points": points, "pixels": pixels, "peak": hist.argmax(1)}

    fit = [load(c) for c in splits["train"]]
    p1 = load_intrinsics(raw/"config/config.yaml", "p1")
    start = [p1[name] for name in NAMES]
    values, train_error = refine(fit, transform, offsets, start, bin_offset)
    report = {"fit_captures": splits["train"], "start_p1": dict(zip(NAMES, start)),
              "refined": dict(zip(NAMES, values)), "train_median_m": train_error, "check_captures": {}}
    # Depth-track captures only; scenes.py labels Reconstruction views with the frozen result.
    for capture in sorted(int(c) for c in metadata["captures"] if c.isdigit()):
        d = load(capture)
        depth_all = project(d["points"], transform, values)
        depth = depth_all[d["pixels"]]
        target = (depth+offsets[d["pixels"]])/BIN_METERS + bin_offset
        labelled = np.isfinite(target) & (target >= 0) & (target <= 671)
        np.savez(root/"processed"/f"labels_{capture}.npz", target_bins=target.astype(np.float32),
                 labelled=labelled, clean=edge_free(depth_all)[d["pixels"]] & labelled)
        if capture in splits["architecture"] + splits["validation"]:
            report["check_captures"][capture] = {
                "p1_median_m": label_error(d, transform, offsets, start, bin_offset),
                "refined_median_m": label_error(d, transform, offsets, values, bin_offset)}
    (root/"processed/calibration_report.json").write_text(json.dumps(report, indent=2)+"\n")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
