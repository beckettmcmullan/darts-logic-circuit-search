"""Score circuits and baselines under test-time sensor perturbations (validation split only).

The clean photons are exactly the standard ones: the same draws as
Validator(train, validation, (16, 256, 0.6), 3, seed=1234). Each perturbation is then applied
to those same photons (paired), with its own fixed generator, labels unchanged.

Two calibrations are reported for every case:
- factory: the constant offset fitted on clean training photons (what a chip calibrated on the
  bench, then used with a different sensor, would have). Shows the full damage.
- recalibrated: the offset refitted on perturbed training photons. What is left is accuracy that
  a constant calibration cannot buy back.

Usage (from SPAD/): ../.venv/bin/python -m constraints_lab.slot -- ../.venv/bin/python -m
constraints_lab.sensor.evaluate --out runs/2026-11-11_constraints-lab/sensor/eval-references
"""
import argparse
import json
from pathlib import Path
import time

import torch

from spad import ROOT
from spad.dataset.photons import load_rays, photon_histogram, sample_conditions
from spad.training.baselines import box_peak, metrics
from spad.core.stream_model import StreamConfig, pack_circuit, rule_circuit, simulate_population_packed, simulate_stream
from constraints_lab.sensor.perturb import apply

AREA = ROOT/"runs/2026-11-11_local-cpu_area-objective"
REFERENCES = {
    "final_design": ROOT/"runs/2026-11-10_kaggle-t4_batch3_fused-larger-search/random-s4-seed0/circuit.json",
    "area_tol5": AREA/"final-design-tol5/circuit.json",
    "search_end_20um2": AREA/"final-design-tol5_no-recheck/search_end_circuit.json",
}
VARIANTS = ["clean", "jitter:0.5", "jitter:1", "jitter:2", "jitter:4", "pileup:2", "pileup:4", "pileup:8",
            "pileup:2+jitter:1", "pileup:4+jitter:2", "bits:0.001", "bits:0.01", "bits:0.01@0", "bits:0.01@9"]
BUCKETS = ((16, 32), (32, 64), (64, 128), (128, 257))


class Streams:
    """Standard validation and offset-fit photons, plus what is needed to perturb them."""
    def __init__(self, train, validation, conditions=(16, 256, .6), sets=3, seed=1234):
        generator = torch.Generator().manual_seed(seed)       # same order of draws as Validator
        pick = torch.randperm(len(train[1]), generator=generator)[:8000]
        self.fit_targets, self.fit_histograms = train[1][pick], train[0][pick]
        self.fit_photons, _, self.fit_background = sample_conditions(self.fit_histograms, *conditions, generator)
        draws = [sample_conditions(validation[0], *conditions, generator) for _ in range(sets)]
        self.photons, self.counts, self.background = (torch.cat(x) for x in zip(*draws))
        self.targets = validation[1].repeat(sets)
        self.histograms = validation[0].repeat(sets, 1)

    def perturbed(self, spec, seed):
        generator = torch.Generator().manual_seed(seed)
        return (apply(spec, self.photons, self.histograms, self.background, generator),
                apply(spec, self.fit_photons, self.fit_histograms, self.fit_background, generator))


def run_circuits(circuits, photons):
    """Final candidates of every circuit, [circuits, rays], with the packed exact simulator."""
    config = StreamConfig(**next(iter(circuits.values()))["config"])
    packed = [pack_circuit(c) for c in circuits.values()]
    inputs, codes = torch.stack([p[0] for p in packed]), torch.stack([p[1] for p in packed])
    out = []
    for start in range(0, len(photons), 8192):
        out.append(simulate_population_packed(config, inputs, codes, photons[start:start+8192]).float())
    return dict(zip(circuits, torch.cat(out, 1)))


def peak_baselines(photons):
    histogram = photon_histogram(torch.where(photons < 672, photons, -1))    # a 672-bin counter drops >671
    return {"peak": histogram.argmax(-1).float(), "box8": box_peak(histogram, 8)}


def score(raw, fit_raw, fit_raw_clean, streams, clean_signed=None):
    offset = float((fit_raw_clean - streams.fit_targets).median())
    refit = float((fit_raw - streams.fit_targets).median())
    prediction = raw - offset
    signed = prediction - streams.targets
    row = {"factory": metrics(prediction, streams.targets), "recalibrated": metrics(raw - refit, streams.targets),
           "offset_bins": offset, "refit_offset_bins": refit, "offset_change_bins": refit - offset,
           "median_signed_bins": float(signed.median())}
    for low, high in BUCKETS:
        keep = (streams.counts >= low) & (streams.counts < high)
        row[f"signed_photons_{low}-{min(high, 256)}"] = float(signed[keep].median())
    edges = torch.quantile(streams.targets.float(), torch.tensor([1/3, 2/3]))
    third = torch.bucketize(streams.targets.float(), edges)
    for i, name in enumerate(("near", "mid", "far")):
        row[f"signed_range_{name}"] = float(signed[third == i].median())
        row[f"mae_range_{name}_m"] = metrics(prediction[third == i], streams.targets[third == i])["mae_m"]
    return row


def time_shift(circuit, photons, raw, shift=24):
    latest = photons.max(1).values
    movable = (latest + shift < 672) & (latest >= 0)
    moved = torch.where(photons >= 0, photons + shift, photons)[movable]
    change = simulate_stream(circuit, moved).float() - raw[movable]
    return float(((change - shift).abs() <= 1).float().mean())


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data", type=Path, default=ROOT/"data")
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--circuit", action="append", default=[], help="name=path, extra circuits to score")
    parser.add_argument("--no-references", action="store_true")
    parser.add_argument("--variants", nargs="*", default=VARIANTS)
    parser.add_argument("--seed", type=int, default=1234, help="standard photon draws (1234 = audit)")
    parser.add_argument("--perturb-seed", type=int, default=50)
    parser.add_argument("--time-shift", action="store_true", help="also run the time-shift test per variant")
    parser.add_argument("--threads", type=int, default=1)
    args = parser.parse_args()
    torch.set_num_threads(args.threads)
    started = time.monotonic()
    args.out.mkdir(parents=True, exist_ok=True)
    train = load_rays(args.data, "train", clean_only=True)[:2]
    validation = load_rays(args.data, "validation")[:2]
    streams = Streams(train, validation, seed=args.seed)
    circuits = {} if args.no_references else {k: json.loads(v.read_text()) for k, v in REFERENCES.items()}
    for item in args.circuit:
        name, path = item.split("=", 1)
        circuits[name] = json.loads(Path(path).read_text())
    if not args.no_references:
        circuits["rule_w8"] = rule_circuit(StreamConfig(**circuits["final_design"]["config"]))
    # The packed population simulator must agree with the integer reference.
    check = streams.photons[:512]
    for name, c in circuits.items():
        assert torch.equal(run_circuits({name: c}, check)[name], simulate_stream(c, check).float()), name
    clean_fit = {**run_circuits(circuits, streams.fit_photons), **peak_baselines(streams.fit_photons)}
    results = {}
    for index, spec in enumerate(args.variants):
        photons, fit_photons = (streams.photons, streams.fit_photons) if spec == "clean" else \
            streams.perturbed(spec, args.perturb_seed + index)
        raw = {**run_circuits(circuits, photons), **peak_baselines(photons)}
        fit_raw = {**run_circuits(circuits, fit_photons), **peak_baselines(fit_photons)}
        results[spec] = {}
        for name in raw:
            row = score(raw[name], fit_raw[name], clean_fit[name], streams)
            if args.time_shift and name in circuits:
                row["time_shift_within_1_bin"] = time_shift(circuits[name], photons, raw[name])
            results[spec][name] = row
        print(f"[{time.monotonic() - started:.0f} s] {spec}", flush=True)
        for name, row in results[spec].items():
            f, r = row["factory"], row["recalibrated"]
            print(f"  {name:18s} MAE {f['mae_m']:.3f} med {f['median_m']:.3f} r3 {f['recall_3_bins']:.3f} "
                  f"signed {row['median_signed_bins']:+.1f} | recal MAE {r['mae_m']:.3f} r3 {r['recall_3_bins']:.3f} "
                  f"| photons " + " ".join(f"{row[f'signed_photons_{a}-{min(b, 256)}']:+.1f}" for a, b in BUCKETS)
                  + " | range " + " ".join(f"{row[f'signed_range_{n}']:+.1f}" for n in ("near", "mid", "far")), flush=True)
    for spec in results:
        for name, row in results[spec].items():
            base = results.get("clean", {}).get(name)
            if base:
                row["shift_vs_clean_bins"] = row["median_signed_bins"] - base["median_signed_bins"]
                row["mae_change_factory_m"] = row["factory"]["mae_m"] - base["factory"]["mae_m"]
                row["mae_change_recalibrated_m"] = row["recalibrated"]["mae_m"] - base["factory"]["mae_m"]
    (args.out/"results.json").write_text(json.dumps({"seed": args.seed, "perturb_seed": args.perturb_seed,
                                                     "circuits": list(circuits), "results": results,
                                                     "seconds": time.monotonic() - started}, indent=2)+"\n")


if __name__ == "__main__":
    main()
