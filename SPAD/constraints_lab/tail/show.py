"""Print a run's history and summary briefly: python -m constraints_lab.tail.show RUN_DIR"""
import json
import sys
from pathlib import Path

run = Path(sys.argv[1])
for line in (run/"history.jsonl").read_text().splitlines():
    d = json.loads(line)
    g = lambda k: d.get(f"val_{k}", d.get(k))
    print(d.get("generation", 0), d["area_um2"], d.get("accepted"), *(round(g(k), 4) for k in ("mae_m", "median_m", "over_1m", "p90_m", "p95_m")), d["elapsed_seconds"])
if (run/"summary.json").exists():
    s = json.loads((run/"summary.json").read_text())
    a = s["audit_fresh_photons"]
    print("chosen gen", s["chosen_generation"], "accepted", s["accepted_changes"], "synth", s["synthesized"], "parity", s["netlist_mismatches"])
    print("tail fresh", {k: round(v, 4) for k, v in s["tail_fresh_photons"].items()})
    print("recall3", round(a["overall"]["recall_3_bins"], 3), "offsets", [round(a[k]["median_signed_bins"], 1) for k in a if k.startswith("photons_")],
          "bg offsets", [round(a[k]["median_signed_bins"], 1) for k in a if k.startswith("extra_")], "shift", a["time_shift_test"]["moves_with_photons_within_1_bin"])
    print("search end", s["search_end"]["area_um2"], {k: round(v, 4) for k, v in s["search_end"]["tail_fresh_photons"].items()})
