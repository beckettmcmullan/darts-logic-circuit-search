"""Standard numbers plus steadiness for a list of circuits.

Usage: python -m constraints_lab.steadiness.score name=path/circuit.json ... [--verify]
Writes runs/2026-11-11_constraints-lab/steadiness/score.json and prints a table.
"""
import argparse
import json
from pathlib import Path

import torch

from constraints_lab.steadiness.steady import GridSample
from spad import ROOT
from spad.core.stream_model import StreamConfig, pack_circuit, set_search_compile
from spad.dataset.photons import load_rays
from spad.hardware.synth import synthesize, verify
from spad.hardware.verilog import stream_verilog
from spad.training.police import Police, measure_pulse
from spad.training.train_stream import Validator


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("circuits", nargs="+")
    parser.add_argument("--verify", action="store_true")
    parser.add_argument("--out", type=Path, default=ROOT/"runs/2026-11-11_constraints-lab/steadiness/score.json")
    args = parser.parse_args()
    torch.set_num_threads(1)
    set_search_compile(None)
    data = ROOT/"data"
    train = load_rays(data, "train", clean_only=True)[:2]
    validation = load_rays(data, "validation")[:2]
    pulse, zero = measure_pulse(train[0])
    validator = Validator(train, validation, (16, 256, .6), 3, Police(pulse, zero), seed=1234)
    grid = GridSample(validation, len(validation[1]), torch.Generator().manual_seed(1234))
    results = json.loads(args.out.read_text()) if args.out.exists() else {}
    for item in args.circuits:
        name, path = item.split("=", 1)
        circuit = json.loads((ROOT/path).read_text())
        audit = validator.audit(circuit)
        photon = [audit[f"photons_{a}-{b}"]["median_signed_bins"] for a, b in ((16, 32), (32, 64), (64, 128), (128, 256))]
        ambient = [audit[k]["median_signed_bins"] for k in audit if k.startswith("extra_background")]
        inputs, codes = pack_circuit(circuit)
        config = StreamConfig(**circuit["config"])
        ps, bs, gp, gb = grid(config, inputs[None], codes[None])
        synth = synthesize(stream_verilog(circuit), "photon_core", data)
        row = {"path": path, "mae_m": audit["overall"]["mae_m"], "median_m": audit["overall"]["median_m"],
               "within_3_bins": audit["overall"]["recall_3_bins"],
               "photon_offsets": photon, "background_offsets": ambient,
               "audit_photon_spread": max(photon) - min(photon), "audit_background_spread": max(ambient) - min(ambient),
               "grid_photon_spread": float(ps[0]), "grid_background_spread": float(bs[0]),
               "steadiness": max(float(ps[0]), float(bs[0])),
               "grid_photon_offsets": gp[0].tolist(), "grid_background_offsets": gb[0].tolist(),
               "time_shift": audit["time_shift_test"]["moves_with_photons_within_1_bin"],
               "area_um2": synth["area"], "cells": synth["cells"], "flops": synth["flops"]}
        if args.verify:
            row["netlist_mismatches"] = verify(stream_verilog(circuit), "photon_core", circuit)
        results[name] = row
        args.out.write_text(json.dumps(results, indent=1)+"\n")
        print(f"{name:28s} {row['area_um2']:6.2f} µm² {row['cells']:4d} cells {row['flops']:3d} ff | MAE {row['mae_m']:.3f} "
              f"med {row['median_m']:.3f} w3 {row['within_3_bins']:.1%} | offsets {' '.join(f'{x:+.1f}' for x in photon)} "
              f"| bg {' '.join(f'{x:+.1f}' for x in ambient)} | grid P {row['grid_photon_spread']:.2f} B "
              f"{row['grid_background_spread']:.2f} | shift {row['time_shift']:.0%} {row.get('netlist_mismatches', '')}",
              flush=True)


if __name__ == "__main__":
    main()
