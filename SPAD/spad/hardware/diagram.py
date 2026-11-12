"""Draw a learned photon-stream core: controller logic, Boolean equations and gate netlists.

Writes into <out>/ (default: diagrams/ next to circuit.json):
  controller.svg   learned gates only, after removing constants, pass-throughs and dead gates
  equations.txt    minimized Boolean equation for every controller output
  core.v           the full core in Verilog
  logic.json/svg   whole core in generic AND/OR/XOR/MUX gates (netlistsvg)
  asap7.json/svg   whole core mapped to ASAP7 cells (netlistsvg)
The SVG schematics need Node.js; netlistsvg is fetched with npx on first use.
"""
import argparse
from html import escape
import itertools
import json
from pathlib import Path
import shutil
import subprocess
import tempfile

import numpy as np

from spad import ROOT
from spad.core.stream_model import ACTIONS, CONF_LEVELS, StreamConfig
from spad.hardware.synth import LIBRARIES, yosys
from spad.hardware.verilog import stream_verilog

# Truth table order is f(0,0), f(0,1), f(1,0), f(1,1) for inputs (a, b).
GATE_NAMES = {(0, 0, 0, 1): "AND", (0, 1, 1, 1): "OR", (0, 1, 1, 0): "XOR", (1, 0, 0, 1): "XNOR",
              (1, 1, 1, 0): "NAND", (1, 0, 0, 0): "NOR", (0, 0, 1, 0): "a AND NOT b",
              (0, 1, 0, 0): "NOT a AND b", (1, 0, 1, 1): "a OR NOT b", (1, 1, 0, 1): "NOT a OR b"}


def reachable_flags(config):
    """Every datapath flag combination the hardware can actually produce."""
    combos = set()
    for diff in range(-40, 41):
        size = abs(diff)
        near = tuple(int(size <= w) for w in config.windows)
        for conf in range(2**config.conf_bits):
            levels = tuple(int(conf >= level) for level in CONF_LEVELS)
            combos.add(near + (int(diff > 0), int(diff < 0), int(conf == 0)) + levels
                       + (int(conf == 2**config.conf_bits - 1),))
    return sorted(combos)


def analyse(circuit):
    """Truth tables of every wire over all reachable inputs, and a simplified gate graph."""
    config = StreamConfig(**circuit["config"])
    names = circuit["inputs"]
    flags = np.array(reachable_flags(config), dtype=bool)
    states = np.array(list(itertools.product((0, 1), repeat=config.state_bits)), dtype=bool).reshape(2**config.state_bits, config.state_bits)
    rows = len(flags) * len(states)
    columns = {}
    flag_names = [n for n in names if not n.startswith(("const", "state"))]
    for i, name in enumerate(flag_names):
        columns[name] = np.repeat(flags[:, i], len(states))
    for i in range(config.state_bits):
        columns[f"state{i}"] = np.tile(states[:, i], len(flags))
    columns["const0"], columns["const1"] = np.zeros(rows, bool), np.ones(rows, bool)

    # Each wire becomes ("const", v), ("wire", source), ("not", source) or ("gate", label, a, b).
    known = {}  # truth-table bytes -> (wire, negated) of the first wire computing it
    nodes, values = {}, {}

    def register(wire, value):
        values[wire] = value
        for v, neg in ((value, False), (~value, True)):
            known.setdefault(v.tobytes(), (wire, neg))

    for name in names:
        register(name, columns[name])
        nodes[name] = ("const", int(name[-1])) if name.startswith("const") else ("input",)

    def resolve(wire):
        node = nodes[wire]
        return node[1] if node[0] == "wire" else wire

    pool = list(names)
    for depth, layer in enumerate(circuit["layers"]):
        outputs = []
        for gate, (inputs, table) in enumerate(zip(layer["inputs"], layer["truth_tables"])):
            wire = f"g{depth}_{gate}"
            a, b = (values[pool[i]] for i in inputs)
            t = tuple(table)
            value = ((bool(t[0]) & ~a & ~b) | (bool(t[1]) & ~a & b) | (bool(t[2]) & a & ~b)
                     | (bool(t[3]) & a & b)).astype(bool)
            if value.all() or not value.any():
                nodes[wire] = ("const", int(value.all()))
            elif value.tobytes() in known and not known[value.tobytes()][1]:
                nodes[wire] = ("wire", resolve(known[value.tobytes()][0]))
            elif value.tobytes() in known:
                nodes[wire] = ("not", resolve(known[value.tobytes()][0]))
            else:
                source_a, source_b = resolve(pool[inputs[0]]), resolve(pool[inputs[1]])
                nodes[wire] = ("gate", GATE_NAMES.get(t, str(t)), source_a, source_b)
            register(wire, value)
            outputs.append(wire)
        pool = list(names) + outputs
    final = pool[len(names):]
    labels = [f"next_state{i}" for i in range(config.state_bits)] + [f"do_{a}" for a in ACTIONS]
    return config, names, columns, values, nodes, dict(zip(labels, final))


def equations(names, columns, values, outputs):
    """Minimized sum-of-products per output, treating impossible flag combinations as don't-cares."""
    from sympy import symbols
    from sympy.logic import SOPform
    variables = [n for n in names if not n.startswith("const")]
    lines = []
    for label, wire in outputs.items():
        value = values[wire]
        support = [v for v in variables if _depends(columns, value, v, variables)]
        if not support:
            lines.append(f"{label} = {int(value[0])}")
            continue
        table = np.stack([columns[v] for v in support], 1).astype(int)
        seen = {tuple(r): int(f) for r, f in zip(table, value)}
        ones = [list(r) for r, f in seen.items() if f]
        cares = set(seen)
        dont = [list(r) for r in itertools.product((0, 1), repeat=len(support)) if r not in cares]
        expression = SOPform(symbols(support), ones, dont)
        lines.append(f"{label} = {expression}")
    return lines


def _depends(columns, value, var, variables):
    """True if flipping var between two reachable rows (all else equal) changes the output."""
    others = [v for v in variables if v != var]
    key = np.stack([columns[v] for v in others], 1)
    groups = {}
    for k, x, f in zip(map(bytes, np.packbits(key, 1)), columns[var], value):
        groups.setdefault(k, {})[bool(x)] = bool(f)
    return any(len(g) == 2 and g[True] != g[False] for g in groups.values())


def controller_svg(names, nodes, outputs, title):
    """Layered drawing of only the logic that reaches an output."""
    needed, stack = set(), []
    out_sources = {}
    constants = {}
    for label, wire in outputs.items():
        node = nodes[wire]
        source = node[1] if node[0] == "wire" else wire
        if nodes[source][0] == "const":
            constants[label] = nodes[source][1]  # drawn as "label = v", no wire
            continue
        out_sources[label] = source
        stack.append(source)
    while stack:
        wire = stack.pop()
        if wire in needed:
            continue
        needed.add(wire)
        node = nodes[wire]
        stack += [s for s in node[2:]] if node[0] == "gate" else [node[1]] if node[0] == "not" else []
    depth = {}

    def level(wire):
        if wire not in depth:
            node = nodes[wire]
            parents = node[2:] if node[0] == "gate" else [node[1]] if node[0] == "not" else []
            depth[wire] = 1 + max((level(p) for p in parents), default=-1)
        return depth[wire]

    for wire in needed:
        level(wire)
    columns = max(depth.values(), default=0) + 2
    by_column = [[] for _ in range(columns)]
    for wire in sorted(needed, key=lambda w: (names.index(w) if w in names else 999, w)):
        if nodes[wire][0] != "const" or wire in out_sources.values():
            by_column[depth[wire]].append(wire)
    by_column[-1] = list(outputs)
    box_w, box_h, gap_x, gap_y = 150, 34, 90, 16
    height = max(len(c) for c in by_column) * (box_h + gap_y) + 90
    width = columns * (box_w + gap_x) + 40
    pos = {}
    for c, wires in enumerate(by_column):
        offset = (height - 60 - len(wires) * (box_h + gap_y)) / 2 + 50
        for r, wire in enumerate(wires):
            pos[("out", wire) if c == columns - 1 else wire] = (20 + c * (box_w + gap_x), offset + r * (box_h + gap_y))
    svg = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" font-family="Helvetica,Arial" font-size="12">',
           '<rect width="100%" height="100%" fill="white"/>',
           f'<text x="20" y="28" font-size="16" font-weight="bold">{escape(title)}</text>']

    def edge(src, dst, port, ports):
        x0, y0 = pos[src]
        x1, y1 = pos[dst]
        x0 += box_w
        y0 += box_h / 2
        y1 += box_h * (port + 1) / (ports + 1)
        mid = (x0 + x1) / 2
        svg.append(f'<path d="M{x0},{y0} C{mid},{y0} {mid},{y1} {x1},{y1}" fill="none" stroke="#555" stroke-width="1.3"/>')
        if ports == 2:
            svg.append(f'<text x="{x1 + 4}" y="{y1 + 4}" font-size="10" fill="#888">{"ab"[port]}</text>')

    for wire in needed:
        node = nodes[wire]
        if node[0] == "gate":
            edge(node[2], wire, 0, 2)
            edge(node[3], wire, 1, 2)
        elif node[0] == "not":
            edge(node[1], wire, 0, 1)
    for label, source in out_sources.items():
        edge(source, ("out", label), 0, 1)
    colours = {"input": "#dbeafe", "gate": "#fef3c7", "not": "#fde68a", "const": "#e5e7eb"}
    for key, (x, y) in pos.items():
        if isinstance(key, tuple):
            constant = constants.get(key[1])
            text = key[1] if constant is None else f"{key[1]} = {constant}"
            fill = "#dcfce7" if constant is None else "#f3f4f6"
        else:
            node = nodes[key]
            text = (key if node[0] == "input" else node[1] if node[0] == "gate"
                    else "NOT" if node[0] == "not" else f"constant {node[1]}")
            fill = colours[node[0]]
        svg.append(f'<rect x="{x}" y="{y}" width="{box_w}" height="{box_h}" rx="6" fill="{fill}" stroke="#333"/>')
        svg.append(f'<text x="{x + box_w / 2}" y="{y + box_h / 2 + 4}" text-anchor="middle">{escape(text)}</text>')
    svg.append("</svg>")
    return "\n".join(svg)


def netlists(verilog, out, data, render=True):
    """Yosys netlists in generic gates and in ASAP7 cells, rendered with netlistsvg if Node is present."""
    libraries = {kind: next((data/"asap7").glob(f"*{kind}*.lib")) for kind in LIBRARIES}
    with tempfile.TemporaryDirectory() as name:
        folder = Path(name)
        for kind, path in libraries.items():
            shutil.copy(path, folder/f"{kind}.lib")
        (folder/"core.v").write_text(verilog)
        top = "read_verilog core.v\nhierarchy -top photon_core\nsynth -flatten -top photon_core\ndfflegalize -cell $_DFF_P_ x\n"
        yosys(top + "abc -g AND,OR,XOR,MUX\nopt_clean -purge\nwrite_json logic.json\n", folder)
        reads = "\n".join(f"read_liberty -lib {k}.lib" for k in LIBRARIES)
        abc = " ".join(f"-liberty {k}.lib" for k in ("SIMPLE", "INVBUF"))
        yosys(f"{reads}\n{top}dfflibmap -liberty SEQ.lib\nabc -D 1000 {abc}\nopt_clean -purge\nwrite_json asap7.json\n", folder)
        for name in ("logic.json", "asap7.json"):
            shutil.copy(folder/name, out/name)
    if not render:
        return f"skipped rendering; to draw them run: cd {out} && npx netlistsvg logic.json -o logic.svg"
    if not shutil.which("npx"):
        return "Node.js not found; install it to render logic.svg and asap7.svg"
    for name in ("logic", "asap7"):
        done = subprocess.run(["npx", "--yes", "netlistsvg", f"{name}.json", "-o", f"{name}.svg"],
                              cwd=out, capture_output=True, text=True)
        if done.returncode:
            return f"netlistsvg failed on {name}.json: {done.stderr[-500:]}"
    return None


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("circuit", type=Path, help="circuit.json from a training run")
    parser.add_argument("--out", type=Path, help="defaults to diagrams/ beside circuit.json")
    parser.add_argument("--data", type=Path, default=ROOT/"data")
    parser.add_argument("--no-netlist", action="store_true", help="skip Yosys and netlistsvg")
    parser.add_argument("--no-render", action="store_true", help="write netlist JSON but do not run netlistsvg")
    args = parser.parse_args()
    circuit = json.loads(args.circuit.read_text())
    out = args.out or args.circuit.parent/"diagrams"
    out.mkdir(parents=True, exist_ok=True)
    run = args.circuit.parent.name
    config, names, columns, values, nodes, outputs = analyse(circuit)
    lines = equations(names, columns, values, outputs)
    live = sum(1 for n in nodes.values() if n[0] in ("gate", "not"))
    header = [f"# {run}: learned controller", f"# {live} gates do real work out of {config.width * config.layers}",
              "# impossible flag combinations are treated as don't-cares", ""]
    (out/"equations.txt").write_text("\n".join(header + lines) + "\n")
    (out/"controller.svg").write_text(controller_svg(names, nodes, outputs, f"{run}: learned controller"))
    verilog = stream_verilog(circuit)
    (out/"core.v").write_text(verilog)
    print("\n".join(lines))
    if not args.no_netlist:
        problem = netlists(verilog, out, args.data, render=not args.no_render)
        if problem:
            print(problem)
    print(f"wrote {out}")


if __name__ == "__main__":
    main()
