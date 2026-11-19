# ASIC layout (OpenROAD-flow-scripts, ASAP7)

Takes a trained circuit from Verilog to a routed GDSII layout with OpenROAD-flow-scripts
in Docker. ASAP7 is a predictive 7 nm teaching library: the results are realistic
estimates for exploration, not a manufacturable chip.

| Path | What it is |
|---|---|
| `designs/photon_core/` | Flow inputs: `photon_core.v` (exported from a `circuit.json`), `constraint.sdc` (1.5 ns clock), `config.mk` |
| `run_flow.sh` | Runs the whole flow in the `openroad/orfs` image; output goes to `flow/` (scratch, gitignored) |
| `results/` | Saved runs, one dated folder each, with a README |

## Results

| Folder | Circuit | Die | Fastest clock | DRC |
|---|---|---|---|---|
| `results/2026-11-10_final_batch3-random-s4-seed0_asap7_1500ps` | **Final design** (batch 3 random-s4-seed0) | 110 µm² (10.5 µm square) | 682 ps (1.47 GHz) | 0 |

## Lay out another circuit (from SPAD/)

```sh
../.venv/bin/python -c "import json; from spad.hardware.verilog import stream_verilog; \
  open('asic/designs/photon_core/photon_core.v','w').write(stream_verilog(json.load(open('runs/<run>/circuit.json'))))"
asic/run_flow.sh
```
Then copy the GDS, reports and images from `asic/flow/` into a new dated folder under `results/`.
