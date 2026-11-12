# 2026-11-10 · First full layout: random-s4-seed1 on ASAP7, 1.5 ns clock

One photon-stream core taken from Verilog to a routed GDSII layout with
OpenROAD-flow-scripts (Docker image `openroad/orfs:latest`), run by `asic/run_flow.sh`.
Circuit: `runs/2026-11-08_kaggle-t4_physics-police_random-conditions/random-s4-seed1`
(the centred tracker; best median error so far). The whole flow took 44 s.

## Results

| | |
|---|---|
| Timing | Met at 1.5 ns: setup slack +552 ps, hold slack +43 ps |
| Fastest clock (post-route) | 738 ps period, about 1.35 GHz |
| Clock skew | 2.6 ps |
| Die | 104 µm² (about 10.2 x 10.2 µm) |
| Standard-cell area | 41.3 µm², 423 cells (incl. 66 tap cells and timing buffers), 51% utilization |
| Wire length | 842 µm |
| Design-rule violations after routing | 0 |
| Power | 59 µW at 667 MHz, vectorless (assumed activity, not real photon streams) |

## How this compares with the earlier estimates

| | Earlier estimate (Yosys + ASAP7, `spad/hardware`) | This layout |
|---|---|---|
| Cell area | 23.4 (246 cells) | 41.3 µm² (423 cells) |
| Critical path | 1,013 ps (typical corner, no wires) | 738 ps (fast corner, routed) |

- Area is about 1.8x the earlier figure: ORFS forbids the smallest ASAP7 cells, adds tap
  cells, and inserts buffers to meet timing. The earlier area numbers are useful for
  comparing circuits, not as real silicon area.
- Timing looks faster mainly because ORFS uses the fast-fast library corner by default;
  the earlier estimate used typical. A typical- or slow-corner run is needed for a
  conservative number.

## Caveats

- ASAP7 is a predictive teaching library and cannot be fabricated.
- Power uses assumed switching activity at a full 667 MHz. Real photons arrive at MHz rates,
  so real power is far lower; a gate-level simulation of real photon streams (VCD) is
  needed for a meaningful figure.
- The routed netlist (`6_final.v`) has not yet been simulated against the Python model.

## Files

`6_final.gds` (layout), `6_final.v` (routed netlist), `6_final.sdc`, `6_finish.rpt`
(timing, power, area), `5_route_drc.rpt` (empty: no DRC errors), `summary.json`,
`final_*.webp` (layout, routing, placement, worst path, clock tree, congestion images),
and the inputs: `photon_core.v`, `constraint.sdc`, `config.mk`.
