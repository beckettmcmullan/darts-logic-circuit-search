"""Synthesize cores with Yosys and ASAP7 Liberty, and verify them bit for bit."""
import argparse
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile

import numpy as np
import torch

from spad import ROOT
from spad.core.stream_model import rule_circuit, simulate_stream
from spad.hardware.verilog import Netlist, peak_verilog, stream_verilog

YOSYS = str(Path(sys.executable).parent/"yowasp-yosys")
LIBRARIES = ("SIMPLE", "INVBUF", "SEQ")


def yosys(script, folder):
    (folder/"run.ys").write_text(script)
    done = subprocess.run([YOSYS, "-q", "-l", "yosys.log", "run.ys"], cwd=folder, capture_output=True, text=True)
    if done.returncode:
        raise RuntimeError(done.stdout[-2000:] + done.stderr[-2000:])
    return (folder/"yosys.log").read_text()


def verify(verilog, module, circuit, rays=4000, seed=3):
    """Compare the elaborated gate netlist against the Python integer simulator."""
    with tempfile.TemporaryDirectory() as name:
        folder = Path(name)
        (folder/"core.v").write_text(verilog)
        yosys(f"read_verilog core.v\nhierarchy -top {module}\nsynth -flatten -top {module}\n"
              "dfflegalize -cell $_DFF_P_ x\nabc -g AND,OR,XOR,MUX\nopt_clean\nwrite_json core.json\n", folder)
        netlist = Netlist(folder/"core.json", module)
    torch.manual_seed(seed)
    centre = torch.randint(0, 672, (rays, 1))
    photons = (centre + torch.randint(-12, 13, (rays, 96))).clamp(0, 671)
    noise = torch.rand(rays, 96) < .3
    photons = torch.where(noise, torch.randint(0, 672, (rays, 96)), photons)
    photons = torch.where(torch.rand(rays, 96) < .05, torch.full_like(photons, -1), photons)
    expected = simulate_stream(circuit, photons).numpy()
    actual = netlist.run(photons.numpy())
    return int((expected != actual).sum())


def synthesize(verilog, module, data, period_ps=1000):
    libraries = {kind: next((data/"asap7").glob(f"*{kind}*.lib")) for kind in LIBRARIES}
    with tempfile.TemporaryDirectory() as name:
        folder = Path(name)
        for kind, path in libraries.items():
            shutil.copy(path, folder/f"{kind}.lib")
        (folder/"core.v").write_text(verilog)
        reads = "\n".join(f"read_liberty -lib {k}.lib" for k in LIBRARIES)
        stat = " ".join(f"-liberty {k}.lib" for k in LIBRARIES)
        abc = " ".join(f"-liberty {k}.lib" for k in ("SIMPLE", "INVBUF"))
        log = yosys(f"{reads}\nread_verilog core.v\nhierarchy -top {module}\nsynth -flatten -top {module}\n"
                    f"dfflegalize -cell $_DFF_P_ x\ndfflibmap -liberty SEQ.lib\nabc -D {period_ps} {abc}\n"
                    f"opt_clean -purge\ntee -o stat.txt stat {stat}\n", folder)
        text = (folder/"stat.txt").read_text()
    area = re.findall(r"Chip area for module.*?:\s*([\d.eE+-]+)", text)
    cells = re.findall(r"^\s+(\d+)\s+(?:[\d.eE+-]+\s+)?([A-Za-z0-9_]+_ASAP7_75t_R)", text, re.M)
    flops = sum(int(n) for n, cell in cells if cell.startswith(("DFF", "DLL", "DHL")))
    return {"area": float(area[-1]) if area else None, "cells": sum(int(n) for n, _ in cells),
            "flops": flops, "report": text}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("circuits", type=Path, nargs="*", help="circuit.json files")
    parser.add_argument("--data", type=Path, default=ROOT/"data")
    parser.add_argument("--out", type=Path, default=ROOT/"runs/synthesis.json")
    args = parser.parse_args()
    results = {}
    designs = {"rule8": rule_circuit(window=8)}
    for path in args.circuits:
        designs[path.parent.name] = json.loads(path.read_text())
    for name, circuit in designs.items():
        verilog = stream_verilog(circuit)
        mismatches = verify(verilog, "photon_core", circuit)
        results[name] = {k: v for k, v in synthesize(verilog, "photon_core", args.data).items() if k != "report"}
        results[name]["netlist_mismatches"] = mismatches
        print(name, results[name], flush=True)
    results["peak_reader_no_memory"] = {k: v for k, v in synthesize(peak_verilog(), "peak_reader", args.data).items() if k != "report"}
    print(results["peak_reader_no_memory"])
    args.out.write_text(json.dumps(results, indent=2)+"\n")


if __name__ == "__main__":
    main()
