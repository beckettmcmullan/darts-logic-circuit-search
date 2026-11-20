"""Software and hand-rule reference estimators, fitted on design captures only.

These are the comparison points for the learned circuit: histogram argmax ("peak"),
a width-8 box filter then argmax ("box8"), a peak with a bias table keyed on the peak
height ("lut"), a small 1-D CNN over the histogram, and the hand-written streaming
rules from neuralnetwork.core.stream_model.rule_circuit. Each is scored on a full histogram and
on photon budgets of 16-256 photons drawn with neuralnetwork.dataset.photons. Offsets and the
CNN are fitted on the train split only; results on the architecture and validation
splits are written to design_metrics.json. Distances are reported in metres
(1 bin = 750 ps = about 0.1124 m).

Usage (from SPAD/):  python -m neuralnetwork.training.baselines [--data DIR] [--out DIR]
                         [--cnn-seconds S] [--cnn-budgets N ...] [--threads N]
"""
import argparse
import json
from pathlib import Path
import time

import numpy as np
import torch
from torch import nn

from neuralnetwork import ROOT
from neuralnetwork.dataset.photons import load_rays, photon_histogram, sample_photons
from neuralnetwork.dataset.prepare import BIN_METERS
from neuralnetwork.core.stream_model import StreamConfig, rule_circuit, simulate_stream

BUDGETS = (16, 32, 64, 128, 256)


def metrics(prediction, target):
    """Error summary of predicted vs target bins (same shape, in bins).

    Returns mae_m, median_m, rmse_m (metres) and recall_{1,3,5}_bins (fraction of
    rays within that many bins). Also used by train_stream.
    """
    error = (prediction.float() - target).abs()
    return {"mae_m": float(error.mean()*BIN_METERS), "median_m": float(error.median()*BIN_METERS),
            "rmse_m": float(error.square().mean().sqrt()*BIN_METERS),
            **{f"recall_{n}_bins": float((error <= n).float().mean()) for n in (1, 3, 5)}}


def scored(prediction, target, clean):
    """metrics() on all rays and on the clean (edge-free) subset; clean is a bool mask."""
    return {"all": metrics(prediction, target), "clean": metrics(prediction[clean], target[clean])}


def box_peak(histograms, width):
    """Argmax bin of the histogram after a box filter of `width` bins; float [rays]."""
    kernel = torch.ones(1, 1, width)
    return nn.functional.conv1d(histograms.float()[:, None], kernel, padding=width//2)[:, 0].argmax(-1).float()


def peak(histograms):
    """Argmax bin of each histogram; float [rays]."""
    return histograms.argmax(-1).float()


def lut_index(histograms):
    """Bucket of each ray's peak height (log2 of the max count, half-octave steps); indexes the bias table."""
    return torch.bucketize(torch.log2(histograms.amax(-1).float() + 1), torch.arange(1., 12.01, .5))


class RangeCNN(nn.Module):
    """Small per-pixel software reference: a dilated 1-D convolution over bins."""
    def __init__(self, channels=24):
        super().__init__()
        self.net = nn.Sequential(
            nn.Conv1d(1, channels, 9, padding=4), nn.ReLU(),
            nn.Conv1d(channels, channels, 9, padding=8, dilation=2), nn.ReLU(),
            nn.Conv1d(channels, channels, 9, padding=16, dilation=4), nn.ReLU(),
            nn.Conv1d(channels, 1, 1))

    def forward(self, histograms):
        return self.net(torch.log1p(histograms.float())[:, None])[:, 0]

    @torch.no_grad()
    def predict(self, histograms):
        return torch.cat([self(histograms[i:i+500]).argmax(-1) for i in range(0, len(histograms), 500)]).float()


def train_cnn(histograms, targets, budget, seconds, seed=0):
    """Train a RangeCNN for `seconds` of wall time.

    budget: photons per ray to resample each batch with (0 = use the full histogram).
    The target is a soft Gaussian (variance 4 bins^2) around the label bin, trained
    with cross-entropy over the 672 bins.
    """
    torch.manual_seed(seed)
    generator = torch.Generator().manual_seed(seed)
    model = RangeCNN()
    optimizer = torch.optim.Adam(model.parameters(), 2e-3)
    bins = torch.arange(672.)
    started = time.monotonic()
    while time.monotonic() - started < seconds:
        order = torch.randperm(len(targets))
        for start in range(0, len(targets), 128):
            batch = order[start:start+128]
            inputs = histograms[batch]
            if budget:
                inputs = photon_histogram(sample_photons(inputs, budget, generator))
            soft = (-(bins[None] - targets[batch, None])**2 / 8.).softmax(-1)
            loss = -(soft * model(inputs).log_softmax(-1)).sum(-1).mean()
            optimizer.zero_grad()
            loss.backward()
            optimizer.step()
            if time.monotonic() - started > seconds:
                break
    return model


def evaluate_methods(fitted, cnns, histograms, targets, clean, seed=1):
    """Score every frozen reference method on one split."""
    results = {}
    def add(name, prediction, offset):
        results[name] = scored(prediction - offset, targets, clean)
    add("peak_full", peak(histograms), fitted["offset"]["peak_full"])
    add("box8_full", box_peak(histograms, 8), fitted["offset"]["box8_full"])
    table = torch.tensor(fitted["lut"])
    add("peak_lut_full", peak(histograms) - table[lut_index(histograms)], 0.)
    if "cnn_full" in cnns:
        add("cnn_full", cnns["cnn_full"].predict(histograms), 0.)
    generator = torch.Generator().manual_seed(seed)
    for budget in BUDGETS:
        photons = sample_photons(histograms, budget, generator)
        small = photon_histogram(photons)
        add(f"peak_{budget}", peak(small), fitted["offset"][f"peak_{budget}"])
        add(f"box8_{budget}", box_peak(small, 8), fitted["offset"][f"box8_{budget}"])
        if f"cnn_{budget}" in cnns:
            add(f"cnn_{budget}", cnns[f"cnn_{budget}"].predict(small), 0.)
        for window in StreamConfig().windows:
            add(f"rule{window}_{budget}", simulate_stream(rule_circuit(window=window), photons).float(),
                fitted["offset"][f"rule{window}_{budget}"])
    return results


def main():
    """CLI entry point: fit offsets and bias table, train CNNs, score every method."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data", type=Path, default=ROOT/"data")
    parser.add_argument("--out", type=Path, default=ROOT/"runs/2026-11-05_reference-baselines")
    parser.add_argument("--cnn-seconds", type=float, default=150)
    parser.add_argument("--cnn-budgets", type=int, nargs="*", default=[64])
    parser.add_argument("--threads", type=int, default=4)
    args = parser.parse_args()
    torch.set_num_threads(args.threads)
    args.out.mkdir(parents=True, exist_ok=True)
    histograms, targets, clean = load_rays(args.data, "train")
    fit = torch.randperm(len(targets), generator=torch.Generator().manual_seed(0))[:8000]
    fit_h, fit_t = histograms[fit], targets[fit]
    generator = torch.Generator().manual_seed(0)
    median = lambda prediction: float((prediction - fit_t).median())
    offset = {"peak_full": median(peak(fit_h)), "box8_full": median(box_peak(fit_h, 8))}
    for budget in BUDGETS:
        photons = sample_photons(fit_h, budget, generator)
        small = photon_histogram(photons)
        offset[f"peak_{budget}"] = median(peak(small))
        offset[f"box8_{budget}"] = median(box_peak(small, 8))
        for window in StreamConfig().windows:
            offset[f"rule{window}_{budget}"] = median(simulate_stream(rule_circuit(window=window), photons).float())
    index = lut_index(histograms)
    residual = peak(histograms) - targets
    overall = float(residual.median())
    lut = [float(residual[index == i].median()) if (index == i).sum() >= 50 else overall for i in range(int(index.max())+2+24)]
    fitted = {"offset": offset, "lut": lut}
    (args.out/"fitted.json").write_text(json.dumps(fitted, indent=2)+"\n")
    cnns = {}
    if args.cnn_seconds > 0:
        for budget in [0] + args.cnn_budgets:
            name = f"cnn_{budget}" if budget else "cnn_full"
            cnns[name] = train_cnn(histograms, targets, budget, args.cnn_seconds)
            torch.save(cnns[name].state_dict(), args.out/f"{name}.pt")
    results = {}
    for split in ("architecture", "validation"):
        h, t, c = load_rays(args.data, split)
        results[split] = evaluate_methods(fitted, cnns, h, t, c)
    (args.out/"design_metrics.json").write_text(json.dumps(results, indent=2)+"\n")
    for name, row in results["validation"].items():
        a, c = row["all"], row["clean"]
        print(f"{name:16s} all MAE {a['mae_m']:.3f} med {a['median_m']:.3f} r3 {a['recall_3_bins']:.3f} | clean MAE {c['mae_m']:.3f} med {c['median_m']:.3f} r3 {c['recall_3_bins']:.3f}")


if __name__ == "__main__":
    main()
