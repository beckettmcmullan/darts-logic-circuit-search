# 2026-11-10 · Final design: batch 3 random-s4-seed0 on ASAP7, 1.5 ns clock

The circuit chosen as the final design, taken from Verilog to a routed GDSII layout with
OpenROAD-flow-scripts (Docker image `openroad/orfs:latest`), run by `asic/run_flow.sh`.

Circuit: `runs/2026-11-10_kaggle-t4_batch3_fused-larger-search/random-s4-seed0`.
Chosen because it combines near-best accuracy with the steadiest behaviour across photon
counts. On identical validation photons (random 16-256 photons, extra ambient 0-0.6):
0.363 m mean error, 0.151 m median, 76.2% within 34 cm, and an average offset between
0.0 and +0.6 time steps from 16 to 256 photons. The 2026-11-08 Kaggle circuit
random-s4-seed0-nopolice scores slightly better (0.351 m mean, 0.141 m median) but its offset
drifts from +1.2 to -0.6 steps with photon count.

What it learned (measured on real photons, once locked on): a photon 5-16 steps after the
guess always moves it one step later; photons near the guess or earlier usually leave it
alone and occasionally move it one step earlier, depending on its 4 memory bits; photons
more than 16 steps earlier are ignored. 26 of its 48 gates do real work.

## Results

| | |
|---|---|
| Timing | Met at 1.5 ns: setup slack +609 ps, hold slack +42 ps |
| Fastest clock (post-route) | 682 ps period, about 1.47 GHz |
| Clock skew | 2.6 ps |
| Die | 110 µm² (about 10.5 x 10.5 µm) |
| Standard-cell area | 44.1 µm², 451 cells, 49% utilization |
| Wire length | 916 µm |
| Design-rule violations after routing | 0 |
| Power | 71 µW at 667 MHz, vectorless (assumed activity, not real photon streams) |

Compared with the first layout (2026-11-08 random-s4-seed1, same flow): about 6% more die
area (110 vs 104 µm²) and a faster clock (682 vs 738 ps).

## Caveats

- ASAP7 is a predictive teaching library and cannot be fabricated. The project is
  exploratory; these are realistic estimates, not a tapeout.
- ORFS uses the fast-fast library corner by default; a typical or slow corner would be slower.
- Power assumes continuous switching at 667 MHz; real photon rates are far lower. A
  gate-level simulation with real photon streams is needed for a meaningful figure.
- The routed netlist (`6_final.v`) has not yet been simulated against the Python model.
- Accuracy numbers are on validation data; the held-out test has not been run.

## Files

`6_final.gds` (layout), `6_final.def` (placed and routed design, with net names),
`6_final.v` (routed netlist), `6_final.sdc`, `6_finish.rpt` (timing, power, area),
`5_route_drc.rpt` (empty: no DRC errors), `summary.json`, `final_*.webp` (layout, routing,
placement, worst path, clock tree, congestion), and the inputs `photon_core.v`,
`constraint.sdc`, `config.mk`.
