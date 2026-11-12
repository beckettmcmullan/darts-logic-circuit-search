"""Project independent Livox ranges into the SPL grid and select labelled rays."""
import argparse
import json
from pathlib import Path

import numpy as np

from spad import ROOT
from spad.dataset.download import usage

BIN_METERS = 299_792_458 * 750e-12 / 2
INTRINSICS = {
    "p1": dict(fx=120.940059132687, fy=121.125671532013,
               cx=130.412638624449, cy=97.1258022886799),
    "p2": dict(fx=118.6514575329715, fy=118.7964934010577,
               cx=130.6802784645003, cy=100.360570246814),
}


def project_ranges(points, sp_to_livox, intrinsics, k1, k2, width=256, height=192):
    """Inverse raw-to-raw extrinsic then forward radial distortion + range z-buffer.

    No interpolation or label filling. A pixel is labelled only if a reference
    return projects into it. Nearest positive range handles multiple returns.
    """
    points = np.asarray(points, dtype=np.float64)
    good = np.isfinite(points).all(1) & (np.linalg.norm(points, axis=1) > 0)
    points = points[good]
    inverse = np.linalg.inv(sp_to_livox)
    sp = points @ inverse[:3, :3].T + inverse[:3, 3]
    sp = sp[sp[:, 2] > 0]
    ranges = np.linalg.norm(sp, axis=1)
    x, y = sp[:, 0] / sp[:, 2], sp[:, 1] / sp[:, 2]
    r2 = x*x + y*y
    radial = 1 + k1*r2 + k2*r2*r2
    u = intrinsics["fx"] * x * radial + intrinsics["cx"]
    v = intrinsics["fy"] * y * radial + intrinsics["cy"]
    good = (np.isfinite(u) & np.isfinite(v) & (u >= -0.5) & (u < width-0.5)
            & (v >= -0.5) & (v < height-0.5))
    indices = np.rint(v[good]).astype(int)*width + np.rint(u[good]).astype(int)
    depth = np.full(width*height, np.inf)
    np.minimum.at(depth, indices, ranges[good])
    return depth


def load_intrinsics(path, device):
    # The small released YAML only needs scalar calibration values; avoid a new dependency.
    active = False
    values = {}
    for line in path.read_text().splitlines():
        if line.strip() == device + ":":
            active = True
            continue
        if active and line.startswith("  ") and not line.startswith("    "):
            break
        if active and ":" in line:
            key, value = line.strip().split(":", 1)
            values[key] = float(value)
    if not all(key in values for key in ("fx", "fy", "cx", "cy", "k1", "k2")):
        raise ValueError("Missing calibration values")
    if values.get("p1", 0) or values.get("p2", 0):
        raise ValueError("Nonzero tangential distortion requires extending projection")
    return values


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT / "data")
    parser.add_argument("--device-calibration", choices=INTRINSICS, default="p2")
    parser.add_argument("--max-rays", type=int, default=6000)
    parser.add_argument("--max-range", type=float, default=30.)
    parser.add_argument("--bin-offset", type=float, default=17.)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--captures", type=int, nargs="+",
                        help="Only process these captures, keeping existing prepared files")
    args = parser.parse_args()
    if args.max_rays <= 0:
        raise ValueError("max-rays must be positive")
    root = args.root.resolve()
    manifest = json.loads((root / "manifest.json").read_text())
    raw = root / "raw"
    calibration = load_intrinsics(raw / "config/config.yaml", args.device_calibration)
    transform = np.loadtxt(raw / "config/final_extrinsic_sp_to_livox.txt")
    offset = np.loadtxt(raw / "config/offset.txt").reshape(-1)
    if offset.shape != (49152,) or transform.shape != (4, 4):
        raise ValueError("Unexpected calibration dimensions")
    out = root / "processed"
    out.mkdir(exist_ok=True)
    metadata = {"calibration": args.device_calibration, "calibration_values": calibration,
                "calibration_status": "p2 is the upstream raw2pc default; depth-track device identity is unconfirmed",
                "bin_offset": args.bin_offset, "bin_meters": BIN_METERS,
                "max_range": args.max_range, "seed": args.seed, "max_rays": args.max_rays,
                "label_source": "Livox reference projected with inverse SPL-to-Livox extrinsic",
                "split_unit": "capture id (custom research split, not official benchmark protocol)",
                "captures": {}, "dataset_revision": manifest["dataset_revision"]}
    previous = json.loads((out / "metadata.json").read_text()) if (out / "metadata.json").exists() else {}
    if args.captures:
        metadata["captures"] = previous["captures"]
    else:
        # Keep Reconstruction views added by scenes.py; only depth captures are rebuilt here.
        metadata["captures"] = {k: v for k, v in previous.get("captures", {}).items() if not k.isdigit()}
    if "dropped_views" in previous:
        metadata["dropped_views"] = previous["dropped_views"]
    for split, ids in manifest["splits"].items():
        for capture in ids:
            if args.captures and capture not in args.captures:
                if str(capture) in metadata["captures"]:
                    metadata["captures"][str(capture)]["split"] = split
                continue
            # The maximum new npz payload is bounded before reading/allocating.
            path = out / f"{capture}.npz"
            reserve = args.max_rays * (672*2 + 12) + 100_000
            if usage(root) + reserve > manifest["budget_bytes"]:
                raise RuntimeError("Not enough room for preprocessing within data budget")
            hist = np.loadtxt(raw / f"DepthEstimate/Histogram/{capture}.txt", dtype=np.uint32)
            if hist.shape != (49152, 672):
                raise ValueError(f"Unexpected histogram shape {hist.shape}")
            if hist.max() > np.iinfo(np.uint16).max:
                raise ValueError("Photon counts do not fit losslessly in uint16")
            points = np.loadtxt(raw / f"DepthEstimate/gt/{capture}.csv", delimiter=",",
                                skiprows=1, usecols=(8, 9, 10))
            ranges = project_ranges(points, transform, calibration, calibration["k1"], calibration["k2"])
            target_bin = (ranges + np.where(offset < 10, offset, 0)) / BIN_METERS + args.bin_offset
            valid = (np.isfinite(ranges) & (ranges > 0.1) & (ranges <= args.max_range)
                     & (offset < 10) & (target_bin >= 0) & (target_bin <= 671)
                     & (hist.sum(1) > 0))
            indices = np.flatnonzero(valid)
            if len(indices) < 32:
                raise RuntimeError(f"Only {len(indices)} reference-labelled rays in capture {capture}; check calibration")
            rng = np.random.default_rng(args.seed + capture)
            indices = np.sort(rng.choice(indices, min(args.max_rays, len(indices)), replace=False))
            selected = hist[indices].astype(np.uint16)
            targets = target_bin[indices].astype(np.float32)
            peak_error = np.abs(selected.argmax(1) - targets) * BIN_METERS
            np.savez(path, histograms=selected, target_bins=targets,
                     ranges=ranges[indices].astype(np.float32), pixel_indices=indices.astype(np.int32),
                     pixel_offsets=offset[indices].astype(np.float32))
            metadata["captures"][str(capture)] = {
                "split": split, "valid_projected_rays": int(valid.sum()), "selected_rays": len(indices),
                "peak_baseline_mae_m": float(peak_error.mean()),
                "peak_baseline_median_m": float(np.median(peak_error)),
                "peak_baseline_recall_3_bins": float((peak_error <= 3*BIN_METERS).mean())}
            print(f"capture {capture} {split}: {len(indices)} rays, "
                  f"peak median error {np.median(peak_error):.3f} m", flush=True)
            del hist, selected, points
    metadata["storage_bytes"] = usage(root)
    (out / "metadata.json").write_text(json.dumps(metadata, indent=2) + "\n")
    if usage(root) > manifest["budget_bytes"]:
        raise RuntimeError("Data budget exceeded")
    print(f"Data storage: {usage(root):,} / {manifest['budget_bytes']:,} bytes", flush=True)


if __name__ == "__main__":
    main()
