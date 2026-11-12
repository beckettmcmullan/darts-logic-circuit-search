"""One-time held-out scoring of frozen designs. Run only after design choices stop."""
import argparse
import json
from pathlib import Path
import time

import numpy as np
import torch

from spad.training.baselines import RangeCNN, evaluate_methods, scored
from spad import ROOT
from spad.core.model import Config, RecurrentLogic
from spad.dataset.photons import load_rays, sample_conditions, sample_photons
from spad.core.stream_model import simulate_stream


def average(rows):
    """Mean of nested metric dictionaries across photon-sampling seeds."""
    if isinstance(rows[0], dict):
        return {key: average([row[key] for row in rows]) for key in rows[0]}
    return float(np.mean(rows))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("circuits", type=Path, nargs="+", help="Frozen circuit.json files")
    parser.add_argument("--data", type=Path, default=ROOT/"data")
    parser.add_argument("--baselines", type=Path, default=ROOT/"runs/2026-11-05_reference-baselines")
    parser.add_argument("--pilot", type=Path, default=ROOT/"archive/runs/2026-11-05_histogram-pilot/best.pt")
    parser.add_argument("--out", type=Path, default=ROOT/"runs/final_eval.json")
    parser.add_argument("--seeds", type=int, default=3)
    args = parser.parse_args()
    if args.out.exists():
        raise SystemExit(f"{args.out} exists: held-out scoring is one-time, so keep the first result")
    torch.set_num_threads(4)
    fitted = json.loads((args.baselines/"fitted.json").read_text())
    cnns = {}
    for path in args.baselines.glob("cnn_*.pt"):
        cnns[path.stem] = RangeCNN()
        cnns[path.stem].load_state_dict(torch.load(path))
    checkpoint = torch.load(args.pilot, map_location="cpu", weights_only=False)
    pilot = RecurrentLogic(Config(**checkpoint["config"]))
    pilot.load_state_dict(checkpoint["model"])
    designs = {path.parent.name: json.loads(path.read_text()) for path in args.circuits}
    report = {}
    captures = json.loads((args.data/"processed/metadata.json").read_text())["captures"]
    splits = [s for s in ("test", "fresh_test", "scene_test") if any(v["split"] == s for v in captures.values())]
    for split in splits:
        histograms, targets, clean = load_rays(args.data, split)
        rows = []
        for seed in range(args.seeds):
            row = evaluate_methods(fitted, cnns, histograms, targets, clean, seed=100+seed)
            generator = torch.Generator().manual_seed(200+seed)
            for name, circuit in designs.items():
                # Fixed 64 photons for comparison with earlier designs, and the randomized
                # photon count and ambient light the newer circuits were trained under.
                conditions = circuit.get("conditions", {"min_photons": 16, "max_photons": 256, "max_background": .6})
                draws = {"64": sample_photons(histograms, 64, generator),
                         "randomized": sample_conditions(histograms, conditions["min_photons"], conditions["max_photons"],
                                                         conditions["max_background"], generator)[0]}
                for label, photons in draws.items():
                    prediction = simulate_stream(circuit, photons).float() - circuit["offset_bins"]
                    row[f"{name}_{label}"] = scored(prediction, targets, clean)
            rows.append(row)
        report[split] = average(rows)
        with torch.no_grad():
            scores = torch.cat([pilot(histograms[i:i+500], hard=True) for i in range(0, len(histograms), 500)])
        report[split]["pilot_full"] = scored(scores.argmax(-1).float(), targets, clean)
        report[split]["rays"] = len(targets)
    frame = torch.randint(0, 50, (2000, 672))
    cnn = next(iter(cnns.values()))
    started = time.monotonic()
    cnn.predict(frame)
    report["cnn_cpu_seconds_per_frame_49152_rays"] = (time.monotonic()-started)*49152/2000
    args.out.write_text(json.dumps(report, indent=2)+"\n")
    for split in splits:
        print(split, report[split]["rays"], "rays")
        for name, row in report[split].items():
            if name != "rays":
                a, c = row["all"], row["clean"]
                print(f"  {name:22s} all MAE {a['mae_m']:.3f} med {a['median_m']:.3f} r3 {a['recall_3_bins']:.3f} | clean MAE {c['mae_m']:.3f} med {c['median_m']:.3f} r3 {c['recall_3_bins']:.3f}")


if __name__ == "__main__":
    main()
