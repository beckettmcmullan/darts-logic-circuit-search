"""Compare circuits and histogram methods on identical validation photons, with sub-bin detail.

Every method sees the same photons: validation recordings, random photon counts (16-256)
and extra ambient (0-0.6), three photon sets. Each method's constant offset is fitted on
training recordings. The histogram is always read with a sub-bin fit (matched filter plus
centroid) as well as the plain tallest bar.

Three kinds of numbers:
- error against the reference distances (which themselves carry about 0.6-1 bin of noise),
- repeatability: the spread of one pixel's answer over fresh photon draws, which needs no
  reference and shows the resolution a method can actually hold,
- agreement with a sub-bin fit of the pixel's full histogram (all its photons).
Held-out recordings are never loaded.
"""
import argparse
import json
from pathlib import Path

import torch

from training import ROOT
from training.core.stream_model import predict_bins
from training.dataset.photons import load_rays, photon_histogram, sample_conditions, sample_photons
from training.dataset.prepare import BIN_METERS
from training.training.baselines import box_peak, metrics, peak, subbin_fit
from training.training.police import Police, measure_pulse
from training.training.train_stream import Validator


def detail(prediction, targets):
    error = (prediction - targets).abs()
    row = metrics(prediction, targets)
    row["recall_half_bin"] = float((error <= .5).float().mean())
    row["over_1m"] = float((error * BIN_METERS > 1).float().mean())
    return row


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("circuits", nargs="+", help="name=path/to/circuit.json")
    parser.add_argument("--data", type=Path, default=ROOT/"data")
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--repeat-pixels", type=int, default=2000)
    parser.add_argument("--repeat-draws", type=int, default=16)
    parser.add_argument("--threads", type=int, default=4)
    parser.add_argument("--seed", type=int, default=1234, help="Validator seed: which validation photon draw is scored")
    args = parser.parse_args()
    torch.set_num_threads(args.threads)
    train = load_rays(args.data, "train", clean_only=True)[:2]
    validation = load_rays(args.data, "validation")[:2]
    pulse, zero = measure_pulse(train[0])
    validator = Validator(train, validation, (16, 256, .6), 3, Police(pulse, zero), seed=args.seed)
    fit = lambda h: subbin_fit(h, pulse, zero)
    histogram_methods = {"histogram, tallest bar": peak, "histogram, 8-bin box": lambda h: box_peak(h, 8),
                         "histogram, sub-bin fit": fit}
    full = fit(validation[0])                                   # every photon the pixel recorded
    full_sets = full.repeat(3)

    generator = torch.Generator().manual_seed(99)
    pixels = torch.randperm(len(validation[1]), generator=generator)[:args.repeat_pixels]
    repeats = {n: sample_photons(validation[0][pixels].repeat_interleave(args.repeat_draws, 0), n, generator)
               for n in (64, 256)}

    miss_bins = 9.                                               # about 1 m
    moved = lambda photons: torch.where(photons >= 0, (photons + 300) % 672, photons)
    reference = {}

    def report(predict):
        """predict(photons) -> range in bins, before the constant offset."""
        offset = float((predict(validator.fit_photons) - validator.fit_targets).median())
        prediction = predict(validator.photons) - offset
        row = detail(prediction, validator.targets)
        row["offset_bins"] = offset
        # Avoidable large misses: far off where a sub-bin histogram fit of the same photons is not.
        error = (prediction - validator.targets).abs()
        avoidable = (error > miss_bins) & reference["histogram_ok"]
        row["avoidable_miss_rate"] = float(avoidable.float().mean())
        row["avoidable_miss_mean_error_share_m"] = float((error * avoidable).mean() * BIN_METERS)
        row["avoidable_miss_rate_16-32_photons"] = float(avoidable[validator.counts < 32].float().mean())
        row["mae_16-32_photons_m"] = float(error[validator.counts < 32].mean() * BIN_METERS)
        # Moved-target check: delay every photon by 300 bins (wrapping), so targets sit mid-window. A
        # method that leans on targets being near the start of the window gets worse here.
        moved_offset = float((predict(moved(validator.fit_photons)) - validator.fit_targets - 300).median())
        moved_error = (predict(moved(validator.photons)) - moved_offset - validator.targets - 300).abs()
        row["moved_target_mae_m"] = float(moved_error.mean() * BIN_METERS)
        gap = prediction - full_sets
        row["vs_full_histogram_fit"] = {
            "median_m": float((gap - gap.median()).abs().median() * BIN_METERS),
            "within_1_bin": float(((gap - gap.median()).abs() <= 1).float().mean())}
        for low, high in ((16, 32), (32, 64), (64, 128), (128, 257)):
            keep = (validator.counts >= low) & (validator.counts < high)
            part = detail(prediction[keep], validator.targets[keep])
            row[f"photons_{low}-{min(high, 256)}"] = {
                "mae_m": part["mae_m"], "median_m": part["median_m"], "recall_1_bins": part["recall_1_bins"],
                "median_signed_bins": float((prediction[keep] - validator.targets[keep]).median())}
        for n, photons in repeats.items():
            answers = predict(photons).reshape(len(pixels), args.repeat_draws)
            centre = answers.median(1, keepdim=True).values
            # Mean distance of a pixel's answers from their own median: fine-grained even when
            # the answers are whole bins, and the median over pixels ignores the few that jump.
            spread = (answers - centre).abs().mean(1)
            row[f"repeatability_{n}_photons"] = {
                "median_spread_m": float(spread.median() * BIN_METERS),
                "pixels_spread_below_half_bin": float((spread < .5).float().mean()),
                "draws_within_half_bin_of_pixel_median": float(((answers - centre).abs() <= .5).float().mean())}
        return row

    results = {"conditions": f"validation, 16-256 photons, extra ambient 0-0.6, 3 photon sets, seed {args.seed}",
               "bin_m": BIN_METERS, "full_histogram_fit": detail(full - float((fit(train[0][:8000]) - train[1][:8000]).median()),
                                                                 validation[1])}
    fit_offset = float((fit(photon_histogram(validator.fit_photons)) - validator.fit_targets).median())
    reference["histogram_ok"] = (fit(photon_histogram(validator.photons)) - fit_offset - validator.targets).abs() <= miss_bins
    for name, method in histogram_methods.items():
        results[name] = report(lambda photons: method(photon_histogram(photons)).float())
    for item in args.circuits:
        name, path = item.split("=", 1)
        circuit = json.loads(Path(path).read_text())
        row = report(lambda photons: predict_bins(circuit, photons))
        audit = validator.audit(circuit)
        row["time_shift_test"] = audit["time_shift_test"]["moves_with_photons_within_1_bin"]
        row["police_flags"] = audit["police_violation_rate"]["physics"]
        row["config"] = circuit["config"]
        row["circuit"] = path
        results[name] = row
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(results, indent=2) + "\n")
    print(f"{'method':34s} {'mean':>6s} {'median':>6s} {'<=.5bin':>7s} {'<=1bin':>6s} {'<=3bin':>6s} {'>1m':>5s} "
          f"{'spread64':>7s} {'spread256':>9s} {'avoidable':>9s} {'its mean':>8s} {'16-32ph':>7s} {'moved':>6s}")
    for name, row in results.items():
        if isinstance(row, dict) and "repeatability_64_photons" in row:
            print(f"{name:34s} {row['mae_m']:6.3f} {row['median_m']:6.3f} {row['recall_half_bin']:7.1%} "
                  f"{row['recall_1_bins']:6.1%} {row['recall_3_bins']:6.1%} {row['over_1m']:5.1%} "
                  f"{row['repeatability_64_photons']['median_spread_m']:7.3f} "
                  f"{row['repeatability_256_photons']['median_spread_m']:9.3f} "
                  f"{row['avoidable_miss_rate']:9.2%} {row['avoidable_miss_mean_error_share_m']:8.3f} "
                  f"{row['mae_16-32_photons_m']:7.3f} {row['moved_target_mae_m']:6.3f}")


if __name__ == "__main__":
    main()
