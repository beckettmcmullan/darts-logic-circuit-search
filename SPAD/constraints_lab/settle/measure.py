"""Score circuits on settling, plus the standard numbers (audit, synthesis, netlist parity).

../.venv/bin/python -m constraints_lab.slot -- ../.venv/bin/python -m constraints_lab.settle.measure \
    --out runs/2026-11-11_constraints-lab/settle/reference name=path.json ...   (name=rule for rule_circuit)
"""
import argparse
import json
from pathlib import Path
import statistics
import time

import torch

from spad import ROOT
from spad.dataset.photons import load_rays
from spad.training.police import Police, measure_pulse
from spad.training.train_stream import Validator
from spad.core.stream_model import StreamConfig, rule_circuit
from constraints_lab.settle.settle import (FINE, READOUTS, curve_metrics, full_streams, per_count_offsets,
                                           settle_curve, settle_points, trace_stream)

CONDITIONS = (16, 256, .6)


def load(spec):
    name, path = spec.split("=", 1)
    if path == "rule":
        return name, rule_circuit(StreamConfig())
    return name, json.loads(Path(path).read_text())


def standard(circuit, validator, data, parity=True):
    from spad.hardware.synth import synthesize, verify
    from spad.hardware.verilog import stream_verilog
    audit = validator.audit(circuit)
    verilog = stream_verilog(circuit)
    synth = synthesize(verilog, "photon_core", data)
    row = {"audit": audit, "area_um2": synth["area"], "cells": synth["cells"], "flops": synth["flops"]}
    if parity:
        row["netlist_mismatches"] = verify(verilog, "photon_core", circuit)
    return row


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("circuits", nargs="+", help="name=path/to/circuit.json or name=rule")
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--data", type=Path, default=ROOT/"data")
    parser.add_argument("--sets", type=int, default=3)
    parser.add_argument("--repeats", type=int, default=5, help="single-set photon draws for repeatability")
    parser.add_argument("--no-standard", action="store_true")
    args = parser.parse_args()
    torch.set_num_threads(1)
    args.out.mkdir(parents=True, exist_ok=True)
    train = load_rays(args.data, "train", clean_only=True)[:2]
    validation = load_rays(args.data, "validation")[:2]
    pulse, zero = measure_pulse(train[0])
    validator = Validator(train, validation, CONDITIONS, 3, Police(pulse, zero), seed=1234)
    # Settling pixels: the validation pixels, full 256-photon streams, `sets` draws (seed 1234).
    g = torch.Generator().manual_seed(1234)
    photons = torch.cat([full_streams(validation[0], generator=g)[0] for _ in range(args.sets)])
    targets = validation[1].repeat(args.sets)
    # Per-count offsets are fitted like the standard one: on 8,000 train pixels.
    pick = torch.randperm(len(train[1]), generator=torch.Generator().manual_seed(7))[:8000]
    fit_photons = full_streams(train[0][pick], generator=torch.Generator().manual_seed(8))[0]
    fit_targets = train[1][pick]
    results = {}
    for spec in args.circuits:
        started = time.time()
        name, circuit = load(spec)
        offset = validator.offset(circuit)
        own = per_count_offsets(circuit, fit_photons, fit_targets)
        row = {"settle": settle_curve(circuit, photons, targets, offset, FINE, own)}
        # Repeatability: the same pixels, independent photon draws, one set each.
        repeats = {"single_offset": {n: [] for n in READOUTS}, "points": []}
        for r in range(args.repeats):
            gr = torch.Generator().manual_seed(5000 + r)
            p = full_streams(validation[0], generator=gr)[0]
            raw = trace_stream(circuit, p, FINE)
            rows = {n: curve_metrics(raw[n].float() - offset, validation[1]) for n in FINE}
            for n in READOUTS:
                repeats["single_offset"][n].append(rows[n])
            repeats["points"].append(settle_points(rows, rows[256]["mae_m"]))
        spread = {}
        for n in READOUTS:
            for key in ("mae_m", "median_m", "within_3_bins"):
                values = [x[key] for x in repeats["single_offset"][n]]
                spread[f"{key}@{n}"] = {"mean": statistics.mean(values), "sd": statistics.stdev(values),
                                       "min": min(values), "max": max(values), "draws": values}
        for key in repeats["points"][0]:
            spread[key] = [x[key] for x in repeats["points"]]
        row["repeatability_single_set"] = spread
        if not args.no_standard:
            row.update(standard(circuit, validator, args.data))
        row["seconds"] = time.time() - started
        results[name] = row
        s = row["settle"]["single_offset"]
        print(name, {n: round(s[n]["mae_m"], 3) for n in READOUTS}, row["settle"]["settle_single_offset"],
              {k: row.get(k) for k in ("area_um2", "cells", "flops", "netlist_mismatches")}, flush=True)
        (args.out/"settle_scores.json").write_text(json.dumps(results, indent=1) + "\n")


if __name__ == "__main__":
    main()
