"""Run the frozen Boolean circuit and save a metric range map for a capture."""
import argparse
from pathlib import Path

import numpy as np
import torch

from spad import ROOT
from spad.core.model import Config, RecurrentLogic
from spad.dataset.prepare import BIN_METERS
from spad.pilot.train import choose_device


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("checkpoint", type=Path)
    parser.add_argument("--capture", type=int, default=7)
    parser.add_argument("--data", type=Path, default=ROOT / "data")
    parser.add_argument("--out", type=Path, default=ROOT / "runs/prediction.npz")
    parser.add_argument("--batch-size", type=int, default=32)
    parser.add_argument("--device", choices=("cpu", "mps", "cuda", "auto"), default="cpu")
    parser.add_argument("--full-frame", action="store_true",
                        help="Use all valid raw pixels instead of the prepared labelled-ray subset")
    args = parser.parse_args()
    torch.set_num_threads(2)
    checkpoint = torch.load(args.checkpoint, map_location="cpu", weights_only=False)
    config = Config(**checkpoint["config"])
    device = choose_device(args.device)
    model = RecurrentLogic(config).to(device)
    model.load_state_dict(checkpoint["model"])
    bin_offset = checkpoint["data_metadata"]["bin_offset"]
    if args.full_frame:
        histograms = np.loadtxt(args.data / "raw/DepthEstimate/Histogram" / f"{args.capture}.txt", dtype=np.int32)
        offsets = np.loadtxt(args.data / "raw/config/offset.txt")
        if histograms.shape != (49152, config.bins) or offsets.shape != (49152,):
            raise ValueError("Unexpected raw histogram or calibration shape")
        indices = np.flatnonzero((offsets < 10) & (histograms.sum(-1) > 0))
        histograms, offsets = histograms[indices], offsets[indices]
    else:
        with np.load(args.data / "processed" / f"{args.capture}.npz") as data:
            histograms = data["histograms"].astype(np.int32)
            offsets, indices = data["pixel_offsets"], data["pixel_indices"]
    predicted_bins, ties = [], []
    with torch.no_grad():
        for start in range(0, len(histograms), args.batch_size):
            hist = torch.from_numpy(histograms[start:start+args.batch_size]).to(device)
            scores = model(hist, hard=True)
            predicted_bins.append(scores.argmax(-1).cpu().numpy())
            ties.append(((scores == scores.max(-1, keepdim=True).values).sum(-1) > 1).cpu().numpy())
    bins = np.concatenate(predicted_bins)
    ranges = (bins-bin_offset)*BIN_METERS-offsets
    depth_map = np.full(49152, np.nan, dtype=np.float32)
    depth_map[indices] = ranges
    args.out.parent.mkdir(parents=True, exist_ok=True)
    np.savez(args.out, range_m=depth_map.reshape(192, 256), pixel_indices=indices,
             predicted_bins=bins, score_ties=np.concatenate(ties),
             physically_positive=ranges > 0, source_checkpoint=str(args.checkpoint))
    print(f"Saved {len(indices)} predictions to {args.out}")


if __name__ == "__main__":
    main()
