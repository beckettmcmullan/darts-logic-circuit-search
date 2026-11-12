# Area objective from the final design (2026-11-11, local CPU)

Full write-up: `runs/2026-11-11_local-cpu_area-objective/README.md`.
`train_stream.py --objective area` keeps the smallest circuit within 5% of the start's error,
with every accepted change confirmed by real Yosys + ASAP7 synthesis. From the final design:
**24.68 µm² (-8.0%, 253 cells vs 295)** at the same accuracy (0.364 m mean, 76.9% within 3 bins)
and still steady across photon counts (+0.3 to +0.6 steps). A 20.0 µm² circuit (-25%) exists at
10% worse error, but its offset drifts from +2.0 to -1.3 steps with photon count.

# Kaggle batch 3 (2026-11-10): fused step, compiled search, larger search

Full write-up: `runs/2026-11-10_kaggle-t4_batch3_fused-larger-search/README.md`.
All 8 jobs worked; about 30 min per job on the T4 (batch 2: about 80), with a ~10x larger
search. Best: random-s4-seed0 (police) 0.363 m mean, 0.151 m median, 76.2% within 3 bins;
rule-s0-seed0 has the best median (0.143 m). Photon-count bias is nearly flat in every circuit.
The best single circuits do not beat batch 2's (0.351 m mean, 0.131 m median). In both
police/no-police pairs, the police run has the better median and within-3-bins.

# Police + randomized-conditions batch on Kaggle T4 x2 (2026-11-08)

Same jobs as the local batch below, larger search: batch 1024, population 128, 1024 search
rays, 600 generations. Same randomized validation scoring. 1.59 s per gradient pass on the
T4 (flat from 256 to 8192 rays), about 80 min per job.

| Run | MAE | Median | Within 3 bins | Police flags | Shift test | Bias 16-32 -> 128-256 photons | Area |
|---|---|---|---|---|---|---|---|
| random-s4-seed0-nopolice | **0.385** | 0.139 | 76.5% | 5.5% | 100% | +1.1 -> -0.7 bins | 25.6 (274 cells) |
| random-s4-seed1 (police) | 0.584 | **0.130** | **77.8%** | **2.3%** | 100% | **+0.2 -> +0.3** | 23.4 (246 cells) |
| random-s4-seed0 (police) | 0.566 | 0.152 | 75.0% | 6.0% | 100% | +1.7 -> -1.0 | |
| rule-s4-seed0-nopolice | 0.704 | 0.204 | 68.2% | 10.1% | 100% | +0.3 -> +0.8 | |
| random-s2-seed0 (police) | 2.168 | 1.043 | 24.1% | 76.1% | 20% | broken | |

The three rule-started police jobs crashed in the gradient phase: a NaN soft output became a
gather index in police.distances. CPU turns NaN into index 0, CUDA aborts. Fixed
(nan_to_num before indexing).

Findings:
- The larger search finds clearly better circuits than the local batch (best MAE 0.385 vs
  0.568 m), with more gates in use (16-18 of 48 instead of 3).
- random-s4-seed1 learned a different algorithm: it steps toward photons 5-16 bins away on
  either side, holds within 4 bins, and ignores anything farther than 16. A centred tracker
  with a dead zone, which explains its nearly flat bias across photon counts.
- Correction to the local batch's conclusion: the police did not uniformly break
  random-start training. Locally all three police random runs failed; on Kaggle two of three
  succeeded, including the flattest-bias circuit. One seed per setting cannot settle whether
  the police helps.
- All synthesized circuits match their netlists exactly.

# Police + randomized-conditions batch (2026-11-08, M5 CPU)

All scored on capture 6 with random photon counts (16-256) and extra ambient (0-0.6),
3 photon sets, same seed. Old circuits were trained at a fixed 64 photons.

| Run | MAE | Median | Within 3 bins | Police flags | Time-shift test | Area |
|---|---|---|---|---|---|---|
| rule-s4-seed0 (police) | 0.568 | 0.157 | 74.0% | 7.4% | 100% | 20.2 |
| rule-s4-seed0-nopolice | 0.568 | 0.157 | 74.0% | 7.4% | 100% | 20.2 |
| rule-s0-nopolice | 0.754 | 0.178 | 73.8% | 5.2% | 100% | |
| random-s4-seed0-nopolice | 0.765 | 0.182 | 72.2% | 8.4% | 99.9% | 22.8 |
| rule-s4-seed1 (police) | 0.831 | 0.152 | 74.9% | 6.1% | 100% | |
| rule-s0-seed0 (police) | 0.848 | 0.153 | 74.7% | 6.3% | 99.9% | |
| random-s2/s4 (police, 3 runs) | 1.84-2.13 | 0.83-0.99 | 25-30% | 64-76% | 16-21% | |
| old Kaggle rule-s4-seed0 | 0.559 | 0.171 | 71.0% | 11.2% | 99.8% | 20.7 |
| hand rule | 2.251 | 0.189 | 70.0% | 9.7% | 100% | 23.6 |

Findings:
- The police did not help. From the rule start it changed nothing (the police and no-police
  rule-s4 circuits compute the same function). From random starts all three police runs
  failed: they fail the time-shift test, so their answers do not move with the photons,
  and one hit 87 non-finite steps. The no-police random run reached 0.765 m.
  Likely cause: the gradient hinge (up to 50 bins per term) dwarfs the Huber range loss.
- The gradient phase does not learn under 256-photon randomized streams (soft MAE about
  7 m throughout); every gain came from the hard search.
- The best new circuit ties the old one on mean error and is better on median and
  within-3-bins, but still drifts with photon count (+1.8 bins at 16-32 photons,
  -1.0 at 128-256).
- All synthesized circuits match their netlists exactly (0 mismatches).

# Photon-stream core: design-stage results

Everything in this section uses captures 1-6 only, on the Mac. Captures 7-10 have not
been scored, so none of this is a held-out result. CUDA has not been run yet.

Labels changed first. Released intrinsics were misaligned, so `spad/dataset/calibration.py` refined
six lens numbers on captures 1-4. Median peak-to-label error on unused captures fell
from 0.269 to 0.090 m (capture 5) and 0.252 to 0.124 m (capture 6). The SPAD peak is
the alignment reference, so this self-calibrates the sensors and slightly favors
peak-like methods. Pilot numbers below used the old labels and are not comparable.

Results on validation capture 6. Area is Yosys + ASAP7 Liberty, in Liberty units.
MAE is the mean absolute range error over all labelled rays.

| Method | Photons | MAE (m) | Median (m) | Within 3 bins | Area | Histogram memory |
|---|---:|---:|---:|---:|---:|---|
| Peak, full histogram | all | 0.267 | 0.110 | 79.7% | 22.0 (reader only) | 8,064 bits/pixel, not costed |
| 8-bin box filter, full histogram | all | 0.235 | 0.084 | 81.1% | not synthesized | 8,064 bits/pixel, not costed |
| Small CNN, full histogram | all | 0.252 | 0.085 | 79.5% | software | 8,064 bits/pixel, not costed |
| Small CNN | 64 | 0.243 | 0.090 | 80.6% | software | histogram of 64 photons |
| Hand rule | 64 | 0.300 | 0.167 | 75.2% | 23.6 | none |
| **Learned, no state bits (`rule-s0-seed0`)** | 64 | **0.233** | **0.091** | **80.9%** | **20.3** | none |
| Learned, best of sweep (`rule-s4-seed1`) | 64 | 0.232 | 0.089 | 81.0% | 21.2 | none |

Learned rows use fresh photon samples, but capture 6 also selected their checkpoints,
so they are mildly optimistic. All eight synthesized circuits match the Python
simulator on 4,000 rays with zero mismatches. Area excludes wires, clocking, place and
route, and the TDC that produces timestamps. Energy was not measured.

Search behavior:
- The gradient phase degrades after hardening at every learning rate tested for 1500 steps.
  Rollback to the best state fixes this: five of five rule-started runs reached 0.236 m,
  against 0.299 m without it.
- From random gates the gradient phase alone reached only 0.61-0.85 m. With hard
  search, two of four random starts matched the rule-started runs and two stopped near 0.30-0.32 m.
- Learned state bits added almost nothing. The datapath's confidence counter holds the
  useful memory. This core is recurrent through its datapath, not through learned state.

The best circuit removes upward steps, so the candidate tracks the pulse's leading
edge, plus a -3 bin off-chip offset. That offset was fitted at 64 photons and will not
transfer to other budgets. Labels also use the nearest Livox return, so this may be a
label shortcut as well as a useful estimator. The shortcut audit must test it.

Photons are replayed from histograms, so pile-up is retained and dead time is absent.
No result here shows behavior on a real photon stream.

# Initial histogram pilot (old labels): execution verified, accuracy improvement unproven

Data occupies **880,839,738 bytes** under `SPAD/data/`, including raw downloads,
48,000 prepared rays, calibration and extracted ASAP7 libraries. Captures 1-5
are training data, 6 is architecture validation, and 7-8 are held out.

A CPU pilot ran 200 bilevel optimization steps with batches of eight rays,
two 24-gate layers, 16 recurrent state bits, 12 count bits and eight score bits.
It took about 100 seconds through the final validation pass on this execution
host. This is not a measured M1/M5 benchmark. Checkpoint 175 was selected by
hard validation MAE on a fixed 128-ray validation subset: 0.5324 m, versus
0.5454 m for peak detection on that same validation subset.

After checkpoint selection, the frozen model was evaluated on **all 12,000
prepared held-out rays**. The authoritative output is
`archive/runs/2026-11-05_histogram-pilot/full-evaluation/metrics.json`.

| Metric | Hard Boolean model | Raw peak detection |
|---|---:|---:|
| Mean absolute range error | 0.9505 m | 0.8956 m |
| RMSE | 2.0473 m | 1.7857 m |
| Median absolute range error | 0.3622 m | 0.3626 m |
| Recall within 1 bin | 17.80% | 14.09% |
| Recall within 3 bins | 46.89% | 46.82% |
| Recall within 5 bins | 63.88% | 64.00% |

The model does **not** improve mean absolute error over peak detection. This
is an initial pipeline check, not a converged result. The selected circuit is
still mostly pass-through functions (45 of 48 candidate gates); three have
become OR functions. Its recurrent search space has not established a useful
memory-based estimator. Maximum scores tie for 38.99% of the held-out rays;
inference consistently chooses the earliest tied bin. No prepared counts saturate
the default 12-bit input. Test results did not drive another training search.

The learned-core cost proxy is 4.9280 native Liberty area units and 807.34 ps.
Those figures include 16 state DFFs and all candidate gate functions. They omit
fixed surrounding circuitry, wires, fanout, clock/reset implementation and
physical design; they are not synthesized PPA or a realizable clock specification.

`archive/runs/2026-11-05_histogram-pilot/best.pt` and `archive/runs/2026-11-05_histogram-pilot/last.pt` contain the pilot checkpoints.
`archive/runs/2026-11-05_histogram-pilot/full-evaluation/circuit.json` is the independently verified Boolean
export. `archive/runs/2026-11-05_histogram-pilot/capture7-range.npz` contains a 192 x 256 range map with 6,000
predicted pixels; unselected pixels are NaN. `archive/runs/2026-11-05_pilot-smoke-test/` and
`archive/runs/2026-11-05_pilot-resume-check/` are pipeline diagnostics, not research results.

All six correctness tests pass. Integration checks cover real-data preprocessing,
Liberty extraction, training, checkpoint recovery, full held-out evaluation,
integer-export equivalence and range-map inference.

Calibration remains an explicit assumption: `p2` intrinsics and released YAML
distortion are used because the depth-track sensor identity is unconfirmed.
The timing correction follows the reference converter's 17-bin shift and
per-pixel offsets. These are custom projected-ray metrics, not the official
point-cloud benchmark protocol, and no motion-recovery claim follows from them.

The next research step is to confirm calibration and then assess longer searches
and reduced-photon inputs against fixed baselines using training/validation data.
Reserve a fresh held-out experiment for choosing among future design changes.
