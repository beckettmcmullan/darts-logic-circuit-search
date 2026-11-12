"""Collect the flops track's search runs into one table (no simulation; reads summary.json and history.jsonl).

Run (from SPAD/):  ../.venv/bin/python -m constraints_lab.flops.collect base-s0 cap2-s0 ...
"""
import json
import sys
from pathlib import Path

from spad import ROOT

RUNS = ROOT/"runs/2026-11-11_constraints-lab/flops"


def main():
    for name in sys.argv[1:]:
        folder = RUNS/name
        summary = json.loads((folder/"summary.json").read_text())
        rows = [json.loads(line) for line in (folder/"history.jsonl").read_text().splitlines()]
        rows = [r for r in rows if "validation_mae_m" in r]
        limit = summary["limit_mae_m"]
        print(f"== {name}: forced state bits {summary['forced_state_bits']}, repaired {summary['repaired']}, "
              f"{summary['seconds']:.0f} s, selection limit {limit:.4f} m")
        for label in ("chosen", "best_mae"):
            if label in summary:
                s = summary[label]
                a, y = s["audit"], s["synth"]
                print(f"  {label:8s} area {y['area']:.2f} cells {y['cells']} flops {y['flops']} | MAE {a['mae_m']:.3f} "
                      f"median {a['median_m']:.3f} within3 {a['within3']*100:.1f}% offset {a['offset_steps']} "
                      f"shift {a['time_shift']*100:.0f}% | selection MAE {s['selection_mae_m']:.4f} parity {s['parity_mismatches']}")
        # Pareto front of validated checkpoints: (selection MAE, area)
        front, best = [], float("inf")
        for r in sorted(rows, key=lambda r: (r["area_um2"], r["validation_mae_m"])):
            if r["validation_mae_m"] < best:
                best = r["validation_mae_m"]
                front.append(r)
        print("  front:", ", ".join(f"g{r.get('generation', 0)} {r['area_um2']:.2f}um2/{r['flops']}ff/{r['validation_mae_m']:.4f}m"
                                   for r in front))


if __name__ == "__main__":
    main()
