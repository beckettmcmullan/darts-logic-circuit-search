"""The low-photon benchmark: any design against the full-histogram fit on identical photons.

The reference configuration is a full histogram: 672 counters, one per time bin, read with the
sub-bin fit (matched filter over the measured pulse shape, then a centroid). A design is scored on
exactly the photons the histogram is given, stream by stream, so the comparison is paired.

What counts as the right answer. The reference labels come from a separate lidar and, on many rays,
disagree with the pixel's own data even when every recorded photon is used (multiple surfaces, weak
returns). Scoring against those labels measures the labels, not the method. So the benchmark:
  - uses only trusted rays: at least 1024 recorded photons, and the sub-bin fit of the ray's FULL
    recording (all its photons) within 3 bins of the label, so the two instruments agree on the surface;
  - takes that full-recording fit as the target (--truth full, the default): it is sub-bin precise,
    where the labels carry about a bin of noise. --truth label scores against the labels instead.
The target and the reference method share one estimator, which slightly favours the reference; the
label-truth numbers show how much.

Two sets of rays, both from design recordings only (held-out recordings are never loaded):
  dev       architecture recordings at even positions (16 recordings): look at it as often as you like
  decision  architecture recordings at odd positions (15 recordings): for the final, reported number
The validation recording is reported as a third set ("validation") for continuity with older tables;
training jobs select on it, so it is not a decision set.

Photons are drawn on the CPU from fixed seeds, so every machine scores the same streams. The main
condition is 16-32 photons with 0-60% extra background; 32-64, 64-128 and 128-256 photons are guard
bands, where a design must not get worse. Each method's calibration constant is fitted once on
training recordings at 16-256 photons and reused everywhere.

A design is either a circuit file (name=path/to/circuit.json, simulated with predict_bins) or any
Python function (name=path/to/file.py:function) taking photons [streams, steps] (arrival bins, -1 =
no photon, in arrival order) and returning the range in bins as a float tensor [streams].

Run from SPAD/accuracy-focused/:
  python -m validation.benchmark mine=../runs/x/circuit.json --set dev --out bench_dev.json
"""
import argparse
import importlib.util
import json
from pathlib import Path

import numpy as np
import torch

from neuralnetwork import ROOT
from neuralnetwork.core.stream_model import predict_bins
from neuralnetwork.dataset.photons import photon_histogram, sample_conditions
from neuralnetwork.dataset.prepare import BIN_METERS
from validation.eval_large import MISS_BINS, SHIFT, load_split, moved
from neuralnetwork.training.baselines import peak, subbin_fit
from neuralnetwork.training.police import measure_pulse

NAME = "lowphoton-v1"
REFERENCE = "histogram, sub-bin fit"
MAIN_BAND = (16, 32)
GUARD_BANDS = ((32, 64), (64, 128), (128, 256))
MAX_BACKGROUND = .6
SEEDS = {"dev": 5150, "decision": 6160, "validation": 7170}
DRAWS = {"dev": 8, "decision": 8, "validation": 24}
GUARD_RAYS = 20000                       # guard bands use a fixed random subset of the set's rays
TRUST_BINS, MIN_RECORDED = 3., 1024      # a trusted ray: full-recording fit within 3 bins of the label
# Circuits scored with --references, besides the histogram methods (paths relative to SPAD/).
REFERENCES = {"k4 + gate": "accuracy-focused/circuit/circuit.json",
              "area-optimized circuit": "area-optimized/circuit/circuit.json"}


def rays_of(data, which):
    """(histograms, targets, recording index per ray, recording names) of one benchmark set."""
    if which == "validation":
        return load_split(data, "validation")
    histograms, targets, capture, names = load_split(data, "architecture")
    keep = capture % 2 == (0 if which == "dev" else 1)
    return histograms[keep], targets[keep], capture[keep], names


def load_design(spec):
    name, path = spec.split("=", 1)
    if ".py:" in path:
        file, function = path.rsplit(":", 1)
        module_spec = importlib.util.spec_from_file_location(f"design_{abs(hash(file))}", file)
        module = importlib.util.module_from_spec(module_spec)
        module_spec.loader.exec_module(module)
        return name, getattr(module, function), path
    circuit = json.loads(Path(path).read_text())
    return name, (lambda photons: predict_bins(circuit, photons)), path


def score(designs, data, which, device="cpu", chunk=65536, bands=None, draws=None, truth="full"):
    """Per-band rows for every design plus the histogram methods, and paired differences from the fit."""
    train = load_split(data, "train")
    pulse, zero = measure_pulse(train[0])
    table = {"histogram, tallest bar": lambda p: peak(photon_histogram(p)).float(),
             REFERENCE: lambda p: subbin_fit(photon_histogram(p), pulse.to(p.device), zero).float()}
    table.update(designs)

    bright = train[0].sum(1) >= MIN_RECORDED
    full_offset = float((subbin_fit(train[0][bright][:40000], pulse, zero) - train[1][bright][:40000]).median())

    def trusted(histograms, labels):
        """Mask of trusted rays, and the target of every ray under the chosen truth."""
        full = subbin_fit(histograms, pulse, zero) - full_offset
        keep = ((full - labels).abs() <= TRUST_BINS) & (histograms.sum(1) >= MIN_RECORDED)
        return keep, (full if truth == "full" else labels)

    generator = torch.Generator().manual_seed(2026)
    keep, train_targets = trusted(train[0], train[1])
    pick = torch.nonzero(keep)[:, 0]
    pick = pick[torch.randperm(len(pick), generator=generator)[:8000]]
    fit_photons = sample_conditions(train[0][pick], 16, 256, MAX_BACKGROUND, generator)[0].to(device)
    fit_targets = train_targets[pick].to(device)
    can_move = fit_targets + SHIFT + 24 < 672
    offsets = {n: float((f(fit_photons) - fit_targets).median()) for n, f in table.items()}
    moved_offsets = {n: float((f(moved(fit_photons[can_move])) - fit_targets[can_move] - SHIFT).median())
                     for n, f in table.items()}

    histograms, labels, capture, names = rays_of(data, which)
    all_rays = len(labels)
    keep, targets = trusted(histograms, labels)
    histograms, targets, capture = histograms[keep], targets[keep], capture[keep]
    recordings = len(names)
    result = {"benchmark": NAME, "set": which, "truth": truth, "rays": len(targets), "rays_before_trust_filter": all_rays,
              "recordings": int(len(capture.unique())),
              "reference": REFERENCE, "bin_m": BIN_METERS, "offset_bins": offsets, "bands": {}}
    draws = draws or DRAWS[which]
    for low, high in bands or (MAIN_BAND,) + GUARD_BANDS:
        sampler = torch.Generator().manual_seed(SEEDS[which] + low)
        rays = torch.arange(len(targets))
        if (low, high) != MAIN_BAND and len(rays) > GUARD_RAYS:
            rays = torch.randperm(len(rays), generator=sampler)[:GUARD_RAYS].sort().values
        rays = rays[histograms[rays].sum(1) >= high]
        errors = {n: [] for n in table}
        moved_errors = {n: [] for n in table}
        caps, backgrounds, movables = [], [], []
        for _ in range(draws):
            for start in range(0, len(rays), chunk):
                ids = rays[start:start + chunk]
                photons, _, background = sample_conditions(histograms[ids], low, high, MAX_BACKGROUND, sampler)
                photons = photons.to(device)
                target = targets[ids].to(device)
                movable = target + SHIFT + 24 < 672
                shifted = moved(photons[movable])
                caps.append(capture[ids]); backgrounds.append(background); movables.append(movable.cpu())
                for n, f in table.items():
                    errors[n].append((f(photons) - offsets[n] - target).cpu())
                    moved_errors[n].append((f(shifted) - moved_offsets[n] - target[movable] - SHIFT).abs().cpu())
        cap, background, movable = torch.cat(caps), torch.cat(backgrounds), torch.cat(movables)
        size = {n: torch.cat(e).abs() for n, e in errors.items()}
        reference = size[REFERENCE]
        rows = {}
        for n in table:
            e = size[n]
            large = e > MISS_BINS
            row = {"streams": len(e), "mae_m": float(e.mean() * BIN_METERS), "median_m": float(e.median() * BIN_METERS),
                   "recall_half_bin": float((e <= .5).float().mean()), "recall_1_bins": float((e <= 1).float().mean()),
                   "recall_3_bins": float((e <= 3).float().mean()), "large_miss_rate": float(large.float().mean()),
                   "avoidable_large_miss_rate": float((large & (reference <= MISS_BINS)).float().mean()),
                   "mae_from_large_misses_m": float((e * large).mean() * BIN_METERS),
                   "mae_high_background_m": float(e[background >= .4].mean() * BIN_METERS),
                   "moved_target_mae_m": float(torch.cat(moved_errors[n]).mean() * BIN_METERS),
                   "median_signed_bins": float(torch.cat(errors[n]).median())}
            # Paired with the histogram fit on the same streams, then averaged per recording, so the
            # interval reflects scene-to-scene variation and not just the number of streams.
            gap = ((e - reference) * BIN_METERS).double()
            total = torch.zeros(recordings, dtype=torch.double).index_add_(0, cap, gap)
            count = torch.zeros(recordings, dtype=torch.double).index_add_(0, cap, torch.ones_like(gap))
            used = count > 0
            per = (total[used] / count[used]).numpy()
            rng = np.random.default_rng(0)
            boot = [rng.choice(per, len(per)).mean() for _ in range(4000)] if len(per) > 1 else [float(gap.mean())]
            row["minus_reference_m"] = {"all_streams": float(gap.mean()), "mean_of_recordings": float(per.mean()),
                                        "low": float(np.percentile(boot, 2.5)), "high": float(np.percentile(boot, 97.5)),
                                        "recordings_at_or_below_reference": int((per <= 0).sum()),
                                        "recordings": int(len(per))}
            rows[n] = row
        result["bands"][f"{low}-{high}"] = rows
    return result


def table_text(result):
    lines = [f"benchmark {result['benchmark']}, set {result['set']}, truth = "
             f"{'full-recording fit' if result['truth'] == 'full' else 'reference label'}: {result['rays']} trusted rays of "
             f"{result['rays_before_trust_filter']}, {result['recordings']} recordings. "
             f"Reference: {result['reference']} (672 counters)."]
    for band, rows in result["bands"].items():
        lines += ["", f"{band} photons" + ("  <- main condition" if band == "16-32" else "  (guard band)"),
                  f"{'method':32s} {'streams':>8s} {'mean':>6s} {'median':>6s} {'<=.5bin':>7s} {'<=1bin':>6s} {'<=3bin':>6s} "
                  f"{'large':>6s} {'avoid':>6s} {'hi-bg':>6s} {'moved':>6s}   mean minus histogram fit [95%], recordings <= fit"]
        for name, r in rows.items():
            d = r["minus_reference_m"]
            lines.append(f"{name:32s} {r['streams']:8d} {r['mae_m']:6.3f} {r['median_m']:6.3f} {r['recall_half_bin']:7.1%} "
                         f"{r['recall_1_bins']:6.1%} {r['recall_3_bins']:6.1%} {r['large_miss_rate']:6.2%} "
                         f"{r['avoidable_large_miss_rate']:6.2%} {r['mae_high_background_m']:6.3f} "
                         f"{r['moved_target_mae_m']:6.3f}   {d['mean_of_recordings']:+.4f} [{d['low']:+.4f}, {d['high']:+.4f}]"
                         f"  {d['recordings_at_or_below_reference']}/{d['recordings']}")
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("designs", nargs="*", help="name=circuit.json or name=file.py:function")
    parser.add_argument("--set", default="dev", choices=tuple(SEEDS))
    parser.add_argument("--data", type=Path, default=ROOT/"data")
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--references", action="store_true", help="also score the project's existing circuits")
    parser.add_argument("--main-only", action="store_true", help="only the 16-32 photon band (quick look)")
    parser.add_argument("--truth", default="full", choices=("full", "label"),
                        help="target: the ray's full-recording fit (default) or the reference label")
    parser.add_argument("--device", default="cpu")
    parser.add_argument("--threads", type=int, default=1)
    args = parser.parse_args()
    torch.set_num_threads(args.threads)
    specs = ([f"{name}={ROOT/path}" for name, path in REFERENCES.items()] if args.references else []) + args.designs
    designs, sources = {}, {}
    for spec in specs:
        name, function, source = load_design(spec)
        designs[name], sources[name] = function, str(source)
    result = score(designs, args.data, args.set, args.device, bands=(MAIN_BAND,) if args.main_only else None,
                   truth=args.truth)
    result["designs"] = sources
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, indent=2) + "\n")
    text = table_text(result)
    args.out.with_suffix(".txt").write_text(text + "\n")
    print(text)


if __name__ == "__main__":
    main()
