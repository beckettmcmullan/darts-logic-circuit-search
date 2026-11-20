# Saved circuits

Two trained circuits, each as the circuit description (`circuit.json`) and the
Verilog generated from it (`core.v`).

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

## Regenerate core.v

The function is `stream_verilog(circuit, module="photon_core")` in
[`spad/hardware/verilog.py`](../spad/hardware/verilog.py). It takes the loaded
JSON and returns the Verilog text. From the `SPAD/` folder:

```bash
python -c "import json; from spad.hardware.verilog import stream_verilog; \
  print(stream_verilog(json.load(open('circuits/final/circuit.json'))), end='')" > circuits/final/core.v
```
