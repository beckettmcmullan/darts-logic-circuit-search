# The final circuit

The chosen design (batch 3, random start, 4 memory bits, seed 0). The
[area-optimized README](../README.md) explains how it works and how it was found. Its chip
layout is in [`../asic/results/`](../asic/results/2026-11-10_final_batch3-random-s4-seed0_asap7_1500ps/README.md).

| File | What it is |
|---|---|
| `circuit.json` | The trained circuit: which wires each gate reads and its truth table |
| `core.v` | The circuit as Verilog, generated from `circuit.json` |
| `controller.svg` | Diagram of the learned gates that do real work |
| `equations.txt` | The same logic as one Boolean equation per output |
| `gates.svg` | Every logic cell of the routed ASAP7 layout |
| `area-optimized.json` | A smaller variant, kept as data only (see below) |

**`area-optimized.json`** is the same search rerun with chip area as the goal,
starting from this circuit. It is 8% smaller with the same accuracy (section 5 of
the area-optimized README) and has no layout run. Only its `circuit.json` is kept; its Verilog
and diagrams can be regenerated from it with the commands below.

## circuit.json

A plain JSON file with these fields (`area-optimized.json` has the same ones):

| Field | Meaning |
|---|---|
| `format` | `photon-stream-core-v1`, the file format name |
| `config` | The circuit's shape: `state_bits` (memory bits, 4), `width` (gates per layer, 16), `layers` (3), `conf_bits` (confidence counter width, 4), `cand_bits` (distance guess width, 10) and `windows` (the "within N steps" comparator sizes: 1, 2, 4, 8, 16) |
| `inputs` | The 18 named wires the first layer can read, in order: the comparator flags (`near1` to `near16`, `gt`, `lt`), the confidence flags (`zero`, `conf2`, `conf4`, `conf8`, `full`), the constants `const0` and `const1`, and the memory bits `state0` to `state3` |
| `actions` | The 5 things a photon can do: `replace`, `up`, `down`, `inc`, `dec` |
| `layers` | Three layers of 16 gates. Each layer has `inputs` (for each gate, the two wire numbers it reads) and `truth_tables` (for each gate, its 4 output bits for input pairs 00, 01, 10, 11) |
| `offset_bins` | A fixed correction, in time steps, for the answer. `core.v` does not use it |
| `budget` | Photon count the circuit was prepared for (256) |
| `conditions` | The photon counts (`min_photons`, `max_photons`) and background level (`max_background`) it was trained on |

Wire numbers in `layers[*].inputs` are positions in a list. For layer 1, numbers
0 to 17 are the entries of `inputs`. For layers 2 and 3, numbers 0 to 17 are
still the `inputs` and 18 to 33 are the 16 gates of the layer before. In the last
layer, the first 4 gates give the new memory bits and the next 5 give the
`actions`. The other gates in that layer are not used.

## core.v

A Verilog module named `photon_core` that implements the circuit. It holds the
hand-made comparator, the gates written as one-line truth-table expressions,
and the registers for the guess, the confidence count and the memory bits. It is
generated, so do not edit it by hand.

`core.v` is the same file as
[`../asic/designs/photon_core/photon_core.v`](../asic/designs/photon_core/photon_core.v),
the input to the layout flow. The `asic` copy is the one the flow reads, so you
can swap in another circuit there without changing this folder.

## Gate diagrams

| File | What it shows |
|---|---|
| `controller.svg` | The learned gates only, after removing constant gates, pass-throughs and gates whose output is never used. Inputs are on the left (blue), gates in the middle, and the next memory bits and actions on the right (green). This circuit keeps 26 of its 48 gates (the area-optimized one, 24). |
| `equations.txt` | A minimized Boolean equation for each memory bit and action. Flag combinations the comparator can never produce (for example `near1` without `near2`) are treated as don't-cares, so the equations are shorter than the gates. |
| `gates.svg` | All 381 logic cells of the routed ASAP7 netlist (`6_final.v` in [`../asic/results/`](../asic/results/2026-11-10_final_batch3-random-s4-seed0_asap7_1500ps/README.md)) drawn with logic-gate symbols, including the hand-made comparator, counters and clock buffers. Compound cells are drawn as their internal gates inside a dashed outline. The image is large, so open it and zoom in. |

To redraw `controller.svg` and `equations.txt` (needs `sympy`), from `SPAD/area-optimized/`:

```bash
python -m asic.synthesis.diagram circuit/circuit.json --out circuits --no-netlist --title random-s4-seed0
```

This also rewrites `core.v` (with identical contents). For the area-optimized circuit,
write to a different folder so these files are not overwritten:

```bash
python -m asic.synthesis.diagram circuit/area-optimized.json --out runs/area-optimized --no-netlist --title area-optimized
```

To redraw `gates.svg` from a routed layout (needs Yosys and Node.js):

```bash
python asic/draw_gates.py asic/results/2026-11-10_final_batch3-random-s4-seed0_asap7_1500ps -o circuit/gates.svg
```

## Regenerate core.v

The function is `stream_verilog(circuit, module="photon_core")` in
[`asic/synthesis/verilog.py`](../asic/synthesis/verilog.py). It takes the loaded
JSON and returns the Verilog text. From the `SPAD/area-optimized/` folder:

```bash
python -c "import json; from asic.synthesis.verilog import stream_verilog; \
  print(stream_verilog(json.load(open('circuit/circuit.json'))), end='')" > circuit/core.v
```
