# Constraints lab, track `steadiness`: keep the range offset steady across photon counts and background

## 1. Outcome

**Adopt with changes: as a hard limit, mainly at selection, value 1.0 bin. Do not adopt as a weighted penalty.**

- **The measure:** "steadiness" is the larger of two spreads (max minus min) of the range offset, in bins (1 bin = 0.1124 m):
  - across photon counts 16–256, read at fixed counts 23, 45, 91 and 181;
  - across extra ambient 0–0.6, read at fixed levels 0.1, 0.3 and 0.5.

  It uses a paired grid: the same pixels in every bucket (section 2).
- **The rule:** a circuit qualifies only if its steadiness on the full validation grid (5,505 pixels × 12 cells) is **≤ 1.0 bin**.
  - The check costs about 0.1 s per circuit.
  - It sits about 5 standard deviations of measurement noise above the steady designs (0.03–0.55) and well below the failure case (3.23).
- **Inside the search:** the same limit on fresh 2,048-pixel design-split grids is optional. It adds about 2% run time. It kept the search path steady, but it **did not reach smaller areas**: one win and one loss over two seeds (section 4).
- **The weighted penalty** (loss + 1.0 × steadiness, one seed) did worse than both: 25.49 µm². It also needs a weight tuned to the loss scale (section 4).
- **What it buys:** insurance, not area. Without any limit, every circuit the existing selection rule picked was already steady (≤ 0.55 bins). The unsteady 20 µm² circuit was never selected, because its error was also past the limit. The limit matters if the error tolerance is ever loosened, or if a future objective lets accuracy trade against something else.

## 2. How it is measured, and how repeatable it is

**Definition.** Offset is the median signed error (prediction minus label, in bins) over the pixels in a bucket. A constant offset cancels in the spread, so no offset fit is needed. Two ways to fill the buckets were compared:

- **Audit-style:** the audit's buckets (16–32 … 128–256 photons; background 0–0.2, 0.2–0.4, 0.4–0.6) on randomly drawn conditions. Each bucket holds different pixels, so pixel-to-pixel differences leak into the spread.
- **Paired grid (`constraints_lab/steadiness/steady.py`):**
  - Each pixel gets one photon stream of 181 draws. Signal draws, noise arrivals and replacement draws are shared across the three ambient levels, so a photon replaced at 0.1 is also replaced at 0.3.
  - Each stream is read out after 23, 45, 91 and 181 photons (geometric centres of the audit's photon buckets) at ambient 0.1, 0.3 and 0.5 (centres of the background buckets).
  - One bit-packed simulation per ambient level yields all four counts. The checkpoint simulator matched the reference integer simulator with 0 mismatches.
  - Per pixel this costs 3 × 181 = 543 photon steps, about the same as one circuit on the search batch (256 steps per pixel). So 2,048 grid pixels cost about as much as the 4,096-pixel search batch.

**Repeatability.** Same circuit, different photon draws: 12 draws on design splits, 4 on validation (`runs/2026-11-11_constraints-lab/steadiness/measure/measure.json`).

Photon-count spread, mean ± sd in bins (range for the noisiest row):

| Method, pixels | Final design | Area-optimized 24.68 µm² | Search end 20 µm² |
|---|---|---|---|
| Audit-style, design split, 4,096 (search size) | 0.58 ± 0.15 (0.28–0.81) | 0.37 ± 0.14 | 3.37 ± 0.10 |
| Audit-style, design split, 16,384 | 0.56 ± 0.07 | 0.35 ± 0.05 | 3.37 ± 0.04 |
| Audit-style, validation 3 sets (16,515) | 0.53 ± 0.07 | 0.35 ± 0.04 | 3.33 ± 0.06 |
| Grid, design split, 1,024 | 0.58 ± 0.07 | 0.33 ± 0.07 | 3.32 ± 0.07 |
| **Grid, design split, 2,048 (used in search)** | **0.56 ± 0.03** | **0.30 ± 0.04** | **3.35 ± 0.07** |
| Grid, design split, 4,096 | 0.55 ± 0.04 | 0.31 ± 0.04 | 3.33 ± 0.03 |
| **Grid, validation all 5,505 (used at selection)** | **0.54 ± 0.01** | **0.30 ± 0.01** | **3.25 ± 0.01** |

Background spread:

| Method | Final design | Area-optimized | Search end |
|---|---|---|---|
| Audit-style, 4,096 | 0.19 ± 0.10 | 0.24 ± 0.10 | 0.39 ± 0.10 |
| Grid, 2,048 | 0.09 ± 0.03 | 0.23 ± 0.02 | 0.38 ± 0.03 |
| Grid, validation | 0.05 ± 0.01 | 0.32 ± 0.02 | 0.43 ± 0.02 |

What this shows:

- **At the search's own size, the audit-style spread is too noisy for a tight limit.** One circuit ranged 0.28–0.81 across draws. It still separates 0.5 from 3.3, but a borderline mutant would pass or fail by luck.
- **The grid at 2,048 pixels is 3–5× tighter at the same cost.** Comparing two circuits on the same grid is tighter still: sd 0.05–0.09 for the difference, against 0.21–0.26 audit-style.
- **On all validation pixels the grid is repeatable to ±0.01–0.02.**
- **Design splits and validation differ by up to about 0.1 bin** (for example the 24.68 µm² design's background spread is 0.23 on design splits and 0.32 on validation). That is one more reason to apply the final check on validation.
- **Photon spread is the part that fails.** The 20 µm² circuit fails on photon count (3.2), not background (0.4).

## 3. Results table

Standard numbers: `Validator(..., seed=1234).audit` on conditions (16, 256, 0.6), 3 photon sets.

| Circuit | Area µm² / cells / flip-flops | MAE / median m | Within 3 bins | Offset by photon bucket 16-32…128-256 | Offset by background bucket | Audit spread, photon / background | Grid spread, photon / background | **Steadiness** | Time shift | Netlist mismatches |
|---|---|---|---|---|---|---|---|---|---|---|
| Final design (start) | 26.83 / 295 / 18 | 0.363 / 0.151 | 76.2% | +0.0 +0.4 +0.6 +0.6 | +0.4 +0.4 +0.5 | 0.55 / 0.12 | 0.55 / 0.07 | **0.55** | 100% | 0 |
| Area-optimized, existing (`final-design-tol5`) | 24.68 / 253 / 17 | 0.364 / 0.162 | 76.9% | +0.6 +0.5 +0.3 +0.3 | +0.6 +0.4 +0.3 | 0.33 / 0.36 | 0.31 / 0.34 | **0.34** | 100% | 0 |
| Search end without recheck | 20.02 / 207 / 16 | 0.399 / 0.174 | 72.1% | +2.0 +0.7 −0.3 −1.3 | +0.1 +0.2 +0.5 | 3.30 / 0.45 | 3.23 / 0.41 | **3.23** | 100% | 0 |
| Limit 1.0, seed 0, selected (`limit1.0-g300-seed0`) | **22.83 / 238 / 16** | 0.382 / 0.182 | 73.6% | +0.4 +0.6 +0.6 +0.6 | +0.5 +0.5 +0.7 | 0.17 / 0.26 | 0.05 / 0.32 | **0.32** | 100% | 0 |
| Limit 1.0, seed 1, selected (start kept) | 26.83 / 295 / 18 | 0.363 / 0.151 | 76.2% | as start | as start | 0.55 / 0.12 | 0.55 / 0.07 | **0.55** | 100% | 0 |
| Limit 1.0, seed 1, search end (not selectable) | 24.84 / 256 / 17 | **0.500** / 0.179 | 72.3% | +0.5 +0.5 +0.6 +0.6 | +0.3 +0.5 +0.9 | 0.12 / 0.53 | 0.16 / 0.49 | **0.49** | 100% | 0 |
| No limit, seed 1, selected (`off-g300-seed1`) | **23.37 / 255 / 16** | 0.380 / 0.180 | 74.4% | +0.5 +0.5 +0.5 +0.5 | +0.5 +0.4 +0.5 | 0.06 / 0.10 | 0.02 / 0.03 | **0.03** | 100% | 0 |
| Penalty 1.0, seed 0, selected | 25.49 / 261 / 18 | 0.374 / 0.175 | 74.8% | +0.6 +0.4 +0.4 +0.5 | +0.6 +0.5 +0.3 | 0.11 / 0.29 | 0.13 / 0.27 | **0.27** | 100% | 0 |
| Penalty 1.0, seed 0, search end | 24.95 / 254 / 18 | 0.382 / 0.180 | 73.6% | +0.3 +0.6 +0.7 +0.7 | +0.2 +0.5 +1.0 | 0.40 / 0.78 | 0.33 / 0.81 | **0.81** | 100% | 0 |

Notes on the table:

- Area, cells and flip-flops are real Yosys + ASAP7 synthesis (predictive). "Netlist mismatches" is `verify` netlist parity.
- **Steadiness** is max(grid photon spread, grid background spread) on all 5,505 validation pixels, seed 1234.
- Selection inside the runs used the trainer's seed-7 validation photons. On those draws the limit seed-0 circuit's MAE was 0.378 m, inside the 5% limit (0.386). On the fresh seed-1234 draws above it is 0.382 against a start of 0.363 (+5.2%). That difference is within the protocol's ~0.02 m noise.

## 4. What it costs and what it buys

**Setup.**

- `constraints_lab/steadiness/search.py` is a copy of the area-objective loop in `train_stream.py`. Mutation, scoring, area model, Yosys confirmation and the fresh-pixel recheck are the same.
- The run settings match the existing run (population 192, 4,096 search pixels, 5% tolerance, physics-check weight 4) except for 300 generations instead of 500, 1 thread and 1 synthesis worker.
- 300 generations covers the original run's whole course: its selection settled at 24.68 µm² by generation 120, and its search had drifted to 20.4 µm² by generation 300.
- Modes:
  - `off`: the original loop.
  - `limit`: the 16 smallest-estimated mutants that pass the loss check are scored on a fresh 2,048-pixel design-split grid. Those above the limit are dropped. The winner must also pass the limit on a second fresh grid, and selection needs validation steadiness ≤ 1.0.
  - `penalty`: loss + w × steadiness is compared against the start's score within the 5% tolerance, with a 10% loss pre-filter so better steadiness can buy back some loss. Selection is the original rule.

**Area and error against the existing 24.68 µm² result.**

| Run | Selected area | Validation MAE (fresh) | Steadiness | Search end |
|---|---|---|---|---|
| Existing, no limit, seed 0 (500 generations; `train_stream`) | 24.68 | 0.364 | 0.34 | 20.4 µm², MAE past tolerance |
| Limit 1.0, seed 0 | **22.83 (−7.5%)** | 0.382 | 0.32 | 22.83, within tolerance and steady |
| Limit 1.0, seed 1 | 26.83 (no change) | 0.363 | 0.55 | 24.84, MAE 0.50: never within tolerance |
| No limit, seed 1 (`off` mode) | 23.37 (−5.3%) | 0.380 | 0.03 | 23.37, within tolerance |
| Penalty w = 1.0, seed 0 | 25.49 (+3.3%) | 0.374 | 0.27 | 24.95, MAE past tolerance |

**Reading it.**

- **No consistent area benefit.**
  - Seed 0: the limit beat the existing result by 1.85 µm².
  - Seed 1: the limit run found nothing usable, while the same seed with no limit reached 23.37 µm².
  - The seed-1 limit run's search broke validation accuracy within 40 generations (MAE 0.401 m at generation 20, 0.537 at generation 60) and never recovered. That happened on its accuracy, not its steadiness, which stayed ≤ 0.55 throughout.
  - Which path a run takes decides the result far more than the limit does.
  - The smaller area at seed 0 came with a cost: within-3-bins fell from 76.9% to 73.6%, against 74.4% for the seed-1 no-limit circuit.
- **What the limit does do:** it keeps the search path itself steady.
  - The seed-0 limit run ended at 22.83 µm² inside tolerance.
  - The original run's path drifted to 20.4 µm² outside tolerance, and the no-recheck run's path to the unsteady 20.0 µm² circuit.
  - It rejected 29 (seed 0) and 60 (seed 1) shortlisted mutants per 300 generations.
  - At selection the limit never bound: every validation checkpoint of every run was ≤ 0.84.
- **Run-time cost is small.** Seed 1: 1,066 s with the limit against 1,043 s without (+2%). Seed 0 took 1,588 s on a busier machine.
- **The penalty did worse, and is harder to set.**
  - The search loss is about 34–41 (Huber in bins, on design splits). So weight 1.0 makes 1 bin of spread cost about 3% of the loss, under the 5% budget. A weight has to be retuned whenever the loss changes.
  - In this run the loosened pre-filter let accuracy slide first. By generation 20 the search circuit's validation MAE was 0.386 m, and the path stalled at 24.95 µm² with background spread 0.81, while 256 mutants were rejected.
  - Without the loosening, the penalty would only ever tighten the loss check, which a hard limit does more simply.
  - A hard limit has one interpretable value and no interaction with the loss scale. **The hard limit is the better form.**

## 5. What failed or is uncertain, and how to reproduce

- **Two seeds, 300 generations each, one seed for the penalty.**
  - The area differences between runs (22.8–26.8 µm²) depend on the path and are larger than any effect of the limit.
  - The `off` mode copy was run only at seed 1. It was not rerun at seed 0 to confirm it reproduces the existing 24.68 µm² run; the existing run is the seed-0 "without" reference.
- **The design splits are a poor proxy for validation. This is outside this track, but it dominates every area result here.**
  - On 16,384 clean design-split pixels the start circuit has MAE 1.17 m (train) and 1.25 m (architecture), against 0.363 m on validation. Its Huber loss is 37–40.
  - The seed-1 limit run's last circuit is **better** on train (MAE 1.04 m, loss 32.3) and level on architecture, but **38% worse on validation**: 0.500 m overall, 0.421 against 0.283 m on clean validation pixels, so non-clean pixels don't explain it.
  - The 5% loss tolerance on design splits therefore does not carry over to validation. Searches can wander far off, and only the validation selection catches it.
  - Files: `runs/2026-11-11_constraints-lab/steadiness/diag.log`, `diag_design.log`.
- **The grid's fixed counts are bucket centres, not the bucket mix.** Its spread runs slightly smaller than audit-style (0.05 against 0.17 for the limit seed-0 circuit), and it ranks circuits the same way as the audit.
- **Timeline.**
  - Day 1 (2026-11-11): measurement study (26 s), the seed-0 limit and penalty runs, and a first seed-1 limit run that was killed at the user's request.
  - Day 2: the seed-1 limit run was rerun from scratch. It reproduced day 1's partial path exactly (deterministic for a given seed). Then the seed-1 no-limit control, scoring and diagnostics.
  - All jobs went through `constraints_lab.slot`, one at a time, one thread, `--synth-workers 1`. Waits were short (40 s and 131 s once each). About 2 h 10 min of compute in total, including the killed run.
- **Data.** The test, fresh_test and scene_test splits were never loaded. Validation was used only for selection and reporting.

**Code** (`constraints_lab/steadiness/`):

| File | Purpose |
|---|---|
| `steady.py` | Grid measure and checkpoint simulator |
| `measure.py` | Repeatability study |
| `search.py` | Area loop with `--steady-mode off/limit/penalty` |
| `score.py` | Standard numbers, synthesis, parity |
| `diag.py`, `diag_design.py` | Validation clean/non-clean split; design-split MAE |

**Runs** (`runs/2026-11-11_constraints-lab/steadiness/`): `measure/`, `limit1.0-g300-seed0/`, `limit1.0-g300-seed1/`, `off-g300-seed1/`, `penalty1.0-g300-seed0/`, and `score.json` (holds all table numbers).

**Reproduce the main run** (from `SPAD/`):
```
../.venv/bin/python -m constraints_lab.slot -- ../.venv/bin/python -m constraints_lab.steadiness.search \
  --init-circuit runs/2026-11-10_kaggle-t4_batch3_fused-larger-search/random-s4-seed0/circuit.json \
  --out runs/2026-11-11_constraints-lab/steadiness/limit1.0-g300-seed0 \
  --steady-mode limit --steady-limit 1.0 --generations 300 --seed 0 --threads 1 --synth-workers 1
```
Other runs:
- Seed-1 control: `--steady-mode off --seed 1`.
- Penalty: `--steady-mode penalty --steady-weight 1.0`.

Measurement and scoring:
- `../.venv/bin/python -m constraints_lab.slot -- ../.venv/bin/python -m constraints_lab.steadiness.measure --repeats 12 --threads 1`
- `../.venv/bin/python -m constraints_lab.slot -- ../.venv/bin/python -m constraints_lab.steadiness.score --verify name=path/circuit.json ...`
