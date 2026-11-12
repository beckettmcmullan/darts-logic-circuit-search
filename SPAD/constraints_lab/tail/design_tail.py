"""What are the gross misses (>3 m) in the design splits the search scores on?

Run from SPAD/:
  ../.venv/bin/python -m constraints_lab.slot -- ../.venv/bin/python -m constraints_lab.tail.design_tail
"""
import json

import torch

from spad.core.stream_model import simulate_stream
from spad.dataset.photons import load_rays, photon_histogram, sample_conditions
from spad.dataset.prepare import BIN_METERS
from spad.training.baselines import box_peak
from spad import ROOT

from constraints_lab.tail.common import CONDITIONS, OUT, REFERENCES, ONE_METRE_BINS, THREE_METRE_BINS, load_circuit, tail_stats


def main():
    torch.set_num_threads(1)
    circuit = load_circuit(REFERENCES["final_design"])
    result = {}
    for split in ("train", "architecture", "validation"):
        h, t, clean = load_rays(ROOT/"data", split, clean_only=split != "validation")
        generator = torch.Generator().manual_seed(5)
        pick = torch.randperm(len(t), generator=generator)[:8192]
        h, t, clean = h[pick], t[pick].float(), clean[pick]
        photons = sample_conditions(h, *CONDITIONS, generator)[0]
        raw = simulate_stream(circuit, photons).float()
        error = raw - t
        error = error - error.median()
        box = box_peak(photon_histogram(photons), 8)
        box_error = box - t
        box_error = box_error - box_error.median()
        full = box_peak(h, 8)
        metres = t*BIN_METERS
        gross = error.abs() > THREE_METRE_BINS
        row = {"rays": len(t), "circuit": tail_stats(error), "box8_same_photons": tail_stats(box_error),
               "label_range_m_quantiles": [float(x) for x in torch.quantile(metres, torch.tensor([.01, .1, .5, .9, .99]))],
               "share_labels_beyond_20m": float((metres >= 20).float().mean()),
               "gross": {"share": float(gross.float().mean()),
                         "share_with_label_beyond_20m": float((gross & (metres >= 20)).sum()/gross.sum().clamp_min(1)),
                         "share_where_box8_same_photons_also_gross": float((gross & (box_error.abs() > THREE_METRE_BINS)).sum()/gross.sum().clamp_min(1)),
                         "share_where_full_histogram_box8_within_1m_of_label": float((gross & ((full - t).abs() <= ONE_METRE_BINS)).sum()/gross.sum().clamp_min(1)),
                         "prediction_minus_label_m_quantiles": [float(x) for x in torch.quantile(error[gross]*BIN_METERS, torch.tensor([.1, .5, .9]))] if gross.any() else None,
                         "label_m_quantiles": [float(x) for x in torch.quantile(metres[gross], torch.tensor([.1, .5, .9]))] if gross.any() else None},
               "without_labels_beyond_20m": tail_stats(error[metres < 20]),
               "box8_without_labels_beyond_20m": tail_stats(box_error[metres < 20])}
        # Range tail: does the circuit stop early? Max label it gets within 1 m.
        good = error.abs() <= ONE_METRE_BINS
        row["max_label_m_within_1m"] = float(metres[good].max())
        for low, high in ((0, 10), (10, 20), (20, 40), (40, 80)):
            keep = (metres >= low) & (metres < high)
            if keep.any():
                row[f"range_{low}-{high}m"] = {"share": float(keep.float().mean()), "circuit": tail_stats(error[keep]),
                                               "box8": tail_stats(box_error[keep])}
        result[split] = row
        print(split, json.dumps(row, indent=1))
    (OUT/"design_split_tail.json").write_text(json.dumps(result, indent=1)+"\n")


if __name__ == "__main__":
    main()
