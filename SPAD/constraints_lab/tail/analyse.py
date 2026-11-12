"""Tail of the three reference circuits: percentiles, breakdown, causes, histogram-peak comparison.

Run from SPAD/:
  ../.venv/bin/python -m constraints_lab.slot -- ../.venv/bin/python -m constraints_lab.tail.analyse
"""
import json

import torch

from spad.dataset.photons import photon_histogram
from spad.dataset.prepare import BIN_METERS
from spad.core.stream_model import simulate_stream
from spad.training.baselines import box_peak, peak
from spad.training.train_stream import Validator

from constraints_lab.tail.common import (CONDITIONS, ONE_METRE_BINS, OUT, REFERENCES, load_circuit, setup,
                                         tail_stats)


def full_histogram_context(histograms, targets):
    """Per pixel, from the whole capture histogram: background per bin and the signal share at the label."""
    h = histograms.double()
    background = h.median(1).values
    bins = torch.arange(h.shape[1])[None]
    near = ((bins - targets[:, None]).abs() <= 5)
    signal = (h*near).sum(1) - background*11
    return background, (signal.clamp_min(0)/h.sum(1).clamp_min(1)), box_peak(histograms, 8)


def excess_at(histograms, background, positions, half=2):
    """Significance of the full-histogram counts in a 5-bin window around each position over background."""
    bins = torch.arange(histograms.shape[1])[None]
    window = ((bins - positions[:, None].round()).abs() <= half)
    counts = (histograms.double()*window).sum(1)
    expected = background*(2*half+1)
    return (counts - expected)/(expected + 1).sqrt()


def main():
    torch.set_num_threads(1)
    train, routing, validation, police = setup()
    validator = Validator(train, validation[:2], CONDITIONS, 3, police, seed=1234)
    sets = len(validator.targets)//len(validation[1])
    histograms = validation[0].repeat(sets, 1)
    clean = validation[2].repeat(sets)
    targets = validator.targets.float()
    background, signal_share, full_peak = full_histogram_context(histograms, validator.targets)
    full_peak_miss = (full_peak - targets).abs() > ONE_METRE_BINS
    expected_signal = validator.counts.double()*(1 - validator.background.double())*signal_share

    # Histogram-peak readers on the very same photons: they see all photons at once.
    small = photon_histogram(validator.photons)
    fit_small = photon_histogram(validator.fit_photons)
    readers = {}
    for name, read in (("peak", peak), ("box8_peak", lambda x: box_peak(x, 8))):
        offset = float((read(fit_small) - validator.fit_targets).median())
        readers[name] = read(small) - offset

    rows = {}
    for name, path in REFERENCES.items():
        circuit = load_circuit(path)
        audit = validator.audit(circuit)
        raw = simulate_stream(circuit, validator.photons).float()
        prediction = raw - validator.offset(circuit)
        rows[name] = {"audit": audit, "prediction": prediction}
    rows.update({name: {"prediction": p} for name, p in readers.items()})

    buckets = {}
    for low, high in ((16, 32), (32, 64), (64, 128), (128, 257)):
        buckets[f"photons_{low}-{min(high, 256)}"] = (validator.counts >= low) & (validator.counts < high)
    for low, high in ((0, .2), (.2, .4), (.4, 1.01)):
        buckets[f"extra_bg_{low}-{min(high, .6)}"] = (validator.background >= low) & (validator.background < high)
    for low, high in ((0, 4), (4, 8), (8, 16), (16, 32), (32, 1e9)):
        buckets[f"exp_signal_photons_{low}-{high if high < 1e9 else 'inf'}"] = (expected_signal >= low) & (expected_signal < high)
    metres = targets*BIN_METERS
    for low, high in ((0, 10), (10, 20), (20, 30), (30, 80)):
        buckets[f"range_{low}-{high}m"] = (metres >= low) & (metres < high)
    buckets["label_clean"] = clean
    buckets["label_not_clean"] = ~clean
    buckets["full_histogram_peak_within_1m_of_label"] = ~full_peak_miss
    buckets["full_histogram_peak_off_by_over_1m"] = full_peak_miss

    result = {"rays": len(targets), "sets": sets, "share_clean": float(clean.float().mean()),
              "share_full_peak_off_1m": float(full_peak_miss.float().mean()), "circuits": {}}
    for name, row in rows.items():
        prediction = row["prediction"]
        error = prediction - targets
        big = error.abs() > ONE_METRE_BINS
        entry = {"overall": tail_stats(error), "buckets": {}}
        if "audit" in row:
            entry["audit"] = row["audit"]
        for bucket, keep in buckets.items():
            entry["buckets"][bucket] = {"share_of_rays": float(keep.float().mean()), **tail_stats(error[keep]),
                                        "share_of_big_misses": float((big & keep).sum()/big.sum().clamp_min(1))}
        # Causes of the >1 m misses (mutually exclusive, first match wins).
        significance = excess_at(histograms, background, prediction)
        box_misses = (readers["box8_peak"] - targets).abs() > ONE_METRE_BINS
        causes = {
            "label_not_clean": ~clean,
            "full_histogram_strongest_return_elsewhere": clean & full_peak_miss,
            "on_second_return": clean & ~full_peak_miss & (significance > 5),
            "on_background": clean & ~full_peak_miss & (significance <= 5),
        }
        entry["causes_of_over_1m"] = {k: float((big & v).sum()/big.sum().clamp_min(1)) for k, v in causes.items()}
        entry["over_1m_where_box8_peak_on_same_photons_also_misses"] = float((big & box_misses).sum()/big.sum().clamp_min(1))
        entry["over_1m_where_box8_peak_on_same_photons_is_right"] = float((big & ~box_misses).sum()/big.sum().clamp_min(1))
        # Signed: early (before label) or late misses
        entry["over_1m_early_share"] = float((big & (error < 0)).sum()/big.sum().clamp_min(1))
        entry["over_1m_with_prediction_at_bin_0"] = float((big & (prediction + 0 <= 1)).sum()/big.sum().clamp_min(1))
        # Tail if the circuit matched box8 wherever box8 is right (a reachable floor with these photons)
        result["circuits"][name] = entry
    # Floor: a circuit that never misses by >1 m where box8 on the same photons is right.
    for name in REFERENCES:
        error = rows[name]["prediction"] - targets
        box_error = readers["box8_peak"] - targets
        # Only the circuit's >1 m misses are replaced, and only where box8 on the same photons is within 1 m.
        fixable = (error.abs() > ONE_METRE_BINS) & (box_error.abs() <= ONE_METRE_BINS)
        floor = torch.where(fixable, box_error.abs(), error.abs())
        result["circuits"][name]["if_fixed_wherever_box8_is_right"] = tail_stats(floor)
        far = metres >= 20
        result["circuits"][name]["labels_beyond_20m"] = {
            "rays": int(far.sum()), "clean": int((far & clean).sum()),
            "share_of_squared_error": float((error[far]**2).sum()/(error**2).sum()),
            "without_them": tail_stats(error[~far])}
        oracle = torch.minimum(error.abs(), box_error.abs())
        result["circuits"][name]["best_of_circuit_and_box8"] = tail_stats(oracle)
    clean_only = {name: tail_stats((row["prediction"] - targets)[clean]) for name, row in rows.items()}
    result["clean_labels_only"] = clean_only
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT/"analysis.json").write_text(json.dumps(result, indent=1)+"\n")

    def show(title, keys):
        print(f"\n{title}")
        print(f"{'bucket':44s}" + "".join(f"{n[:14]:>16s}" for n in rows))
        for key in keys:
            share = result["circuits"]["final_design"]["buckets"][key]["share_of_rays"]
            cells = "".join(f"{result['circuits'][n]['buckets'][key]['over_1m']:7.3f}/{result['circuits'][n]['buckets'][key]['p90_m']:6.2f}m "
                            for n in rows)
            print(f"{key:36s} {share:6.3f}  {cells}")
    print("overall:")
    for name in rows:
        print(f"  {name:24s}", {k: round(v, 3) for k, v in result["circuits"][name]["overall"].items()})
    show("over_1m / p90 by bucket", list(buckets))
    for name in REFERENCES:
        e = result["circuits"][name]
        print(f"\n{name}: causes {json.dumps({k: round(v, 3) for k, v in e['causes_of_over_1m'].items()})}")
        print(f"  box8 also misses: {e['over_1m_where_box8_peak_on_same_photons_also_misses']:.3f}, early share {e['over_1m_early_share']:.3f}")
        print("  if fixed where box8 right:", {k: round(v, 3) for k, v in e["if_fixed_wherever_box8_is_right"].items()})
        far = e["labels_beyond_20m"]
        print(f"  labels >= 20 m: {far['rays']} rays ({far['clean']} clean), share of squared error "
              f"{far['share_of_squared_error']:.2f}; without them", {k: round(v, 3) for k, v in far["without_them"].items()})
    print("\nclean labels only:", json.dumps({n: {k: round(v, 3) for k, v in s.items()} for n, s in clean_only.items()}, indent=0))


if __name__ == "__main__":
    main()
