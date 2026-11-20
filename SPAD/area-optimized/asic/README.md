# ASIC: synthesis and layout (ASAP7)

Everything that turns a trained circuit into hardware. [`synthesis/`](synthesis/README.md)
exports Verilog, checks it against the Python simulator, maps it to ASAP7 cells with Yosys
and estimates area and timing. The rest of this folder takes the Verilog to a routed GDSII
layout with OpenROAD-flow-scripts in Docker: synthesis, floorplan, placement, clock tree,
routing and final checks. ASAP7 is a predictive 7 nm teaching library: the results are realistic
estimates for exploration, not a manufacturable chip.

| Path | What it is |
|---|---|
| [`synthesis/`](synthesis/README.md) | Python package `asic.synthesis`: Verilog export, Yosys/ASAP7 synthesis and checks, timing and area estimates, controller diagrams |
| [`designs/photon_core/`](designs/photon_core/README.md) | Flow inputs: `photon_core.v` (exported from a `circuit.json`; currently the final design, same as [`../circuit/core.v`](../circuit/core.v)), `constraint.sdc` (1.5 ns clock), `config.mk` |
| `run_flow.sh` | Runs the whole flow in the `openroad/orfs` image; output goes to `flow/` (scratch, not tracked in git) |
| `draw_gates.py` | Draws a routed netlist (`6_final.v`) as a gate-symbol schematic. The final design's drawing is [`../circuit/gates.svg`](../circuit/gates.svg). Needs Yosys and Node.js |
| `results/` | Saved runs, one dated folder each, with a README |

## Results

| Folder | Circuit | Die | Fastest clock | DRC |
|---|---|---|---|---|
| `results/2026-11-10_final_batch3-random-s4-seed0_asap7_1500ps` | **Final design** (batch 3 random-s4-seed0) | 110 µm² (10.5 µm square) | 682 ps (1.47 GHz) | 0 |

## Lay out another circuit (from SPAD/area-optimized/)

You need Docker. The first run downloads the `openroad/orfs` image (several GB).
The script runs it as `linux/amd64`, which is emulated and slow on Apple
silicon. Set `ORFS_PLATFORM` (for example `ORFS_PLATFORM="--platform linux/arm64"`)
or `ORFS_IMAGE` to change that.

Export the Verilog from a `circuit.json`. Use a file from [`../circuit/`](../circuit/README.md)
or one your own training run wrote under `runs/` (not tracked in git). Then run the flow:

```sh
../../.venv/bin/python -c "import json; from asic.synthesis.verilog import stream_verilog; \
  open('asic/designs/photon_core/photon_core.v','w').write(stream_verilog(json.load(open('runs/<run>/circuit.json'))))"
asic/run_flow.sh
```
Then copy the GDS, reports and images from `asic/flow/` into a new dated folder under `results/`.
To draw the gates of the new netlist, run
`python asic/draw_gates.py asic/results/<run> -o circuit/gates.svg`.
