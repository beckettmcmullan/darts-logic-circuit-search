"""Static timing estimate for a synthesized core, from ASAP7 Liberty tables.

Synthesizes exactly as synth.synthesize does, reads the mapped netlist, and finds the
longest path that a clock period must cover:
  register clock-to-Q (or an input pin) -> combinational cells -> register D + setup.

Each timing arc uses its Liberty table at a nominal point: 20 ps input transition and
the load column nearest 1.44 fF (about a fanout of 2-3), taking the slower of rise and
fall. This is a pre-layout estimate: no wires, no placement, no clock skew. Real
post-route paths are slower; use it to compare designs, not as signoff timing.

Usage (from SPAD/):  ../.venv/bin/python -m spad.hardware.timing runs/<run>/*/circuit.json
"""
import argparse
from functools import lru_cache
import json
from pathlib import Path
import re
import shutil
import tempfile

from spad import ROOT
from spad.hardware.costs import attribute, groups
from spad.hardware.synth import LIBRARIES, yosys
from spad.hardware.verilog import stream_verilog

SLEW_PS, LOAD_FF = 20., 1.44


def _numbers(text):
    return [float(x) for x in re.findall(r"[-+]?\d*\.?\d+(?:[eE][-+]?\d+)?", text)]


def _nominal(table):
    """Table value at the nominal slew row and the load column nearest LOAD_FF."""
    index_1 = re.search(r'index_1\s*\(\s*"([^"]*)"', table)
    index_2 = re.search(r'index_2\s*\(\s*"([^"]*)"', table)
    values = re.search(r"values\s*\((.*?)\)\s*;", table, re.S)
    if not values:
        return None
    rows = [_numbers(row) for row in re.findall(r'"([^"]*)"', values.group(1))]
    if not index_1 or not rows:
        return max(max(r) for r in rows) if rows else None
    slews = _numbers(index_1.group(1))
    i = min(range(len(slews)), key=lambda k: abs(slews[k] - SLEW_PS))
    row = rows[min(i, len(rows) - 1)]
    if index_2 and len(row) > 1:
        loads = _numbers(index_2.group(1))
        j = min(range(len(loads)), key=lambda k: abs(loads[k] - LOAD_FF))
        return row[min(j, len(row) - 1)]
    return row[0]


class Library:
    """Per-cell pin directions, combinational arcs, clock-to-Q and setup, from Liberty text."""

    def __init__(self, paths):
        self.text = "\n".join(Path(p).read_text() for p in paths)
        self.cells = {}

    def cell(self, name):
        if name not in self.cells:
            match = next((body for cell, body in groups(self.text, "cell") if cell == name), None)
            if match is None:
                raise KeyError(f"cell {name} not in the Liberty files")
            self.cells[name] = self._parse(match)
        return self.cells[name]

    @staticmethod
    def _parse(body):
        directions, arcs, clock_to_q, setup = {}, {}, {}, {}
        for pin, pin_body in groups(body, "pin"):
            directions[pin] = attribute(pin_body, "direction")
            for _, timing in groups(pin_body, "timing"):
                related = attribute(timing, "related_pin")
                kind = attribute(timing, "timing_type") or "combinational"
                if kind.startswith("setup"):
                    values = [_nominal(t) for k in ("rise_constraint", "fall_constraint") for _, t in groups(timing, k)]
                    setup[pin] = max([setup.get(pin, 0.)] + [v for v in values if v is not None])
                    continue
                if kind.startswith(("hold", "min_pulse", "recovery", "removal")):
                    continue
                delays = [_nominal(t) for k in ("cell_rise", "cell_fall") for _, t in groups(timing, k)]
                delays = [d for d in delays if d is not None]
                if not delays:
                    continue
                if kind in ("rising_edge", "falling_edge"):
                    clock_to_q[pin] = max(clock_to_q.get(pin, 0.), max(delays))
                else:
                    for source in (related or "").split():
                        arcs[(source, pin)] = max(arcs.get((source, pin), 0.), max(delays))
        return {"directions": directions, "arcs": arcs, "clock_to_q": clock_to_q, "setup": setup}


def mapped_netlist(verilog, module, data, period_ps=1000):
    libraries = {kind: next((data / "asap7").glob(f"*{kind}*.lib")) for kind in LIBRARIES}
    with tempfile.TemporaryDirectory() as name:
        folder = Path(name)
        for kind, path in libraries.items():
            shutil.copy(path, folder / f"{kind}.lib")
        (folder / "core.v").write_text(verilog)
        reads = "\n".join(f"read_liberty -lib {k}.lib" for k in LIBRARIES)
        abc = " ".join(f"-liberty {k}.lib" for k in ("SIMPLE", "INVBUF"))
        yosys(f"{reads}\nread_verilog core.v\nhierarchy -top {module}\nsynth -flatten -top {module}\n"
              f"dfflegalize -cell $_DFF_P_ x\ndfflibmap -liberty SEQ.lib\nabc -D {period_ps} {abc}\n"
              f"opt_clean -purge\nwrite_json mapped.json\n", folder)
        netlist = json.loads((folder / "mapped.json").read_text())["modules"][module]
    return netlist, list(libraries.values())


def critical_path(netlist, library):
    """Longest arrival at any register input (plus setup) or output port, in ps."""
    drivers, sinks = {}, []
    for name, cell in netlist["cells"].items():
        info = library.cell(cell["type"])
        for pin, bits in cell["connections"].items():
            direction = info["directions"].get(pin)
            for bit in bits:
                if isinstance(bit, str):
                    continue                      # constant 0/1
                if direction == "output":
                    drivers[bit] = (name, cell, info, pin)
                elif direction == "input" and pin in info["setup"]:
                    sinks.append((bit, info["setup"][pin], name))
    for port, spec in netlist["ports"].items():
        if spec["direction"] == "output":
            sinks += [(bit, 0., port) for bit in spec["bits"] if not isinstance(bit, str)]

    @lru_cache(maxsize=None)
    def arrival(bit):
        if bit not in drivers:
            return 0.                             # input port: launched at the clock edge
        name, cell, info, out_pin = drivers[bit]
        if out_pin in info["clock_to_q"]:
            return info["clock_to_q"][out_pin]    # register output
        best = 0.
        for pin, bits in cell["connections"].items():
            if info["directions"].get(pin) != "input":
                continue
            delay = info["arcs"].get((pin, out_pin))
            if delay is None:
                continue
            for b in bits:
                if not isinstance(b, str):
                    best = max(best, arrival(b) + delay)
        return best

    import sys
    sys.setrecursionlimit(100000)
    worst = max((arrival(bit) + setup, end) for bit, setup, end in sinks)
    return worst[0], worst[1]


def analyse(circuit, data=ROOT / "data"):
    netlist, paths = mapped_netlist(stream_verilog(circuit), "photon_core", data)
    delay, endpoint = critical_path(netlist, Library(paths))
    return {"critical_path_ps": round(delay, 1), "max_clock_mhz": round(1e6 / delay, 0), "endpoint": endpoint}


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("circuits", type=Path, nargs="+")
    parser.add_argument("--data", type=Path, default=ROOT / "data")
    args = parser.parse_args()
    for path in args.circuits:
        print(path.parent.name, analyse(json.loads(path.read_text()), args.data), flush=True)


if __name__ == "__main__":
    main()
