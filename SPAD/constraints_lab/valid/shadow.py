"""Minimal extra output logic: a wider "shadow" confidence counter used only by the valid output.

The 4-bit confidence counter saturates at 15, so with structured stray light (return-removed
backgrounds) every threshold k <= 15 is crossed as often as by a weak real return once there are
more than ~64 photons. The shadow counter applies the same inc / dec actions as the confidence
counter but saturates at 2**bits - 1; the controller never sees it, so range estimates are
unchanged. valid_out = shadow >= K.

This file evaluates it (ROC on validation backgrounds) and synthesizes it (Verilog copy with the
extra register and output), with a bit-exact netlist check.
"""
import argparse
import json
import tempfile
from pathlib import Path

import numpy as np
import torch

from spad import ROOT
from spad.core.stream_model import ACTIONS, CONF_LEVELS, StreamConfig
from spad.hardware.synth import synthesize, yosys
from spad.hardware.verilog import stream_verilog

from constraints_lab.valid.common import (BUCKETS, REFERENCES, design_data, load_circuit, standard_validator,
                                          validation_backgrounds)
from constraints_lab.valid.verilog_valid import ValidNetlist


@torch.no_grad()
def simulate_shadow(circuit, photons, bits):
    """Returns (candidate, confidence, shadow) with a `bits`-wide shadow counter."""
    c = StreamConfig(**circuit["config"])
    rays = len(photons)
    photons = photons.long()
    candidate = torch.zeros(rays, dtype=torch.long)
    confidence = torch.zeros_like(candidate)
    shadow = torch.zeros_like(candidate)
    state = torch.zeros(rays, c.state_bits, dtype=torch.long)
    top_c, top_q, top_s = 2**c.cand_bits - 1, 2**c.conf_bits - 1, 2**bits - 1
    specs = [(torch.tensor(x["inputs"]), torch.tensor(x["truth_tables"])) for x in circuit["layers"]]
    gates = torch.arange(c.width)[None]
    for step in range(photons.shape[1]):
        arrival, valid = photons[:, step], photons[:, step] >= 0
        distance = arrival - candidate
        flags = [(distance.abs() <= w) for w in c.windows]
        flags += [distance > 0, distance < 0, confidence == 0]
        flags += [confidence >= level for level in CONF_LEVELS]
        flags += [confidence == top_q, torch.zeros_like(valid), torch.ones_like(valid)]
        base = torch.cat((torch.stack(flags, 1).long(), state), 1)
        output = None
        for inputs, tables in specs:
            pool = base if output is None else torch.cat((base, output), 1)
            output = tables[gates, 2*pool[:, inputs[:, 0]] + pool[:, inputs[:, 1]]]
        new_state = output[:, :c.state_bits]
        replace, up, down, inc, dec = output[:, c.state_bits:c.state_bits+len(ACTIONS)].T
        stepped = (candidate + up - down).clamp(0, top_c)
        candidate = torch.where(valid, torch.where(replace == 1, arrival, stepped), candidate)
        confidence = torch.where(valid, (confidence + inc - dec).clamp(0, top_q), confidence)
        shadow = torch.where(valid, (shadow + inc - dec).clamp(0, top_s), shadow)
        state = torch.where(valid[:, None], new_state, state)
    return candidate, confidence, shadow


def run_shadow(circuit, photons, bits, chunk=12000):
    parts = [simulate_shadow(circuit, photons[i:i+chunk], bits) for i in range(0, len(photons), chunk)]
    return tuple(torch.cat(x) for x in zip(*parts))


def shadow_verilog(circuit, bits, threshold, module="photon_core"):
    text = stream_verilog(circuit, module)
    head, rest = text.split(");", 1)
    text = head + ",\n                   output valid_out);" + rest
    top = 2**bits - 1
    text = text.replace("  wire [", f"  reg [{bits-1}:0] shadow;\n  wire [", 1)
    text = text.replace("      confidence <= 0;", "      confidence <= 0;\n      shadow <= 0;", 1)
    text = text.replace("    end\n  end\nendmodule",
                        f"      if (do_inc && !do_dec && shadow != {top}) shadow <= shadow + 1'b1;\n"
                        f"      if (do_dec && !do_inc && shadow != 0) shadow <= shadow - 1'b1;\n"
                        f"    end\n  end\n  assign valid_out = shadow >= {threshold};\nendmodule")
    return text


def verify_shadow(circuit, bits, threshold, rays=3000, seed=3):
    verilog = shadow_verilog(circuit, bits, threshold)
    with tempfile.TemporaryDirectory() as name:
        folder = Path(name)
        (folder/"core.v").write_text(verilog)
        yosys("read_verilog core.v\nhierarchy -top photon_core\nsynth -flatten -top photon_core\n"
              "dfflegalize -cell $_DFF_P_ x\nabc -g AND,OR,XOR,MUX\nopt_clean\nwrite_json core.json\n", folder)
        netlist = ValidNetlist(folder/"core.json", "photon_core")
    torch.manual_seed(seed)
    centre = torch.randint(0, 672, (rays, 1))
    photons = (centre + torch.randint(-6, 7, (rays, 160))).clamp(0, 671)
    photons = torch.where(torch.rand(rays, 160) < .3, torch.randint(0, 672, (rays, 160)), photons)
    photons[: rays//3] = torch.randint(0, 672, (rays//3, 160))
    photons = torch.where(torch.rand(rays, 160) < .05, torch.full_like(photons, -1), photons)
    cand, _, shadow = simulate_shadow(circuit, photons, bits)
    got_cand, got_valid = netlist.run_valid(photons.numpy())
    expected = (shadow >= threshold).numpy()
    return {"candidate_mismatches": int((cand.numpy() != got_cand).sum()),
            "valid_mismatches": int((expected != got_valid).sum()), "valid_ones": int(expected.sum())}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bits", type=int, nargs="+", default=[5, 6, 7])
    parser.add_argument("--circuits", nargs="*", default=None)
    parser.add_argument("--out", type=Path, default=ROOT/"runs/2026-11-11_constraints-lab/valid/shadow/shadow.json")
    args = parser.parse_args()
    torch.set_num_threads(1)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    circuits = REFERENCES if not args.circuits else dict(x.split("=", 1) for x in args.circuits)
    train, _, validation = design_data()
    validator = standard_validator(train, validation)
    backgrounds = validation_backgrounds(validation, seed=4321)
    report = {}
    for cname, path in circuits.items():
        circuit = load_circuit(path)
        report[cname] = {}
        for bits in args.bits:
            _, _, s_real = run_shadow(circuit, validator.photons, bits)
            s_bg = {k: run_shadow(circuit, v[0], bits)[2] for k, v in backgrounds.items() if k != "pixel"}
            rows = {}
            for k in range(1, 2**bits):
                row = {"detect": float((s_real >= k).float().mean()),
                       **{f"fa_{n}": float((s >= k).float().mean()) for n, s in s_bg.items()}}
                row["by_photons"] = {}
                for low, high in BUCKETS:
                    keep = (validator.counts >= low) & (validator.counts < high)
                    b = {"detect": float((s_real[keep] >= k).float().mean())}
                    for n, s in s_bg.items():
                        kb = (backgrounds[n][1] >= low) & (backgrounds[n][1] < high)
                        b[f"fa_{n}"] = float((s[kb] >= k).float().mean())
                    row["by_photons"][f"{low}-{min(high, 256)}"] = b
                rows[k] = row
            best = {}
            for combo in (("uniform",), ("uniform", "residual_far"), ("uniform", "residual")):
                ok = [(r["detect"], k) for k, r in rows.items() if max(r[f"fa_{c}"] for c in combo) <= .01]
                best["+".join(combo)] = max(ok) if ok else (0., None)
            entry = {"best_at_1pct": best, "rows": rows}
            k = best["uniform+residual"][1]
            if k is not None:
                s = synthesize(shadow_verilog(circuit, bits, k), "photon_core", ROOT/"data")
                entry["synthesized"] = {x: v for x, v in s.items() if x != "report"}
                entry["parity"] = verify_shadow(circuit, bits, k)
            report[cname][bits] = entry
            print(cname, bits, best, entry.get("synthesized"), entry.get("parity"), flush=True)
            args.out.write_text(json.dumps(report, indent=1)+"\n")


if __name__ == "__main__":
    main()
