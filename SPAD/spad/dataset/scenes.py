"""Add multi-view Reconstruction scenes as extra labelled captures, split by scene.

The depth track has only 10 captures. Each Reconstruction scene holds 20-40 more
views from the same SPL device, each with a full 672-bin histogram map and the
matching Livox cloud ({view}.csv), the same format as the depth track. Views are
labelled with the frozen intrinsics from calibration.py (fitted on captures 1-4).

A whole scene goes to one split, so no scene is in both training and evaluation.
Each histogram map is decompressed from the zip, reduced to a ray sample and
discarded, so the 67 MB text files never reach disk.

Pairing comes from each scene's sp_pose_results.csv (checked: each map aligns best
with its own cloud, not its neighbours). Every view reports
its median |histogram peak - label| on edge-free pixels; a view above
--max-label-error is dropped and listed in the metadata.
"""
import argparse
import csv
import io
import json
from pathlib import Path
import warnings
import zipfile

import numpy as np

from spad import ROOT
from spad.dataset.calibration import NAMES, edge_free, project
from spad.dataset.download import DATASET, HF, fetch, get_json, usage
from spad.dataset.prepare import BIN_METERS

# Scene -> split. parking (outdoor) is a held-out scene: never used for design decisions.
# AI_floor2 is excluded: its Livox labels are spatially misaligned under the frozen
# calibration (0.5-0.7 m median, not a timing shift), and fixing that would mean
# calibrating on a test scene's own labels.
SCENES = {"library_floor2": "train", "c4floor2": "train", "material_building": "train",
          "design_floor1": "architecture", "parking": "scene_test"}
PIXELS, BINS = 49152, 672


def parse_histograms(raw):
    """Fast whitespace parse of a 49152 x 672 integer text map."""
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", DeprecationWarning)
        values = np.fromstring(raw, dtype=np.int64, sep=" ")
    if values.size != PIXELS * BINS:
        raise ValueError(f"Histogram map has {values.size} values, expected {PIXELS * BINS}")
    if values.max() > np.iinfo(np.uint16).max or values.min() < 0:
        raise ValueError("Photon counts do not fit losslessly in uint16")
    return values.reshape(PIXELS, BINS).astype(np.uint16)


def view_pairs(archive, scene):
    """(view id, histogram member, csv member) from the scene's pose file.

    sp_pose_results.csv names the Livox cloud matched to each histogram map; some
    scenes have an extra cloud, so ordering alone cannot pair them.
    """
    names = archive.namelist()
    pose = next(n for n in names if n.endswith("sp_pose_results.csv"))
    rows = csv.DictReader(io.StringIO(archive.read(pose).decode()))
    by_file = {Path(n).name: n for n in names}
    pairs = []
    for row in rows:
        hist, cloud = by_file.get(row["sp_file"]), by_file.get(row["livox_csv_name"])
        if hist is None or cloud is None:
            raise ValueError(f"{scene}: pose file names a missing file in row {row['sp_seq']}")
        pairs.append((int(Path(cloud).stem), hist, cloud))
    if len({p[0] for p in pairs}) != len(pairs):
        raise ValueError(f"{scene}: a point cloud is paired with two histogram maps")
    return sorted(pairs)


def process_view(archive, hist_member, csv_member, calibration, transform, offset, args, seed):
    hist = parse_histograms(archive.read(hist_member))
    with archive.open(csv_member) as handle:
        points = np.loadtxt(handle, delimiter=",", skiprows=1, usecols=(8, 9, 10))
    depth = project(points, transform, calibration)
    target = (depth + np.where(offset < 10, offset, 0)) / BIN_METERS + args.bin_offset
    valid = (np.isfinite(depth) & (depth > 0.1) & (depth <= args.max_range) & (offset < 10)
             & (target >= 0) & (target <= BINS - 1) & (hist.sum(1) > 0))
    candidates = np.flatnonzero(valid)
    if len(candidates) < 32:
        return None, {"valid_projected_rays": int(valid.sum()), "dropped": "too few labelled rays"}
    error = np.abs(hist[candidates].argmax(1) - target[candidates]) * BIN_METERS
    edges_ok = edge_free(depth)
    clean_error = error[edges_ok[candidates]]
    rng = np.random.default_rng(seed)
    indices = np.sort(rng.choice(candidates, min(args.rays_per_view, len(candidates)), replace=False))
    clean = edges_ok[indices]
    payload = dict(histograms=hist[indices], target_bins=target[indices].astype(np.float32),
                   ranges=depth[indices].astype(np.float32), pixel_indices=indices.astype(np.int32),
                   pixel_offsets=offset[indices].astype(np.float32))
    labels = dict(target_bins=target[indices].astype(np.float32), labelled=np.ones(len(indices), bool), clean=clean)
    info = {"valid_projected_rays": int(valid.sum()), "selected_rays": len(indices),
            # Judged on edge-free pixels: cluttered scenes have many depth edges, where a
            # one-pixel projection error is large but those rays are excluded from training.
            "label_median_m": float(np.median(clean_error)) if len(clean_error) else float("inf"),
            "label_median_all_m": float(np.median(error)), "clean_fraction": float(edges_ok[candidates].mean()),
            "peak_baseline_mae_m": float(error.mean()),
            "peak_baseline_recall_3_bins": float((error <= 3 * BIN_METERS).mean())}
    return (payload, labels), info


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--root", type=Path, default=ROOT / "data")
    parser.add_argument("--scenes", nargs="+", default=list(SCENES), choices=list(SCENES))
    parser.add_argument("--rays-per-view", type=int, default=2500)
    parser.add_argument("--max-range", type=float, default=30.)
    parser.add_argument("--bin-offset", type=float, default=17.)
    parser.add_argument("--max-label-error", type=float, default=0.2,
                        help="Drop a view whose median |peak - label| on edge-free pixels exceeds this (m)")
    parser.add_argument("--budget-bytes", type=int, default=2_400_000_000)
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()
    root = args.root.resolve()
    manifest_path, metadata_path = root / "manifest.json", root / "processed/metadata.json"
    manifest, metadata = json.loads(manifest_path.read_text()), json.loads(metadata_path.read_text())
    manifest["budget_bytes"] = args.budget_bytes
    report = json.loads((root / "processed/calibration_report.json").read_text())
    calibration = [report["refined"][name] for name in NAMES]
    raw = root / "raw"
    transform = np.loadtxt(raw / "config/final_extrinsic_sp_to_livox.txt")
    offset = np.loadtxt(raw / "config/offset.txt").reshape(-1)
    rev = manifest["dataset_revision"]
    tree = {Path(x["path"]).name: x for x in get_json(f"{HF}/api/datasets/{DATASET}/tree/{rev}/Reconstruction")}
    scene_splits = manifest.setdefault("scene_splits", {})
    for scene in args.scenes:
        item = tree[f"{scene}.zip"]
        url = f"{HF}/datasets/{DATASET}/resolve/{rev}/Reconstruction/{scene}.zip"
        path = raw / "Reconstruction" / f"{scene}.zip"
        digest = fetch(url, path, root, args.budget_bytes, item.get("lfs", {}).get("oid"))
        manifest["files"][f"raw/Reconstruction/{scene}.zip"] = {"url": url, "sha256": digest}
        scene_splits[scene] = SCENES[scene]
        manifest_path.write_text(json.dumps(manifest, indent=2) + "\n")
        with zipfile.ZipFile(path) as archive:
            pairs = view_pairs(archive, scene)
            dropped = {}
            for view, hist_member, csv_member in pairs:
                capture = f"{scene}-{view:02d}"
                reserve = args.rays_per_view * (BINS * 2 + 32) + 200_000
                if usage(root) + reserve > args.budget_bytes:
                    raise RuntimeError("Not enough room within the data budget")
                result, info = process_view(archive, hist_member, csv_member, calibration, transform,
                                            offset, args, args.seed + view + 1000 * len(scene))
                if result is None or info["label_median_m"] > args.max_label_error:
                    dropped[capture] = info.get("dropped") or f"label median {info['label_median_m']:.3f} m"
                    print(f"{capture}: dropped ({dropped[capture]})", flush=True)
                    continue
                payload, labels = result
                np.savez_compressed(root / "processed" / f"{capture}.npz", **payload)
                np.savez_compressed(root / "processed" / f"labels_{capture}.npz", **labels)
                metadata["captures"][capture] = {"split": SCENES[scene], "scene": scene, "view": view, **info}
                print(f"{capture} {SCENES[scene]}: {info['selected_rays']} rays, label median "
                      f"{info['label_median_m']:.3f} m", flush=True)
        previous = metadata.setdefault("dropped_views", {})
        for key in [k for k in previous if k.startswith(scene + "-")]:
            del previous[key]   # a rerun replaces this scene's record
        previous.update(dropped)
        metadata["storage_bytes"] = usage(root)
        metadata_path.write_text(json.dumps(metadata, indent=2) + "\n")
    manifest["downloaded_bytes"] = usage(root)
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n")
    print(f"Storage: {usage(root):,} / {args.budget_bytes:,} bytes", flush=True)


if __name__ == "__main__":
    main()
