# Saved circuits

Two trained circuits. Each folder holds the circuit description (`circuit.json`), the
Verilog generated from it (`core.v`), the learned logic as a gate diagram
(`controller.svg`) and as Boolean equations (`equations.txt`).
`final/` also has `gates.svg`, every standard cell of its routed chip layout.

| Folder | What it is |
|---|---|
| `final/` | The chosen design: batch 3, random start, 4 memory bits, seed 0. The [SPAD README](../README.md) explains it. Its layout is in [`../asic/results/`](../asic/results/2026-11-10_final_batch3-random-s4-seed0_asap7_1500ps/README.md). |
| `area-optimized/` | The same search rerun with chip area as the goal, starting from the final circuit. Smaller, with the same accuracy (see section 5 of the SPAD README). It has no layout run. |

## circuit.json

A plain JSON file. Both circuits have the same fields:

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

`final/core.v` is the same file as
[`../asic/designs/photon_core/photon_core.v`](../asic/designs/photon_core/photon_core.v),
the input to the layout flow. The `asic` copy is the one the flow reads, so you
can swap in another circuit there without changing these folders.
`area-optimized/core.v` has not been run through the flow.

## Gate diagrams

| File | What it shows |
|---|---|
| `controller.svg` | The learned gates only, after removing constant gates, pass-throughs and gates whose output is never used. Inputs are on the left (blue), gates in the middle, and the next memory bits and actions on the right (green). The final design keeps 26 of its 48 gates, the area-optimized one 24. |
| `equations.txt` | A minimized Boolean equation for each memory bit and action. Flag combinations the comparator can never produce (for example `near1` without `near2`) are treated as don't-cares, so the equations are shorter than the gates. |
| `final/gates.svg` | All 381 logic cells of the routed ASAP7 netlist (`6_final.v` in [`../asic/results/`](../asic/results/2026-11-10_final_batch3-random-s4-seed0_asap7_1500ps/README.md)) drawn with logic-gate symbols, including the hand-made comparator, counters and clock buffers. Compound cells are drawn as their internal gates inside a dashed outline. The image is large, so open it and zoom in. |

To redraw `controller.svg` and `equations.txt` (needs `sympy`), from `SPAD/`:

```bash
python -m asic.synthesis.diagram circuits/final/circuit.json --out circuits/final --no-netlist
```

This also rewrites `core.v`. The diagram title is taken from the folder name.
To redraw `gates.svg` from a routed layout (needs Yosys and Node.js):

```bash
python asic/draw_gates.py asic/results/2026-11-10_final_batch3-random-s4-seed0_asap7_1500ps -o circuits/final/gates.svg
```

## Regenerate core.v

The function is `stream_verilog(circuit, module="photon_core")` in
[`asic/synthesis/verilog.py`](../asic/synthesis/verilog.py). It takes the loaded
JSON and returns the Verilog text. From the `SPAD/` folder:

```bash
python -c "import json; from asic.synthesis.verilog import stream_verilog; \
  print(stream_verilog(json.load(open('circuits/final/circuit.json'))), end='')" > circuits/final/core.v
```
