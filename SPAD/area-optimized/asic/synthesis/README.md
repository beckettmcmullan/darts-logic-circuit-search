# `asic.synthesis`: from a trained circuit to ASAP7 cells

Python code that takes a trained `circuit.json` and turns it into hardware numbers
before layout: Verilog, a check against the Python simulator, a Yosys mapping to
ASAP7 cells, area and timing estimates, and diagrams of the learned logic. The
OpenROAD layout flow that comes after this is one folder up, in [`../`](../README.md).

Run everything from `SPAD/area-optimized/`, as modules (`python -m asic.synthesis.<module>`).

| Module | What it does |
|---|---|
| `verilog.py` | `stream_verilog(circuit)` writes the synchronous module `photon_core` (ports `clk`, `rst`, `valid`, `arrival`, `candidate`): the fixed comparator and counters plus one combinational wire per learned gate. Also simulates a Yosys netlist in numpy. |
| `synth.py` | Checks that the netlist matches `training.core.stream_model.simulate_stream` bit for bit, then maps it with Yosys and ABC to ASAP7 cells and reports area. |
| `timing.py` | Reads the mapped netlist and the Liberty tables and returns a critical-path estimate without wires or placement. |
| `costs.py` | Builds `data/asap7/costs.json`, the area and delay of every two-input truth table. |
| `area_model.py`, `area_model.json` | A linear whole-core area estimate fitted to Yosys results. The area objective in `training/training/train_stream.py` uses it. |
| `diagram.py` | Draws the learned controller (`controller.svg`) and writes its minimized Boolean equations (`equations.txt`). Optionally also writes whole-core netlists in generic gates and in ASAP7 cells. |

ASAP7 is a predictive process design kit: the numbers are comparative estimates, not
figures for a manufacturable design. `costs.py` and `timing.py` use Liberty table values
directly, and `area_model.py` is a regression on Yosys results.

## Commands

```bash
python -m asic.synthesis.costs                                  # needs data/asap7 from training.dataset.download
python -m asic.synthesis.synth runs/NAME/circuit.json           # verify and synthesize
python -m asic.synthesis.timing runs/NAME/circuit.json          # critical-path estimate
python -m asic.synthesis.area_model --circuits 400              # refit area_model.json (slow: runs Yosys)
python -m asic.synthesis.diagram circuit/circuit.json --out circuits --no-netlist --title random-s4-seed0
```

`diagram.py` needs `sympy` for the equations. Without `--no-netlist` it also needs Yosys,
the ASAP7 libraries in `data/`, and Node.js (for `netlistsvg`). The diagram title is
`--title`, or else the name of the folder holding `circuit.json`. `--out` also gets a
fresh `core.v`, so point it at a new folder when drawing a circuit other than
`circuit/circuit.json`.
