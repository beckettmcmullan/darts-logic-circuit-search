"""Draw every cell of a routed ASAP7 netlist as a schematic with real logic-gate symbols.

Usage (from SPAD/):  python asic/draw_gates.py asic/results/<run>   [-o gates.svg]

Reads <run>/6_final.v, converts it to JSON with Yosys and lays it out with netlistsvg
(fetched with npx), using a skin generated here. Simple cells (INV, BUF, NAND2, OR3, XNOR2, ...)
get the standard symbol. Compound cells (AO/OA/AOI/OAI, half and full adders) are drawn as their
internal gates inside a dashed outline that marks the boundary of the one standard cell.
Tap, filler and decap cells are not in 6_final.v and are not drawn.
"""
import argparse
import json
from pathlib import Path
import re
import subprocess
import tempfile

PITCH = 10          # vertical distance between neighbouring gate inputs
GATE_W = 30         # body width of AND/OR/XOR symbols
OUTPUT_PINS = {"Y", "Q", "QN", "CON", "SN", "H", "L"}

STYLE = """
svg { background-color: #fff; }
.cellbox { stroke: #9aa0a6; stroke-dasharray: 3,2; }
.dot { fill: #000; }
.celltype { font-size: 8px; font-weight: normal; fill: #555; }
.pinlabel { font-size: 6px; font-weight: normal; fill: #333; }
"""


class Drawing:
    """A cell template under construction: SVG elements plus pin positions."""

    def __init__(self):
        self.parts, self.pins = [], []

    def path(self, d, cls=""):
        cls = f' class="{cls}"' if cls else ""
        self.parts.append(f'<path d="{d}"{cls}/>')

    def line(self, *points):
        self.path("M" + " L".join(f"{x:g},{y:g}" for x, y in points))

    def dot(self, x, y):
        self.parts.append(f'<circle cx="{x:g}" cy="{y:g}" r="1.6" class="dot"/>')

    def bubble(self, x, y):
        self.parts.append(f'<circle cx="{x + 3:g}" cy="{y:g}" r="3"/>')
        return x + 6

    def gate(self, kind, x, y, n, invert=False):
        """Draw an n-input gate with top-left at (x, y); return (input points, output point)."""
        h = max(2 * PITCH, n * PITCH)
        top = y + (h - PITCH * (n - 1)) / 2
        ys = [top + PITCH * i for i in range(n)]
        w = GATE_W
        if kind in ("buf", "not"):
            w, h = 20, 20
            ys = [y + 10]
            self.path(f"M{x},{y} L{x + w},{y + h / 2} L{x},{y + h} Z")
            ins = [(x, ys[0])]
        elif kind == "and":
            self.path(f"M{x},{y} H{x + w / 2} A{w / 2},{h / 2} 0 0 1 {x + w / 2},{y + h} H{x} Z")
            ins = [(x, yi) for yi in ys]
        else:  # or / xor: curved back, shifted right by 4 for the extra xor curve
            c = 8
            bx = x + 4 if kind == "xor" else x
            self.path(f"M{bx},{y} Q{bx + w * 0.6},{y} {x + w},{y + h / 2} "
                      f"Q{bx + w * 0.6},{y + h} {bx},{y + h} Q{bx + c},{y + h / 2} {bx},{y} Z")
            if kind == "xor":
                self.path(f"M{x},{y} Q{x + c},{y + h / 2} {x},{y + h}")
            ins = []
            for yi in ys:
                t = (yi - y) / h
                ins.append((x + 2 * t * (1 - t) * c, yi))
        out = (x + w, y + h / 2)
        if invert:
            out = (self.bubble(*out), out[1])
        return ins, out

    def pin(self, name, x, y, label=True):
        self.pins.append((name, x, y))
        if label:
            anchor = "start" if x == 0 else "end"
            dx = 1.5 if x == 0 else -1.5
            self.parts.append(f'<text x="{x + dx:g}" y="{y - 1.5:g}" class="pinlabel" '
                              f'style="text-anchor:{anchor}">{name}</text>')

    def template(self, cell_type, width, height, box):
        body = []
        if box:
            body.append(f'<rect x="0" y="-2" width="{width}" height="{height + 4}" class="cellbox"/>')
        body.append(f'<text x="{width / 2:g}" y="-4" class="nodelabel celltype">{cell_type}</text>')
        body += self.parts
        body += [f'<g s:x="{x:g}" s:y="{y:g}" s:pid="{name}"/>' for name, x, y in self.pins]
        return (f'<g s:type="{cell_type}" transform="translate(0,0)" s:width="{width:g}" '
                f's:height="{height:g}">\n  <s:alias val="{cell_type}"/>\n  '
                + "\n  ".join(body) + "\n</g>")


def route(d, nets, trunk_x):
    """Connect each source point to its target points through its own vertical trunk."""
    for (src, targets), tx in zip(nets, trunk_x):
        ys = [src[1]] + [t[1] for t in targets]
        d.line(src, (tx, src[1]))
        if max(ys) > min(ys):
            d.line((tx, min(ys)), (tx, max(ys)))
        for t in targets:
            d.line((tx, t[1]), t)
            if len(targets) > 1 or min(ys) < t[1] < max(ys):
                d.dot(tx, t[1])


def simple(cell_type, kind, pins, invert):
    d = Drawing()
    n = len(pins)
    x0 = 6
    if kind in ("buf", "not"):
        ins, out = d.gate(kind, x0, 0, 1, invert)
        height = 20
    else:
        ins, out = d.gate(kind, x0, 0, n, invert)
        height = max(2 * PITCH, n * PITCH)
    for name, (x, y) in zip(pins, ins):
        d.line((0, y), (x, y))
        d.pin(name, 0, y, label=False)
    width = out[0] + 6
    d.line(out, (width, out[1]))
    d.pin("Y", width, out[1], label=False)
    return d.template(cell_type, width, height, box=False)


def and_or(cell_type, groups, inner, outer, invert):
    """AO/OA/AOI/OAI cells: a column of inner gates (one per multi-pin group) feeding one outer gate."""
    d = Drawing()
    inner_x = 14  # leaves room for the pin labels
    trunk0 = inner_x + GATE_W + 6
    outer_x = trunk0 + 4 * len(groups) + 6
    signals, y = [], 0
    for group in groups:
        if len(group) == 1:
            d.pin(group[0], 0, y + 5)
            signals.append((0, y + 5))
            y += PITCH + 5
        else:
            ins, out = d.gate(inner, inner_x, y, len(group))
            for name, (x, yi) in zip(group, ins):
                d.line((0, yi), (x, yi))
                d.pin(name, 0, yi)
            signals.append(out)
            y += max(2 * PITCH, len(group) * PITCH) + 5
    height = y - 5
    outer_h = max(2 * PITCH, len(groups) * PITCH)
    ins, out = d.gate(outer, outer_x, (height - outer_h) / 2, len(groups), invert)
    # Give each signal its own trunk so vertical runs never overlap: signals moving down use
    # trunks right-to-left from the top, signals moving up use them right-to-left from the bottom.
    order = sorted(range(len(groups)), key=lambda j: signals[j][1] if ins[j][1] >= signals[j][1] else -signals[j][1])
    trunks = [0] * len(groups)
    down = [j for j in order if ins[j][1] > signals[j][1]]
    up = [j for j in order if ins[j][1] < signals[j][1]]
    for rank, j in enumerate(down):
        trunks[j] = trunk0 + 4 * (len(groups) - 1 - rank)
    for rank, j in enumerate(up):
        trunks[j] = trunk0 + 4 * (len(groups) - 1 - rank)
    for j in range(len(groups)):
        if ins[j][1] == signals[j][1]:
            trunks[j] = trunk0
    route(d, [(signals[j], [ins[j]]) for j in range(len(groups))], trunks)
    width = out[0] + 6
    d.line(out, (width, out[1]))
    d.pin("Y", width, out[1], label=False)
    return d.template(cell_type, width, max(height, outer_h), box=True)


def half_adder(cell_type):
    """HAxp5: SN = XNOR(A, B) (inverted sum), CON = NAND(A, B) (inverted carry)."""
    d = Drawing()
    gx = 12 + 4 * 2 + 4
    sn_in, sn_out = d.gate("xor", gx, 0, 2, invert=True)
    con_in, con_out = d.gate("and", gx, 30, 2, invert=True)
    pins = {"A": sn_in[0][1], "B": sn_in[1][1]}
    for name, y in pins.items():
        d.pin(name, 0, y)
    route(d, [((0, pins["A"]), [sn_in[0], con_in[0]]), ((0, pins["B"]), [sn_in[1], con_in[1]])], [12, 16])
    width = max(sn_out[0], con_out[0]) + 18  # room for the output labels
    for name, out in (("SN", sn_out), ("CON", con_out)):
        d.line(out, (width, out[1]))
        d.pin(name, width, out[1])
    return d.template(cell_type, width, 50, box=True)


def full_adder(cell_type):
    """FAx1: SN = XNOR(A, B, CI) (inverted sum), CON = NOT majority(A, B, CI) (inverted carry)."""
    d = Drawing()
    gx = 12 + 4 * 3 + 4
    sn_in, sn_out = d.gate("xor", gx, 0, 3, invert=True)
    pairs = (("A", "B"), ("A", "CI"), ("B", "CI"))
    ands = [d.gate("and", gx, 40 + 25 * k, 2) for k in range(3)]
    pins = dict(zip(("A", "B", "CI"), (p[1] for p in sn_in)))
    for name, y in pins.items():
        d.pin(name, 0, y)
    targets = {name: [sn_in[i]] for i, name in enumerate(pins)}
    for (ins, _), pair in zip(ands, pairs):
        for name, point in zip(pair, ins):
            targets[name].append(point)
    route(d, [((0, pins[n]), targets[n]) for n in pins], [12, 16, 20])
    ox = ands[0][1][0] + 4 * 3 + 6
    nor_in, con_out = d.gate("or", ox, 40 + 25 - 5, 3, invert=True)
    route(d, [(out, [nor_in[k]]) for k, (_, out) in enumerate(ands)],
          [ands[0][1][0] + 12, ands[0][1][0] + 4, ands[0][1][0] + 12])
    width = max(sn_out[0], con_out[0]) + 18  # room for the output labels
    for name, out in (("SN", sn_out), ("CON", con_out)):
        d.line(out, (width, out[1]))
        d.pin(name, width, out[1])
    return d.template(cell_type, width, 110, box=True)


def dff(cell_type):
    """DFFHQNx1: rising-edge flip-flop with an inverted output QN."""
    d = Drawing()
    d.path("M6,0 H36 V40 H6 Z")
    d.path("M6,25 L11,30 L6,35")
    d.parts.append('<text x="9" y="13" class="pinlabel">D</text>')
    d.parts.append('<text x="33" y="13" class="pinlabel" style="text-anchor:end">Q</text>')
    d.line((0, 10), (6, 10))
    d.line((0, 30), (6, 30))
    x = d.bubble(36, 10)
    d.line((x, 10), (x + 4, 10))
    d.pin("D", 0, 10, label=False)
    d.pin("CLK", 0, 30, label=False)
    d.pin("QN", x + 4, 10, label=False)
    return d.template(cell_type, x + 4, 40, box=False)


def tie(cell_type, pin, value):
    """TIEHI / TIELO: a constant 1 or 0 driver."""
    d = Drawing()
    d.path("M0,0 H20 V20 H0 Z")
    d.parts.append(f'<text x="10" y="14" class="pinlabel" style="text-anchor:middle">{value}</text>')
    d.line((20, 10), (26, 10))
    d.pin(pin, 26, 10, label=False)
    return d.template(cell_type, 26, 20, box=False)


def base_type(cell_type):
    return re.sub(r"x[0-9p]+f?$", "", cell_type)


def template_for(cell_type, pins):
    base = base_type(cell_type)
    inputs = sorted(p for p in pins if p not in OUTPUT_PINS)
    if base in ("INV", "BUF", "CKINVDC", "HB1", "HB2", "HB3", "HB4"):
        base = "INV" if base == "CKINVDC" else "BUF" if base.startswith("HB") else base
        return simple(cell_type, "not" if base == "INV" else "buf", inputs, invert=base == "INV")
    if m := re.fullmatch(r"(N?)(AND|OR)(\d)", base):
        return simple(cell_type, m[2].lower(), inputs, invert=bool(m[1]))
    if m := re.fullmatch(r"(XN?OR)2", base):
        return simple(cell_type, "xor", inputs, invert=m[1] == "XNOR")
    if m := re.fullmatch(r"(AO|OA)(I?)(\d+)", base):
        letters = sorted({p[0] for p in inputs})
        groups = [sorted(p for p in inputs if p[0] == letter) for letter in letters]
        inner, outer = ("and", "or") if m[1] == "AO" else ("or", "and")
        return and_or(cell_type, groups, inner, outer, invert=bool(m[2]))
    if base == "HA":
        return half_adder(cell_type)
    if base == "FA":
        return full_adder(cell_type)
    if base in ("TIEHI", "TIELO"):
        return tie(cell_type, "H" if base == "TIEHI" else "L", 1 if base == "TIEHI" else 0)
    if base == "DFFHQN":
        return dff(cell_type)
    raise ValueError(f"no symbol for {cell_type}")


def default_skin():
    """netlistsvg's own skin (ports, splits, joins), from the npx cache."""
    subprocess.run(["npx", "--yes", "netlistsvg", "--help"], capture_output=True)
    found = sorted(Path.home().glob(".npm/_npx/*/node_modules/netlistsvg/lib/default.svg"))
    if not found:
        raise SystemExit("netlistsvg not found; needs Node.js and npx")
    return found[-1]


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("run", type=Path, help="results folder containing 6_final.v")
    parser.add_argument("-o", "--out", default="gates.svg", help="output name inside the run folder")
    args = parser.parse_args()
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        subprocess.run(["yosys", "-q", "-p", f"read_verilog {args.run.resolve()/'6_final.v'}; write_json {tmp/'raw.json'}"],
                       check=True)
        data = json.loads((tmp/"raw.json").read_text())
        (top, module), = data["modules"].items()
        pins = {}
        for cell in module["cells"].values():
            cell["type"] = cell["type"].replace("_ASAP7_75t_R", "")
            cell["port_directions"] = {p: "output" if p in OUTPUT_PINS else "input" for p in cell["connections"]}
            pins.setdefault(cell["type"], set()).update(cell["connections"])
        (tmp/"netlist.json").write_text(json.dumps(data))

        skin_src = default_skin().read_text()
        templates = "\n".join(template_for(t, p) for t, p in sorted(pins.items()))
        skin = skin_src.replace("</style>", STYLE + "</style>").replace("</svg>", templates + "\n</svg>")
        (tmp/"skin.svg").write_text(skin)
        out = args.run/args.out
        subprocess.run(["npx", "--yes", "netlistsvg", str(tmp/"netlist.json"), "--skin", str(tmp/"skin.svg"),
                        "-o", str(out.resolve())], check=True)
    counts = {}
    for cell in module["cells"].values():
        counts[cell["type"]] = counts.get(cell["type"], 0) + 1
    print(f"{out}: {sum(counts.values())} cells of {len(counts)} types")


if __name__ == "__main__":
    main()
