# Circuits

The two designs worth keeping, each with its logic diagram, equations and
Verilog. Both use the same fixed memory and comparator; only the learned
controller differs.

| Folder | What it is | Area (Yosys + ASAP7) | Memory bits | Average / median error | Within 34 cm |
|---|---|---|---|---|---|
| [`final/`](final/) | The chosen design, taken to a routed layout in [`../asic/`](../asic/README.md) | 26.83 µm², 295 cells | 18 | 0.363 / 0.151 m | 76.2% |
| [`area-optimized/`](area-optimized/) | The same design after a search for smaller area | 24.68 µm², 253 cells | 17 | 0.364 / 0.162 m | 76.9% |

Errors are measured on the validation recordings with random photon counts
(16 to 256) and background light. Areas are logic-only synthesis estimates; the
routed layout adds clock, power and timing cells.

## Files in each folder

| File | Purpose |
|---|---|
| `controller.svg` | Picture of the learned controller, with unused gates removed |
| `equations.txt` | The controller's logic written as simplified equations |
| `core.v` | The whole circuit in Verilog, including the fixed memory and comparator |
| `circuit.json` | Every gate's function and wiring, readable by the code in [`../spad/`](../spad/) |

## Reading the equations

The controller reads yes/no signals from the comparator and its own memory
bits:

| Signal | Meaning |
|---|---|
| `near1` ... `near16` | The photon is within 1, 2, 4, 8 or 16 steps of the current guess |
| `gt`, `lt` | The photon arrived later or earlier than the guess |
| `zero`, `conf2`, `conf4`, `conf8`, `full` | The confidence counter is 0, at least 2, 4, 8, or 15 |
| `state0` ... `state3` | The extra memory bits the search can use freely |

Its outputs decide what the photon does: `do_replace` (take the photon's time
as the new guess), `do_up` and `do_down` (move the guess one step later or
earlier), `do_inc` and `do_dec` (raise or lower the confidence), and
`next_state0` ... `next_state3` (update the extra memory bits).

To redraw a diagram from the `SPAD/` folder:

```bash
python -m spad.hardware.diagram circuits/final/circuit.json --out circuits/final --no-netlist
```
