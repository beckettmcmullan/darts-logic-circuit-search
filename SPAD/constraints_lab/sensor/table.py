"""Print markdown tables from evaluate.py results (no simulation)."""
import json
import sys

COLUMNS = ["clean", "jitter:1", "jitter:2", "jitter:4", "pileup:2", "pileup:4", "pileup:8", "mixpileup",
           "pileup:4+jitter:2", "mix", "bits:0.01", "bits:0.01@5"]


def main():
    merged = {}
    for path in sys.argv[1:]:
        for spec, rows in json.load(open(path))["results"].items():
            for name, row in rows.items():
                merged.setdefault(name, {})[spec] = row
    for title, key in (("Offset shift vs clean, bins (factory calibration)", lambda r: f"{r['shift_vs_clean_bins']:+.1f}"),
                       ("Within 3 bins, factory / recalibrated", lambda r: f"{r['factory']['recall_3_bins']*100:.1f} / {r['recalibrated']['recall_3_bins']*100:.1f}"),
                       ("Median error m, factory / recalibrated", lambda r: f"{r['factory']['median_m']:.3f} / {r['recalibrated']['median_m']:.3f}"),
                       ("MAE m, factory / recalibrated", lambda r: f"{r['factory']['mae_m']:.3f} / {r['recalibrated']['mae_m']:.3f}"),
                       ("Spread of offset across photon buckets (max - min), bins",
                        lambda r: f"{max(v for k, v in r.items() if k.startswith('signed_photons')) - min(v for k, v in r.items() if k.startswith('signed_photons')):.1f}")):
        cols = [c for c in COLUMNS if any(c in v for v in merged.values())]
        print(f"\n{title}\n\n| circuit | " + " | ".join(cols) + " |\n" + "|---" * (len(cols) + 1) + "|")
        for name, specs in merged.items():
            print(f"| {name} | " + " | ".join(key(specs[c]) if c in specs and "shift_vs_clean_bins" in specs[c] else "" for c in cols) + " |")


if __name__ == "__main__":
    main()
