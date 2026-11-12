"""Valid-bit ROC of the reference circuits on DESIGN-split backgrounds (train and architecture).

The search scores mutants on these, so this shows what the search can and cannot improve:
uniform, residual (with the crosstalk peak) and residual_far (bins < 48 removed).
"""
import json

import torch
from spad import ROOT
from spad.dataset.photons import sample_conditions

from constraints_lab.valid.background import (capture_groups_clean, residual_profiles, residual_streams,
                                              uniform_streams)
from constraints_lab.valid.common import CONDITIONS, DATA, REFERENCES, design_data, load_circuit, readouts, run_full


def main():
    torch.set_num_threads(1)
    train, routing, _ = design_data()
    g = torch.Generator().manual_seed(77)
    out = {}
    sets = {}
    for name, split in (("train", train), ("architecture", routing)):
        groups = capture_groups_clean(DATA, name)
        pick = torch.randperm(len(split[1]), generator=g)[:8000]
        real = sample_conditions(split[0][pick], *CONDITIONS, g)
        prof = residual_profiles(*split, groups)
        far = residual_profiles(*split, groups, min_bin=48)
        gp = groups[torch.randint(len(groups), (8000,), generator=g)]
        sets[name] = {"real": real, "uniform": uniform_streams(8000, generator=g),
                      "residual": residual_streams(prof, gp, generator=g),
                      "residual_far": residual_streams(far, gp, generator=g)}
    for cname, path in REFERENCES.items():
        circuit = load_circuit(path)
        out[cname] = {}
        for sname, s in sets.items():
            bits = {}
            for kind, data in s.items():
                _, conf, state = run_full(circuit, data[0])
                bits[kind] = readouts(conf, state)
            rows = {}
            for k in bits["real"]:
                rows[k] = {"detect": float(bits["real"][k].float().mean()),
                           **{f"fa_{kind}": float(bits[kind][k].float().mean()) for kind in ("uniform", "residual", "residual_far")}}
            best = {}
            for combo in (("uniform",), ("residual",), ("residual_far",), ("uniform", "residual_far")):
                ok = [(r["detect"], k) for k, r in rows.items() if max(r[f"fa_{c}"] for c in combo) <= .01]
                best["+".join(combo)] = max(ok) if ok else (0., None)
            out[cname][sname] = {"best_at_1pct": best, "readouts": {k: rows[k] for k in ("conf>=6", "conf>=8", "conf>=12", "conf>=15")}}
            print(cname, sname, best, flush=True)
    path = ROOT/"runs/2026-11-11_constraints-lab/valid/design_check.json"
    path.write_text(json.dumps(out, indent=1)+"\n")


if __name__ == "__main__":
    main()
