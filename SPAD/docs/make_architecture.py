"""Draw the photon-stream core block diagram. Usage: python docs/make_architecture.py OUT.svg [kaggle|police]"""
from html import escape
from pathlib import Path
import sys
import textwrap

W, H = 1420, 1560
LEFT, LW = 60, 640          # main flow column
TX, TW = 770, 92            # explanation column x, wrap width (chars)
COL = {"io": "#dcfce7", "mem": "#ede9fe", "fixed": "#dbeafe", "learn": "#fef3c7"}
svg = []

# Per-circuit text. Usage: python docs/make_architecture.py OUT.svg [profile]
PROFILES = {
    "kaggle": {
        "run": "rule-s4-seed0 (first Kaggle batch)",
        "photons": "64 photons per pixel",
        "readout": "after 64 photons: bin = candidate - offset",
        "output_note": "The final candidate is the pixel's range estimate. One constant offset is fitted "
            "on the training captures (-5.9 bins for this circuit): it locks onto the pulse's early "
            "edge, about 0.66 m short, and a fixed shift corrects that. Result: ASAP7 area 20.7, 230 cells, "
            "0 netlist mismatches, 0.229 m mean error on validation at 64 photons.",
        "training": ["Soft -> hard: temperature 2.0 -> 0.15; straight-through after 30% of steps",
                     "Bilevel DARTS: truth tables on captures 1-4, routing on 5, pick on 6",
                     "Rollback to the best state if error jumps 25% (stops collapse)",
                     "Then evolutionary search: 256 mutants x 800 generations on hard circuits",
                     "Area cost from ASAP7 Liberty cells added to the loss",
                     "Captures 7-10 held out for one final test"],
        "learned_title": "What it learned (1 of 48 gates does real work)",
        "learned": ["replace = zero           start over when confidence is 0",
                    "inc     = near8          +1 confidence for a photon within 8 bins",
                    "dec     = !gt & !zero    -1 for a photon at or before the guess",
                    "down    = near2          step 1 bin earlier for a photon within 2",
                    "up      = 0              never steps later; state bits unused"],
        "verdict": ["=> locks onto a photon cluster, then walks to its early edge", "   (a leading-edge tracker)"],
    },
    "police": {
        "run": "rule-s4-seed0 (police batch, randomized conditions)",
        "photons": "16-256 photons per pixel",
        "readout": "after the frame: bin = candidate - offset",
        "output_note": "The final candidate is the pixel's range estimate. One constant offset is fitted "
            "on the training captures (-2.7 bins for this circuit, about 0.31 m early). Result: ASAP7 area "
            "20.2, 228 cells, 0 netlist mismatches. On validation with random photon counts (16-256) and "
            "extra ambient (0-0.6): 0.568 m mean, 0.157 m median, 74% within 3 bins.",
        "training": ["16-256 photons and 0-0.6 extra ambient, drawn per sample",
                     "Bilevel DARTS: tables on captures 1-4 + 3 scenes, routing on 5 + 1 scene",
                     "Physics police: CFAR + Poisson likelihood, label-free",
                     "Evolutionary search: 32 mutants x 400 generations, bit-packed",
                     "Area cost from ASAP7 Liberty cells added to the loss",
                     "Held out: captures 7-10 and the outdoor parking scene"],
        "learned_title": "What it learned (3 of 48 gates do real work)",
        "learned": ["replace = zero           start over when confidence is 0",
                    "inc     = conf2|near16   +1 unless confidence <2 and photon far",
                    "dec     = !near16        -1 for a photon more than 16 bins away",
                    "down    = lt & near8     1 bin earlier for a photon <=8 bins earlier",
                    "up      = 0              never steps later; state bits unused"],
        "verdict": ["=> far photons only reset a weak lock; strong locks hold.",
                    "   Walks to the cluster's early edge (leading-edge tracker)"],
    },
}
PROFILE = PROFILES[sys.argv[2] if len(sys.argv) > 2 else "kaggle"]


def text(x, y, s, size=13, weight="normal", anchor="start", fill="#111", family=None):
    f = f' font-family="{family}"' if family else ""
    svg.append(f'<text x="{x}" y="{y}" font-size="{size}" font-weight="{weight}" '
               f'text-anchor="{anchor}" fill="{fill}" style="white-space:pre"{f}>{escape(s)}</text>')


def box(x, y, w, h, kind, title, lines, dashed=False):
    dash = ' stroke-dasharray="6 4"' if dashed else ""
    svg.append(f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="10" fill="{COL[kind]}" '
               f'stroke="#334155" stroke-width="1.5"{dash}/>')
    text(x + 14, y + 24, title, 15, "bold")
    for i, line in enumerate(lines):
        text(x + 14, y + 48 + i * 19, line, 13, family="Menlo,Consolas,monospace")


def note(y, heading, body):
    text(TX, y, heading, 13, "bold", fill="#334155")
    for i, line in enumerate(textwrap.wrap(body, TW)):
        text(TX, y + 19 + i * 18, line, 13, fill="#374151")


def arrow(x1, y1, x2, y2, label=None):
    svg.append(f'<line x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}" stroke="#334155" stroke-width="2" marker-end="url(#a)"/>')
    if label:
        text(x1 + 10, (y1 + y2) / 2 + 4, label, 12, fill="#475569")


svg.append(f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}" '
           'font-family="Helvetica,Arial,sans-serif" xml:space="preserve">')
svg.append('<defs><marker id="a" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" '
           'orient="auto-start-reverse"><path d="M0,0 L10,5 L0,10 z" fill="#334155"/></marker></defs>')
svg.append(f'<rect width="{W}" height="{H}" fill="white"/>')
text(LEFT, 42, "Photon-stream range core: one pixel, one photon per clock cycle", 24, "bold")
text(LEFT, 68, "Differentiable logic-gate network with DARTS routing, synthesized to ASAP7 standard cells. "
     f"Example numbers from {PROFILE['run']}.", 14, fill="#475569")
for i, (kind, label) in enumerate([("io", "input / output"), ("mem", "memory (flip-flops)"),
                                   ("fixed", "fixed hardware"), ("learn", "learned logic gates")]):
    x = TX + i * 158
    svg.append(f'<rect x="{x}" y="88" width="16" height="16" rx="3" fill="{COL[kind]}" stroke="#334155"/>')
    text(x + 22, 101, label, 12, fill="#334155")

# Row 1: input + registers
box(LEFT, 120, 300, 120, "io", "Input: SPAD photon arrival",
    ["10-bit time bin per photon", "bins 0-671, 750 ps each", "= 11.2 cm of range per bin", PROFILE["photons"]])
box(LEFT + 340, 120, 300, 120, "mem", "Pixel registers",
    ["candidate   10 bits", "            (range guess)", "confidence   4 bits (0-15)", "state      0-4 learned bits"])
note(128, "INPUT", "The single-photon detector reports when each photon arrives, as a bin number; distance "
     "is bin x 11.2 cm. Training replays real photon streams drawn from SP-TransientBench histograms.")
note(196, "PIXEL MEMORY", "Only 14-18 flip-flops per pixel, instead of a 672-bin histogram (8,064 bits). "
     "No histogram is ever stored.")

# Layer 0: features
y = 300
box(LEFT, y, LW, 150, "fixed", "Layer 0 - Comparator and flag encoder (fixed)",
    ["|arrival - candidate| <= 1,2,4,8,16  ->  near1 ... near16",
     "arrival > candidate -> gt     arrival < candidate -> lt",
     "confidence: =0 zero, >=2/4/8 conf2/4/8, =15 full",
     "+ const0, const1, state0-3",
     "=> 18 one-bit signals"])
note(y + 8, "FEATURES (not learned)", "Logic gates can only read bits, so numbers become yes/no flags. "
     "Distance uses a thermometer code: a photon 3 bins away sets near4, near8 and near16 but not near1 "
     "or near2. During training the flags are smooth sigmoids so gradients can flow. In silicon they are "
     "plain comparator outputs.")
arrow(LEFT + 150, 240, LEFT + 150, y)
arrow(LEFT + 490, 240, LEFT + 490, y)

# Learned layers
layers = [
    (500, "Layer 1 - 16 learned logic gates",
     ["each gate reads 2 of the 18 signals", "and applies one 2-input Boolean function"],
     "LEARNED LOGIC", "Each gate learns two things. (1) Routing: which two wires it reads. DARTS keeps a "
     "softmax weight over every possible wire and sharpens it until one wins; in silicon it is just a "
     "wire. (2) A 4-entry truth table: the output for inputs 00, 01, 10, 11. It is trained as "
     "probabilities (a 'light' gate) and frozen to 0/1, which picks one of 16 functions (AND, OR, XOR, "
     "NAND...)."),
    (650, "Layer 2 - 16 learned logic gates",
     ["each gate reads 2 of 34 wires:", "the 18 signals + layer 1's 16 outputs"],
     "DEPTH", "Later layers can read the original flags directly (a skip connection) or the previous "
     "layer, so a decision can be 1, 2 or 3 gates deep. All 48 gates are combinational, so one photon "
     "passes through every layer within a single clock cycle."),
    (800, "Layer 3 - 16 learned gates -> control signals",
     ["reads 2 of 34 wires (18 signals + layer 2)", "out: next_state0-3, replace, up, down,",
      "     inc, dec   (other 7 gates unused)"],
     "OUTPUT HEAD", "The last layer's gates have fixed meanings: state bits loop back to memory, and five "
     "action bits tell the datapath what to do with this photon. Yosys deletes unused and constant "
     "gates, so they cost no area."),
]
prev = y + 150
for ly, title, lines, head, body in layers:
    h = 110 if len(lines) == 2 else 125
    box(LEFT, ly, LW, h, "learn", title, lines)
    note(ly + 8, head, body)
    arrow(LEFT + LW / 2, prev, LEFT + LW / 2, ly)
    prev = ly + h

# Update datapath
y = 980
box(LEFT, y, LW, 130, "fixed", "Layer 4 - Update datapath (fixed)",
    ["replace  -> candidate = arrival",
     "up / down -> candidate +/- 1 bin (cancel if both)",
     "inc / dec -> confidence +/- 1, held within 0-15",
     "state <- next_state   on the clock edge"])
note(y + 8, "UPDATE", "A fixed adder and multiplexer apply the actions on the clock edge. The learned "
     "network never does arithmetic, it only decides. That is why the core is tiny: the range estimator "
     "becomes a small state machine that runs once per photon.")
arrow(LEFT + LW / 2, prev, LEFT + LW / 2, y)

# Feedback loop (right of column) and arrival bypass (left of column)
fx = LEFT + LW + 28
svg.append(f'<path d="M{LEFT + LW},{y + 65} H{fx} V180 H{LEFT + LW + 6}" fill="none" stroke="#7c3aed" '
           'stroke-width="2" marker-end="url(#a)"/>')
svg.append(f'<text x="{fx + 8}" y="640" font-size="12" fill="#7c3aed" transform="rotate(90 {fx + 8} 640)" '
           'text-anchor="middle">new candidate, confidence, state -> next photon</text>')
bx = LEFT - 30
svg.append(f'<path d="M{LEFT},180 H{bx} V{y + 30} H{LEFT - 6}" fill="none" stroke="#16a34a" '
           'stroke-width="2" stroke-dasharray="6 4" marker-end="url(#a)"/>')
svg.append(f'<text x="{bx - 8}" y="640" font-size="12" fill="#16a34a" transform="rotate(-90 {bx - 8} 640)" '
           'text-anchor="middle">arrival (loaded on replace)</text>')

# Readout
y2 = 1160
box(LEFT, y2, LW, 110, "io", "Output - range readout",
    [PROFILE["readout"],
     "range = (bin - 17) x 0.1124 m - pixel offset",
     "then reset the registers for the next frame"])
note(y2 + 8, "OUTPUT", PROFILE["output_note"])
arrow(LEFT + LW / 2, y + 130, LEFT + LW / 2, y2)

# Bottom panels
py = 1310
svg.append(f'<rect x="{LEFT}" y="{py}" width="{LW}" height="225" rx="10" fill="#f8fafc" stroke="#64748b" '
           'stroke-dasharray="6 4" stroke-width="1.5"/>')
text(LEFT + 14, py + 26, "Training only (none of this is in the chip)", 15, "bold")
for i, line in enumerate(PROFILE["training"]):
    text(LEFT + 14, py + 54 + i * 26, "- " + line, 13, fill="#334155")
lx = TX - 10
svg.append(f'<rect x="{lx}" y="{py}" width="{W - lx - 40}" height="225" rx="10" fill="#fffbeb" '
           'stroke="#b45309" stroke-width="1.5"/>')
text(lx + 14, py + 26, PROFILE["learned_title"], 15, "bold")
for i, line in enumerate(PROFILE["learned"]):
    text(lx + 14, py + 54 + i * 24, line, 13, family="Menlo,Consolas,monospace")
for k, line in enumerate(PROFILE["verdict"]):
    text(lx + 14, py + 54 + (5 + k) * 24 + 8, line, 13, "bold", fill="#92400e")

svg.append("</svg>")
Path(sys.argv[1]).write_text("\n".join(svg) + "\n")
