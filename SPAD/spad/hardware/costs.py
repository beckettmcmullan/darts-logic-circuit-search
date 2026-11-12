"""ASAP7 Liberty-derived search proxies, not synthesis or signoff timing."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess

import torch

from spad import ROOT
from spad.dataset.download import usage


def groups(text, kind):
    """Balanced Liberty group scanner (handles nested tables and quoted braces)."""
    pattern = re.compile(r"\b" + re.escape(kind) + r"\s*\(\s*([^)]*)\)\s*\{")
    for match in pattern.finditer(text):
        level, quote, escaped = 1, False, False
        i = match.end()
        while level and i < len(text):
            ch = text[i]
            if ch == '"' and not escaped:
                quote = not quote
            if not quote:
                level += (ch == "{") - (ch == "}")
            escaped = ch == "\\" and not escaped
            i += 1
        if level:
            raise ValueError(f"Unbalanced Liberty group: {kind}")
        yield match.group(1).strip().strip('"'), text[match.end():i-1]


def attribute(text, name):
    # Some released ASAP7 attributes omit a semicolon before the newline.
    match = re.search(r"\b" + name + r"\s*:\s*([^;\n\r]+)", text)
    return match.group(1).strip().strip('"') if match else None


def table_max(text, kinds):
    values = []
    for kind in kinds:
        for _, body in groups(text, kind):
            for _, data in re.findall(r'(values)\s*\((.*?)\)\s*;', body, re.S):
                values.extend(float(x) for x in re.findall(r"[-+]?\d*\.?\d+(?:[eE][-+]?\d+)?", data))
    return max(values) if values else None


def extract_cells(text, source):
    time = attribute(text, "time_unit")
    units = re.fullmatch(r"([\d.]+)\s*(ps|ns|us|s)", time or "")
    if not units:
        raise ValueError(f"Unsupported Liberty time unit {time}")
    to_ps = float(units[1]) * {"ps": 1, "ns": 1000, "us": 1e6, "s": 1e12}[units[2]]
    cells = []
    for name, body in groups(text, "cell"):
        area = attribute(body, "area")
        if area is None:
            continue
        delay = table_max(body, ("cell_rise", "cell_fall"))
        if delay is None:
            continue
        setup = []
        for _, timing in groups(body, "timing"):
            if (attribute(timing, "timing_type") or "").startswith("setup_"):
                value = table_max(timing, ("rise_constraint", "fall_constraint"))
                if value is not None:
                    setup.append(value)
        cells.append({"name": name, "area": float(area), "delay_ps": delay * to_ps,
                      "source": source, "time_unit": time,
                      "setup_ps": max([0.] + setup) * to_ps})
    return cells


def build_costs(root):
    folder = root / "asap7"
    for archive in folder.glob("*.lib.7z"):
        # macOS bsdtar supports 7z. Read only the named library from each archive.
        target = archive.with_suffix("")
        if not target.exists():
            members = subprocess.check_output(["tar", "-tf", str(archive)], text=True).splitlines()
            members = [name for name in members if name.endswith(".lib")]
            if len(members) != 1:
                raise ValueError(f"Expected one .lib in {archive}")
            data = subprocess.check_output(["tar", "-xOf", str(archive), members[0]])
            manifest = json.loads((root / "manifest.json").read_text())
            if usage(root) + len(data) > manifest["budget_bytes"]:
                raise RuntimeError("Liberty decompression would exceed data budget")
            target.write_bytes(data)
    cells = []
    for path in folder.glob("*.lib"):
        cells.extend(extract_cells(path.read_text(), path.name))
    if not cells:
        raise RuntimeError("No ASAP7 cells found; run download.py first")
    # The ASAP7 names identify primitive type; choose smallest area then delay.
    # No invented gate constants: fail if a primitive is absent.
    selected = {}
    for kind, pattern in {
            "INV": r"INVx", "BUF": r"BUFx", "AND": r"AND2x", "OR": r"OR2x",
            "NAND": r"NAND2x", "NOR": r"NOR2x", "XOR": r"XOR2x",
            "XNOR": r"XNOR2x", "DFF": r"DFFHQN?x"}.items():
        candidates = [cell for cell in cells if re.match(pattern, cell["name"])]
        if not candidates:
            raise RuntimeError(f"Missing primitive {kind}; cells: {[c['name'] for c in cells]}")
        selected[kind] = min(candidates, key=lambda cell: (cell["area"], cell["delay_ps"]))
    zero = {"area": 0., "delay_ps": 0., "cells": []}
    def compose(*kinds):
        return {"area": sum(selected[k]["area"] for k in kinds),
                "delay_ps": sum(selected[k]["delay_ps"] for k in kinds),
                "cells": [selected[k]["name"] for k in kinds]}
    # Codes are sum(table[i] << i), table ordered 00,01,10,11.
    table = [zero.copy() for _ in range(16)]
    for code, kinds in {1:("NOR",), 2:("INV","AND"), 3:("INV",),
                        4:("INV","AND"), 5:("INV",), 6:("XOR",), 7:("NAND",),
                        8:("AND",), 9:("XNOR",), 11:("INV","OR"),
                        13:("INV","OR"), 14:("OR",)}.items():
        table[code] = compose(*kinds)
    result = {
        "library": "ASAP7 7.5-track RVT TT NLDM", "selected_cells": selected,
        "truth_table_costs": table, "area_unit": "native Liberty area units",
        "delay_definition": "maximum cell_rise/cell_fall entry over all characterized loads, slews and arcs",
        "limitations": ["Not static timing analysis; no fanout, placement, wires, clock tree or power",
                        "Native Liberty area units are retained; no physical-area scaling inferred",
                        "Search counts every candidate gate and every recurrent register; no dead-cone pruning",
                        "Fixed count encoder, bin counter and argmax reducer are outside the learned-core cost"],
        "sources": {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in folder.glob("*.lib")}}
    (folder / "costs.json").write_text(json.dumps(result, indent=2) + "\n")
    return result


def core_cost(model, costs, temperature=1., hard=False):
    """Expected table cost plus routing-dependent combinational path proxy.

    Truth-table probabilities derive from four independent Bernoulli outputs;
    they are only used to compute cost, not a 16-way gate parametrization.
    """
    device = next(model.parameters()).device
    tables = torch.tensor([[float((code >> i) & 1) for i in range(4)] for code in range(16)], device=device)
    areas = torch.tensor([x["area"] for x in costs["truth_table_costs"]], device=device)
    delays = torch.tensor([x["delay_ps"] for x in costs["truth_table_costs"]], device=device)
    dff = costs["selected_cells"]["DFF"]
    base = torch.zeros(model.base_bits, device=device)
    base[model.external_bits:] = dff["delay_ps"]
    area = torch.tensor(model.config.state_bits * dff["area"], device=device)
    previous = None
    for layer in model.layers:
        routes, truth = layer.prepared(temperature, hard=hard)
        likelihood = torch.where(tables[None] > 0, truth[:, None], 1-truth[:, None]).prod(-1)
        area = area + (likelihood @ areas).sum()
        gate_delay = likelihood @ delays
        pool = base if previous is None else torch.cat((base, previous))
        # Constants have no input path; unary/pass-through gates use only their
        # functional input. Expected dependencies relax this for soft tables.
        uses_a = ((tables[:, 0] != tables[:, 2]) | (tables[:, 1] != tables[:, 3])).float()
        uses_b = ((tables[:, 0] != tables[:, 1]) | (tables[:, 2] != tables[:, 3])).float()
        a = (routes[:, 0] @ pool) * (likelihood @ uses_a)
        b = (routes[:, 1] @ pool) * (likelihood @ uses_b)
        previous = torch.maximum(a, b) + gate_delay
    # All last-layer outputs are conservatively included.
    delay = previous.max() + dff["setup_ps"]
    return area, delay


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT / "data")
    args = parser.parse_args()
    result = build_costs(args.root)
    print(json.dumps(result["selected_cells"], indent=2))
