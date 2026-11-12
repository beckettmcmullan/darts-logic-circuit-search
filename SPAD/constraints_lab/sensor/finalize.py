"""Standard numbers for circuits: Validator(seed=1234).audit, Yosys + ASAP7 area, netlist parity.

Usage (from SPAD/): ../.venv/bin/python -m constraints_lab.slot -- ../.venv/bin/python -m
constraints_lab.sensor.finalize name=path [name=path ...] --out runs/.../standard.json
"""
import argparse
import json
from pathlib import Path

import torch

from spad import ROOT
from spad.dataset.photons import load_rays
from spad.hardware.synth import synthesize, verify
from spad.hardware.verilog import stream_verilog
from spad.training.police import Police, measure_pulse
from spad.training.train_stream import Validator


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("circuits", nargs="+")
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--data", type=Path, default=ROOT/"data")
    args = parser.parse_args()
    torch.set_num_threads(1)
    train = load_rays(args.data, "train", clean_only=True)[:2]
    validation = load_rays(args.data, "validation")[:2]
    pulse, zero = measure_pulse(train[0])
    validator = Validator(train, validation, (16, 256, .6), 3, Police(pulse, zero), seed=1234)
    results = json.loads(args.out.read_text()) if args.out.exists() else {}
    for item in args.circuits:
        name, path = item.split("=", 1)
        circuit = json.loads(Path(path).read_text())
        audit = validator.audit(circuit)
        synthesized = synthesize(stream_verilog(circuit), "photon_core", args.data)
        mismatches = verify(stream_verilog(circuit), "photon_core", circuit)
        results[name] = {"path": path, "audit": audit, "offset_bins": validator.offset(circuit),
                         "area_um2": synthesized["area"], "cells": synthesized["cells"],
                         "flops": synthesized["flops"], "netlist_mismatches": mismatches}
        o = audit["overall"]
        buckets = " ".join(f"{audit[k]['median_signed_bins']:+.1f}" for k in audit if k.startswith("photons_"))
        print(f"{name:28s} {synthesized['area']:.2f} um2 {synthesized['cells']} cells {synthesized['flops']} ff | "
              f"MAE {o['mae_m']:.3f} med {o['median_m']:.3f} r3 {o['recall_3_bins']:.3f} | offsets {buckets} | "
              f"shift {audit['time_shift_test']['moves_with_photons_within_1_bin']:.3f} | parity {mismatches}", flush=True)
    args.out.write_text(json.dumps(results, indent=2)+"\n")


if __name__ == "__main__":
    main()
