# photon_core flow inputs

The three files OpenROAD-flow-scripts (ORFS) reads to lay out the photon core.
[`../../run_flow.sh`](../../run_flow.sh) points ORFS at `config.mk`. Inside the
Docker container `asic/` is mounted at `/work`, so the paths in these files
start with `/work`.

| File | Role |
|---|---|
| `photon_core.v` | The circuit as Verilog. Generated from a `circuit.json`; currently the final design, identical to [`circuit/core.v`](../../../circuit/core.v). See [`circuit/README.md`](../../../circuit/README.md) to regenerate it. |
| `constraint.sdc` | The timing goal: the clock and how late inputs arrive. |
| `config.mk` | Tells ORFS which design, library and files to use, and how big and dense to make the layout. |

## config.mk

A Makefile fragment of `export NAME = value` lines that ORFS reads as settings.

| Setting | Meaning |
|---|---|
| `PLATFORM = asap7` | The cell library and rules: ASAP7, a predictive 7 nm teaching library. Layouts from it are estimates and cannot be manufactured. |
| `DESIGN_NAME` | The Verilog module to build (`photon_core`). |
| `DESIGN_NICKNAME` | The name ORFS uses for output folders, so results go under `.../asap7/photon_core/base/`. |
| `VERILOG_FILES`, `SDC_FILE` | The two input files above. |
| `CORE_UTILIZATION = 45` | Percent of the core area that cells may fill. ORFS sizes the die from the cell area and this number. Lower leaves more room for wires. |
| `CORE_ASPECT_RATIO = 1` | Core height divided by width: a square. |
| `CORE_MARGIN = 0.5` | Space in µm between the core and the die edge. |
| `PLACE_DENSITY = 0.6` | How tightly the placer packs cells together. |
| `GPL_PLACE_IOS = 1` | Let the placer choose where the input and output pins go on the edge. |

## constraint.sdc

SDC (Synopsys Design Constraints) is a Tcl-based format that tells the tools
what speed the design must reach. Times are in picoseconds (ps) for ASAP7.

- `create_clock -period 1500` on the `clk` port: the target clock is 1.5 ns. The
  tools add or resize cells until every path between memory bits fits in this
  period, or report negative slack if not. Slack is the time left over.
- A second clock with no port (`vclk_core_clock`) is a virtual clock: it stands
  for the registers outside the core that drive and read the core's pins.
- `set_input_delay` and `set_output_delay` of 20% of the period (300 ps) say that
  signals reach the inputs 300 ps after the clock edge and the outputs must be
  stable 300 ps before the next one. This leaves 1,200 ps for logic from an input pin to
  a register, and the same from a register to an output pin.

To try a different clock, change `clk_period` in `constraint.sdc`. The
[final result](../../results/2026-11-10_final_batch3-random-s4-seed0_asap7_1500ps/README.md)
met 1.5 ns with room to spare and reported 682 ps as the fastest clock after
routing.
