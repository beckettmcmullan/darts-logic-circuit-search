"""Score circuits and histogram methods on large photon samples, on a GPU.

compare_subbin scores about 16,500 streams (the one validation recording, three photon sets, 16-256
photons). This script scores millions: every recording of the design splits (validation, architecture,
train), many photon draws per ray, and photon-count bands far beyond 256. Held-out recordings are never
loaded: only the three design splits are accepted.

Work is split into tasks (split, photon band, draw). `--shard i/n` runs every n-th task, so several
processes (one or two per GPU) share a run; each task writes one small file of sums under <out>/parts/.
`--summarize` then turns the parts into summary.json and summary_table.txt.

Each method's constant offset is fitted once on training recordings at 16-256 photons, as in
compare_subbin, and that same constant is used in every band: a circuit has one calibration constant.
Streams are drawn like training and validation streams: the ray's recorded photons resampled with
replacement, each replaced by uniform background with the ray's own probability (0 to --max-background).
A ray is only used for a band it has enough recorded photons for.
"""
import argparse
import json
from pathlib import Path

import numpy as np
import torch

from training import ROOT
from training.core.stream_model import predict_bins
from training.dataset.photons import photon_histogram, sample_conditions
from training.dataset.prepare import BIN_METERS
from training.training.baselines import box_peak, peak, subbin_fit
from training.training.police import measure_pulse

DESIGN_SPLITS = ("validation", "architecture", "train")       # never scene_test, test or fresh_test
MISS_BINS = 9.                                                  # about 1 m
SHIFT = 300                                                     # moved-target check
HIST_STEP, HIST_BINS = 1/64, 2048                               # |error| histogram: 1/64 bin up to 32 bins


def load_split(root, split):
    """(histograms, target bins, capture index per ray, capture names) of one design split."""
    if split not in DESIGN_SPLITS:
        raise ValueError(f"{split} is not a design split")
    metadata = json.loads((root/"processed/metadata.json").read_text())
    histograms, targets, capture, names = [], [], [], []
    for name, info in metadata["captures"].items():
        if info["split"] != split:
            continue
        with np.load(root/"processed"/f"{name}.npz") as d, np.load(root/"processed"/f"labels_{name}.npz") as labels:
            keep = labels["labelled"]
            histograms.append(d["histograms"][keep].astype(np.int32))
            targets.append(labels["target_bins"][keep])
            capture.append(np.full(int(keep.sum()), len(names), dtype=np.int64))
            names.append(name)
    return (torch.from_numpy(np.concatenate(histograms)), torch.from_numpy(np.concatenate(targets)).float(),
            torch.from_numpy(np.concatenate(capture)), names)


def moved(photons):
    return torch.where(photons >= 0, (photons + SHIFT) % 672, photons)


def methods(circuits, pulse, zero):
    fit = lambda h: subbin_fit(h, pulse.to(h.device), zero)
    table = {"histogram, tallest bar": lambda p: peak(photon_histogram(p)).float(),
             "histogram, 8-bin box": lambda p: box_peak(photon_histogram(p).cpu(), 8).to(p.device),
             "histogram, sub-bin fit": lambda p: fit(photon_histogram(p)).float()}
    for name, circuit in circuits.items():
        table[name] = lambda p, circuit=circuit: predict_bins(circuit, p)
    return table


def tasks(args):
    return [(split, band, draw) for split in args.splits for band in args.bands for draw in range(args.draws)]


def rays_for(args, split, histograms, generator):
    """Rays of a split used by this run: enough recorded photons, then an optional random subsample."""
    keep = torch.nonzero(histograms.sum(1) >= args.min_recorded)[:, 0]
    limit = args.max_rays.get(split, 0)
    if limit and len(keep) > limit:
        keep = keep[torch.randperm(len(keep), generator=generator)[:limit]].sort().values
    return keep


def run(args):
    device = torch.device(args.device)
    circuits = {}
    for item in args.circuits:
        name, path = item.split("=", 1)
        circuits[name] = json.loads(Path(path).read_text())
    train = load_split(args.data, "train")
    pulse, zero = measure_pulse(train[0])
    table = methods(circuits, pulse, zero)

    bright = train[0].sum(1) >= 1024
    full_offset = float((subbin_fit(train[0][bright][:40000], pulse, zero) - train[1][bright][:40000]).median())

    def prepare(data):
        """With --trusted: keep rays whose full-recording fit agrees with the label (as the lowphoton
        benchmark does) and use that fit as the target. Otherwise every labelled ray, scored on its label."""
        if not args.trusted:
            return data
        histograms, labels, capture, names = data
        full = torch.cat([subbin_fit(histograms[i:i + 20000], pulse, zero) for i in range(0, len(labels), 20000)]) - full_offset
        keep = ((full - labels).abs() <= 3.) & (histograms.sum(1) >= 1024)
        return histograms[keep], (labels if args.truth == "label" else full)[keep], capture[keep], names

    train = prepare(train)

    # One calibration constant per method, fitted on training recordings at the usual 16-256 photons.
    generator = torch.Generator().manual_seed(args.seed)
    pick = torch.randperm(len(train[1]), generator=generator)[:8000]
    fit_photons = sample_conditions(train[0][pick], 16, 256, args.max_background, generator)[0].to(device)
    fit_targets = train[1][pick].to(device)
    can_move = fit_targets + SHIFT + 24 < 672
    offsets = {name: float((f(fit_photons) - fit_targets).median()) for name, f in table.items()}
    moved_offsets = {name: float((f(moved(fit_photons[can_move])) - fit_targets[can_move] - SHIFT).median())
                     for name, f in table.items()}
    del fit_photons

    parts = args.out/"parts"
    parts.mkdir(parents=True, exist_ok=True)
    loaded = {}
    for index, (split, (low, high), draw) in enumerate(tasks(args)):
        if index % args.shards != args.shard:
            continue
        path = parts/f"{split}_{low}-{high}_draw{draw}.npz"
        if path.exists():
            continue
        if split not in loaded:
            data = train if split == "train" else prepare(load_split(args.data, split))
            loaded = {split: (data, rays_for(args, split, data[0], torch.Generator().manual_seed(args.seed + 1)))}
        (histograms, targets, capture, names), rays = loaded[split]
        rays = rays[histograms[rays].sum(1) >= high]              # no stream is cut short by a dim ray
        captures = len(names)
        stats = {name: {key: np.zeros(captures) for key in ("abs", "half", "one", "three", "over1m", "avoidable",
                                                            "moved_abs", "moved_n")} for name in table}
        hist = {name: np.zeros(HIST_BINS + 1) for name in table}
        signed = {name: [] for name in table}
        count = np.zeros(captures)
        sampler = torch.Generator(device=device).manual_seed(args.seed * 100003 + index)
        chunk = max(256, min(args.chunk, 2**25 // high))
        for start in range(0, len(rays), chunk):
            ids = rays[start:start + chunk]
            photons = sample_conditions(histograms[ids].to(device), low, high, args.max_background, sampler)[0]
            target, cap = targets[ids].to(device), capture[ids].to(device)
            movable = target + SHIFT + 24 < 672
            shifted = moved(photons[movable])
            count += np.bincount(cap.cpu().numpy(), minlength=captures)
            fit_error = (table["histogram, sub-bin fit"](photons) - offsets["histogram, sub-bin fit"] - target).abs()

            def add(name, key, values, where=cap):
                stats[name][key] += np.bincount(where.cpu().numpy(), weights=values.double().cpu().numpy(),
                                                minlength=captures)

            for name, f in table.items():
                error = f(photons) - offsets[name] - target
                size = error.abs()
                add(name, "abs", size)
                add(name, "half", (size <= .5).float())
                add(name, "one", (size <= 1).float())
                add(name, "three", (size <= 3).float())
                add(name, "over1m", (size * BIN_METERS > 1).float())
                add(name, "avoidable", ((size > MISS_BINS) & (fit_error <= MISS_BINS)).float())
                slot = (size / HIST_STEP).long().clamp(max=HIST_BINS)
                hist[name] += np.bincount(slot.cpu().numpy(), minlength=HIST_BINS + 1)
                signed[name].append(error.cpu())
                if movable.any():
                    moved_size = (f(shifted) - moved_offsets[name] - target[movable] - SHIFT).abs()
                    add(name, "moved_abs", moved_size, cap[movable])
                    add(name, "moved_n", torch.ones_like(moved_size), cap[movable])
        arrays = {"count": count}
        for name in table:
            for key, value in stats[name].items():
                arrays[f"{name}|{key}"] = value
            arrays[f"{name}|hist"] = hist[name]
            arrays[f"{name}|median_signed"] = np.array(float(torch.cat(signed[name]).median()) if signed[name] else np.nan)
        np.savez_compressed(path, names=np.array(names), **arrays)
        print(f"{path.name}: {int(count.sum())} streams", flush=True)
    (args.out/f"offsets_shard{args.shard}.json").write_text(json.dumps(
        {"offset_bins": offsets, "moved_offset_bins": moved_offsets, "device": str(device)}, indent=2) + "\n")


def summarize(args):
    groups = {}
    for path in sorted((args.out/"parts").glob("*.npz")):
        split, band, _ = path.stem.rsplit("_", 2)
        with np.load(path, allow_pickle=False) as part:
            groups.setdefault((split, band), []).append({k: part[k] for k in part.files})

    def pooled(parts, name):
        """Sums over the given parts, and per recording."""
        total = {key: sum(p[f"{name}|{key}"] for p in parts)
                 for key in ("abs", "half", "one", "three", "over1m", "avoidable", "moved_abs", "moved_n", "hist")}
        total["count"] = sum(p["count"] for p in parts)
        return total

    def row(total, parts, name):
        n = total["count"].sum()
        cumulative = np.cumsum(total["hist"])
        median = (np.searchsorted(cumulative, cumulative[-1] / 2) + .5) * HIST_STEP
        moved_n = total["moved_n"].sum()
        return {"streams": int(n), "mae_m": total["abs"].sum() / n * BIN_METERS, "median_m": median * BIN_METERS,
                "recall_half_bin": total["half"].sum() / n, "recall_1_bins": total["one"].sum() / n,
                "recall_3_bins": total["three"].sum() / n, "over_1m": total["over1m"].sum() / n,
                "avoidable_miss_rate": total["avoidable"].sum() / n,
                "moved_target_mae_m": total["moved_abs"].sum() / moved_n * BIN_METERS if moved_n else None,
                "moved_target_streams": int(moved_n),
                "median_signed_bins": float(np.nanmean([p[f"{name}|median_signed"] for p in parts]))}

    names = sorted({k.split("|")[0] for parts in groups.values() for k in parts[0] if "|" in k},
                   key=lambda n: (not n.startswith("histogram"), n))
    order = {name: i for i, name in enumerate(args.order)} if args.order else {}
    names.sort(key=lambda n: (not n.startswith("histogram"), order.get(n, 99)))
    summary = {"bin_m": BIN_METERS, "bands": {}, "splits": {}, "recordings": {}}
    lines = []
    header = (f"{'method':30s} {'streams':>9s} {'mean':>6s} {'median':>6s} {'<=.5bin':>7s} {'<=1bin':>6s} {'<=3bin':>6s} "
              f"{'>1m':>6s} {'avoid':>6s} {'moved':>6s} {'bias':>6s}")

    def show(title, rows):
        lines.extend(["", title, header])
        for name, r in rows.items():
            moved_text = f"{r['moved_target_mae_m']:6.3f}" if r["moved_target_mae_m"] is not None else "     -"
            lines.append(f"{name:30s} {r['streams']:9d} {r['mae_m']:6.3f} {r['median_m']:6.3f} {r['recall_half_bin']:7.1%} "
                         f"{r['recall_1_bins']:6.1%} {r['recall_3_bins']:6.1%} {r['over_1m']:6.2%} "
                         f"{r['avoidable_miss_rate']:6.2%} {moved_text} {r['median_signed_bins']:+6.2f}")

    splits = sorted({split for split, _ in groups}, key=DESIGN_SPLITS.index)
    for split in splits:
        bands = sorted((band for s, band in groups if s == split), key=lambda b: int(b.split("-")[0]))
        every = [p for band in bands for p in groups[(split, band)]]
        summary["splits"][split] = {name: row(pooled(every, name), every, name) for name in names}
        show(f"== {split}: all bands pooled ({', '.join(bands)} photons)", summary["splits"][split])
        for band in bands:
            parts = groups[(split, band)]
            summary["bands"][f"{split} {band}"] = {name: row(pooled(parts, name), parts, name) for name in names}
            show(f"== {split}: {band} photons", summary["bands"][f"{split} {band}"])
        # Per recording: is a result carried by a few scenes, or does it hold across them?
        recordings = [str(n) for n in every[0]["names"]]
        totals = {name: pooled(every, name) for name in names}
        used = totals[names[0]]["count"] > 0
        per = {name: np.where(used, totals[name]["abs"] / np.maximum(totals[name]["count"], 1) * BIN_METERS, np.nan)
               for name in names}
        summary["recordings"][split] = {"names": recordings, "streams": totals[names[0]]["count"].tolist(),
                                        "mae_m": {name: per[name].tolist() for name in names}}
        lines.extend(["", f"== {split}: mean error per recording (m), {int(used.sum())} recordings",
                      f"{'recording':24s} {'streams':>8s} " + " ".join(f"{name[:14]:>14s}" for name in names)])
        for i, recording in enumerate(recordings):
            if used[i]:
                lines.append(f"{recording:24s} {int(totals[names[0]]['count'][i]):8d} "
                             + " ".join(f"{per[name][i]:14.3f}" for name in names))
        if args.compare and int(used.sum()) > 1:
            generator = np.random.default_rng(0)
            lines.extend(["", f"== {split}: paired differences across recordings (mean of per-recording means, m; "
                              "95% interval from resampling recordings)"])
            for pair in args.compare:
                a, b = pair.split(":")
                if a not in per or b not in per:
                    continue
                gap = (per[a] - per[b])[used]
                boot = [generator.choice(gap, len(gap)).mean() for _ in range(4000)]
                wins = int((gap < 0).sum())
                text = (f"{a} minus {b}: {gap.mean():+.4f}  [{np.percentile(boot, 2.5):+.4f}, {np.percentile(boot, 97.5):+.4f}]"
                        f"  better in {wins} of {len(gap)} recordings")
                lines.append(text)
                summary["recordings"][split].setdefault("paired", {})[pair] = {
                    "mean_difference_m": float(gap.mean()), "low_m": float(np.percentile(boot, 2.5)),
                    "high_m": float(np.percentile(boot, 97.5)), "recordings_better": wins, "recordings": int(len(gap))}
    (args.out/"summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    (args.out/"summary_table.txt").write_text("\n".join(lines).lstrip("\n") + "\n")
    print("\n".join(lines))


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("circuits", nargs="*", help="name=path/to/circuit.json")
    parser.add_argument("--data", type=Path, default=ROOT/"data")
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--splits", nargs="+", default=["validation", "architecture"], choices=DESIGN_SPLITS)
    parser.add_argument("--bands", nargs="+", default=["16-32", "32-64", "64-128", "128-256"],
                        help="photon-count bands low-high; counts are log-uniform inside a band")
    parser.add_argument("--draws", type=int, default=5, help="independent photon draws per ray and band")
    parser.add_argument("--max-background", type=float, default=.6)
    parser.add_argument("--min-recorded", type=int, default=0,
                        help="only rays with at least this many recorded photons (the same rays in every band)")
    parser.add_argument("--max-rays", nargs="*", default=[], help="split=N: random subsample of a split")
    parser.add_argument("--chunk", type=int, default=65536, help="streams simulated at once (smaller for long bands)")
    parser.add_argument("--device", default="cuda" if torch.cuda.is_available() else "cpu")
    parser.add_argument("--shard", default="0/1", help="i/n: run every n-th task, starting at i")
    parser.add_argument("--seed", type=int, default=2026)
    parser.add_argument("--threads", type=int, default=2)
    parser.add_argument("--trusted", action="store_true",
                        help="only rays with >= 1024 recorded photons whose full-recording fit is within 3 bins of "
                             "the label, scored against that fit (see validation/README.md)")
    parser.add_argument("--truth", default="full", choices=("full", "label"), help="target for --trusted rays")
    parser.add_argument("--summarize", action="store_true", help="only turn <out>/parts into the summary")
    parser.add_argument("--order", nargs="*", default=[], help="circuit names in table order")
    parser.add_argument("--compare", nargs="*", default=[], help="a:b pairs for per-recording paired differences")
    args = parser.parse_args()
    torch.set_num_threads(args.threads)
    args.bands = [tuple(int(x) for x in band.split("-")) for band in args.bands]
    args.max_rays = {item.split("=")[0]: int(item.split("=")[1]) for item in args.max_rays}
    args.shard, args.shards = (int(x) for x in args.shard.split("/"))
    if args.summarize:
        summarize(args)
    else:
        if not args.circuits:
            parser.error("give at least one name=path circuit")
        run(args)


if __name__ == "__main__":
    main()
