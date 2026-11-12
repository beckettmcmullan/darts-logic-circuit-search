"""How repeatable is the steadiness measure? Scores the three reference circuits.

Writes runs/2026-11-11_constraints-lab/steadiness/measure/measure.json.
"""
import argparse
import json
from pathlib import Path
import time

import torch

from constraints_lab.steadiness.steady import (GridSample, audit_spread, grid_photons, simulate_checkpoints, COUNTS)
from spad import ROOT
from spad.core.stream_model import StreamConfig, pack_circuit, set_search_compile, simulate_population_packed, simulate_stream
from spad.dataset.photons import load_rays, sample_conditions

REFERENCES = {
    "final_design": "runs/2026-11-10_kaggle-t4_batch3_fused-larger-search/random-s4-seed0/circuit.json",
    "area_tol5": "runs/2026-11-11_local-cpu_area-objective/final-design-tol5/circuit.json",
    "search_end_20um2": "runs/2026-11-11_local-cpu_area-objective/final-design-tol5_no-recheck/search_end_circuit.json",
}


def summarize(values):
    t = torch.tensor(values)
    return {"mean": round(float(t.mean()), 3), "sd": round(float(t.std()), 3),
            "min": round(float(t.min()), 3), "max": round(float(t.max()), 3), "n": len(values)}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", type=Path, default=ROOT/"runs/2026-11-11_constraints-lab/steadiness/measure")
    parser.add_argument("--repeats", type=int, default=12)
    parser.add_argument("--threads", type=int, default=1)
    args = parser.parse_args()
    torch.set_num_threads(args.threads)
    set_search_compile(None)
    args.out.mkdir(parents=True, exist_ok=True)
    data = ROOT/"data"
    train = load_rays(data, "train", clean_only=True)[:2]
    validation = load_rays(data, "validation")[:2]
    circuits = {k: json.loads((ROOT/v).read_text()) for k, v in REFERENCES.items()}
    names = list(circuits)
    config = StreamConfig(**circuits[names[0]]["config"])
    packed = [pack_circuit(c) for c in circuits.values()]
    inputs, codes = torch.stack([p[0] for p in packed]), torch.stack([p[1] for p in packed])
    result = {"circuits": REFERENCES, "counts": COUNTS}
    started = time.time()

    # Sanity: checkpoint simulator equals the reference integer simulator on prefixes.
    g = torch.Generator().manual_seed(0)
    grid = grid_photons(train[0][:200], g)
    check = simulate_checkpoints(config, inputs, codes, grid[1])
    mismatches = sum(int((check[i, m] != simulate_stream(c, grid[1][:, :k])).sum())
                     for m, c in enumerate(circuits.values()) for i, k in enumerate(COUNTS))
    result["checkpoint_simulator_mismatches"] = mismatches
    print("checkpoint mismatches", mismatches, flush=True)

    def audit_style(split, rays, seed, sets=1):
        g = torch.Generator().manual_seed(seed)
        pick = torch.randperm(len(split[1]), generator=g)[:rays] if rays else torch.arange(len(split[1]))
        draws = [sample_conditions(split[0][pick], 16, 256, .6, g) for _ in range(sets)]
        photons, counts, background = (torch.cat(x) for x in zip(*draws))
        error = simulate_population_packed(config, inputs, codes, photons).float() - split[1][pick].repeat(sets).float()
        return audit_spread(error, counts, background)

    def grid_style(split, rays, seed):
        g = torch.Generator().manual_seed(seed)
        rays = rays or len(split[1])
        return GridSample(split, rays, g)(config, inputs, codes)

    rows = {}
    for label, fn in (
            ("audit_validation_3sets", lambda s: audit_style(validation, 0, s, 3)),
            ("audit_train_4096", lambda s: audit_style(train, 4096, s)),
            ("audit_train_16384", lambda s: audit_style(train, 16384, s)),
            ("grid_train_1024", lambda s: grid_style(train, 1024, s)),
            ("grid_train_2048", lambda s: grid_style(train, 2048, s)),
            ("grid_train_4096", lambda s: grid_style(train, 4096, s)),
            ("grid_validation_all", lambda s: grid_style(validation, 0, s))):
        repeats = args.repeats if "validation" not in label else max(4, args.repeats//3)
        samples = []
        for r in range(repeats):
            out = fn(1234 + r) if label.startswith("audit") else fn(1234 + r)
            if label.startswith("audit"):
                photon, ambient, ps, bs = out
            else:
                ps, bs, photon, ambient = out
            samples.append((photon, ambient, ps, bs))
        row = {}
        for m, name in enumerate(names):
            ps = [float(s[2][m]) for s in samples]
            bs = [float(s[3][m]) for s in samples]
            both = [max(a, b) for a, b in zip(ps, bs)]
            row[name] = {"photon_spread": summarize(ps), "background_spread": summarize(bs), "max_spread": summarize(both),
                         "photon_offsets_first": [round(float(x), 2) for x in samples[0][0][m]],
                         "background_offsets_first": [round(float(x), 2) for x in samples[0][1][m]]}
            if m:
                diff = [float(s[2][m] - s[2][0]) for s in samples]
                row[name]["photon_spread_minus_final_design"] = summarize(diff)
        rows[label] = row
        print(label, f"{time.time()-started:.0f}s", json.dumps({n: (row[n]["photon_spread"], row[n]["background_spread"])
                                                                  for n in names}), flush=True)
        result["rows"] = rows
        (args.out/"measure.json").write_text(json.dumps(result, indent=1)+"\n")
    result["seconds"] = time.time() - started
    (args.out/"measure.json").write_text(json.dumps(result, indent=1)+"\n")


if __name__ == "__main__":
    main()
