# Settle track: photons needed to settle

## 1. Outcome

**Do not adopt settling as a search constraint. Adopt it as a reported measure, plus a cheap check at selection time.**

- **Hard limit inside the area objective:** not worth it. The limit was settle loss no worse than 5% above the start.
  - It cost 1.7 µm²: 25.60 µm² with the limit against 23.90 µm² without it (same seed, same budget).
  - It bought no faster settling: the run without the limit settles as fast or slightly faster.
- **Weighted term inside the accuracy objective:** not shown to help. Settle weight 1 = settle loss counted equally with the standard loss.
  - Both seeds found circuits that settle faster: 70% within 3 bins after 16 photons instead of 24, and +5.5 to +6.3 points within 3 bins at 16 photons.
  - The area was 1.0 to 1.3 µm² smaller and the standard error unchanged.
  - But one of the two control runs without the term found the same gain. Two seeds cannot separate the term's effect from search luck.
- **What to adopt:**
  - Report the error-versus-photons curve for every circuit: within 3 bins and MAE after 16, 32 and 64 photons, using one offset.
  - Report the photon count at which a circuit reaches 70% within 3 bins (N70 below).
  - At selection only, reject a circuit whose within-3-bins at 16 photons is more than 3 points below the start's. The paired noise is about 1 point (sd). This check would have rejected the 20 µm² "search end without recheck" circuit, which is 17.8 points down at 16 photons, and none of the good circuits.
- **Photons the final design needs:**
  - About 24 photons to reach 70% within 3 bins.
  - About 32 photons to get MAE under 0.45 m.
  - 48 to 64 photons to come within 10% of its 256-photon accuracy.
  - Nothing is gained past 64: MAE is 0.286 m at 64 and 0.280 m at 256; within 3 bins is 78.1% against 78.9%.
  - So a fixed exposure of about 64 photons per pixel would give the full accuracy at a quarter of the 256-photon budget.

## 2. How settling is measured, and how repeatable it is

- **Pixels and photons:** the validation pixels (5,505 per photon set, 3 sets = 16,515). Each pixel gets a full 256-photon stream, with no random cut in photon count, and its own extra ambient level drawn uniformly from 0 to 0.6.
- **Readout after N photons:** the candidate register after the first N photons of the stream. That is exactly what an N-photon exposure would give.
  - `trace_stream` reads all N values in one pass. It matches `simulate_stream` on every prefix N, checked in `check_trace.py`.
  - `trace_population_packed` is the bit-packed population version. It matches too.
  - N runs over a fine grid: 4, 6, 8, 10, 12, 16, 20, 24, 28, 32, 40, 48, 56, 64, 80, 96, 112, 128, 160, 192, 224, 256.
- **Offset: one offset for all readouts.** It is the standard train-fitted offset, `Validator.offset`. Reasons:
  - A chip has one calibration constant.
  - Under a timed exposure a pixel's photon count depends on reflectivity and range, so it is not known at readout.
  - Per-count offsets hide drift. The 20 µm² circuit's best per-count offset moves from +0.3 bins at 8 photons to −6.3 bins at 256, a 6.6-bin drift. With per-count offsets its 64-photon readout looks fine.
  - For well-behaved circuits it makes no difference: MAE at 32 photons is 0.407 m with per-count offsets against 0.405 m with one offset for the final design.
  - Per-count offsets are computed as a side output, fitted on 8,000 train pixels.
- **Settle points:**
  - N70 = the smallest N reaching 70% within 3 bins.
  - Also the smallest N with MAE within 10% of the 256-photon MAE.
  - Any point defined relative to the circuit's own final error favours circuits with a bad final answer. The 20 µm² circuit "settles" by that rule at 40 photons only because its 256-photon answer is bad. Use absolute thresholds.
- **Repeatability:** same pixels, 5 independent single-set photon draws.

| Measure | sd between draws (final design) | Verdict |
|---|---|---|
| MAE at 16 / 32 / 64 photons | 0.057 / 0.023 / 0.013 m (about 6% / 6% / 4%) | Noisy: gross errors dominate (median error at 16 photons is 0.22 m, MAE is 0.98 m) |
| Median error at 16 / 32 photons | 0.005 / 0.003 m | Repeatable |
| Within 3 bins at 16 / 32 photons | 0.9 / 0.6 points | Repeatable |
| N70 | 20 or 24 for the final design; identical in all 5 draws for most circuits | Repeatable to one grid step |
| N for MAE within 10% of final | 48 to 80 | Not repeatable: the curve is flat at the end. Do not use |
| Paired comparison (two circuits, same photon draws) | sd of the difference: 0.004 to 0.03 m for MAE at 32 photons, 0.5 to 1.4 points for within 3 bins at 16 photons | Use paired comparisons |

- **In the search:**
  - The settle term is the Huber loss (delta 4 bins, the same loss as the standard term) on the readouts after 16, 32 and 64 photons. Streams are full 64-photon streams on 2,048 pixels of the same design split.
  - It uses the member's own offset from the standard batch, so there is one offset per circuit, as on the chip.
  - Validation selection uses the mean MAE after 16, 32 and 64 photons, on 3 sets of full 64-photon streams.
- **The standard score already measures settling in part.** Its photon count is log-uniform over 16 to 256, so 25% of pixels get 16 to 32 photons. The final design's standard MAE (0.363 m) is roughly the average of its curve over that range.

## 3. Results

**Notes on the table:**
- Standard numbers: `Validator(seed=1234).audit` on conditions (16, 256, 0.6) with 3 photon sets, plus real Yosys + ASAP7 area.
- The offset column is the median signed error in bins for photon counts 16-32, 32-64, 64-128 and 128-256.
- The curve columns are readouts after 16 / 32 / 64 / 256 photons, all with one offset.
- N70 is followed by its value in each of the 5 repeat draws.
- The time-shift test is 100% and netlist parity (`verify`) shows 0 mismatches for every circuit.
- `area_settle-limit` and `area_tol5` give identical answers on every measured pixel. The same seed made the same early edit, so `area_settle-limit` is the same behaviour at 0.9 µm² more area.
- `acc_control_s0` found nothing better on validation and kept the start circuit.

| Circuit | Area µm² / cells / flip-flops | MAE / median (m) | Within 3 bins | Offset by photon count | MAE after 16/32/64/256 photons (m) | Within 3 bins after 16/32/64/256 (%) | N70 (draws) |
|---|---|---|---|---|---|---|---|
| final (start) | 26.83 / 295 / 18 | 0.363 / 0.151 | 76.2% | +0.0, +0.4, +0.6, +0.6 | 0.983 / 0.405 / 0.286 / 0.280 | 66.1 / 75.2 / 78.1 / 78.9 | 24 (24,20,24,20,24) |
| area_tol5 | 24.68 / 253 / 17 | 0.364 / 0.162 | 76.9% | +0.6, +0.5, +0.3, +0.3 | 0.981 / 0.400 / 0.291 / 0.290 | 68.8 / 76.5 / 78.3 / 77.9 | 20 (all 20) |
| search end, 20 µm² | 20.02 / 207 / 16 | 0.399 / 0.174 | 72.1% | +2.0, +0.7, −0.3, −1.3 | 1.129 / 0.437 / 0.261 / 0.386 | 48.4 / 71.3 / 79.3 / 63.2 | 32 (all 32) |
| rule_circuit (floor) | 23.61 / 260 / 14 | 2.251 / 0.189 | 70.0% | +0.5, +0.4, +0.4, +0.4 | 3.172 / 2.495 / 1.979 / 1.845 | 66.1 / 69.4 / 71.6 / 71.9 | 48 (48,40,32,56,40) |
| **area_settle-limit** (area objective, settle hard limit 5%) | 25.60 / 269 / 18 | 0.364 / 0.162 | 76.9% | +0.6, +0.5, +0.3, +0.3 | 0.990 / 0.400 / 0.291 / 0.290 | 68.8 / 76.5 / 78.3 / 77.9 | 20 (all 20) |
| **area_control** (same run, no settle limit) | **23.90 / 250 / 16** | 0.364 / 0.152 | 77.2% | +0.1, +0.4, +0.4, +0.4 | 0.961 / 0.400 / 0.290 / 0.287 | 69.8 / 76.6 / 78.3 / 78.4 | 20 (20,16,16,16,20) |
| acc_settle-w1_s0 (accuracy objective + settle weight 1, seed 0) | 25.88 / 261 / 18 | 0.371 / 0.135 | 78.7% | +0.4, +0.3, +0.2, +0.2 | 0.916 / 0.413 / 0.289 / 0.271 | 72.1 / 78.5 / 79.8 / 80.0 | 16 (all 16) |
| acc_settle-w1_s1 (same, seed 1) | 25.54 / 263 / 17 | 0.359 / 0.139 | 78.2% | +0.5, +0.4, +0.3, +0.3 | 0.923 / 0.406 / 0.280 / 0.272 | 71.2 / 78.1 / 79.8 / 79.8 | 16 (all 16) |
| acc_control_s0 (accuracy objective, no settle term, seed 0) | 26.83 / 295 / 18 | 0.363 / 0.151 | 76.2% | (start kept) | 0.983 / 0.405 / 0.286 / 0.280 | 66.1 / 75.2 / 78.1 / 78.9 | 24 |
| acc_control_s1 (same, seed 1) | 26.16 / 275 / 17 | 0.365 / 0.135 | 78.8% | +0.4, +0.3, +0.2, +0.2 | 1.062 / 0.392 / 0.271 / 0.270 | 72.2 / 78.5 / 80.0 / 80.0 | 16 (all 16) |

**Error-versus-photons curves** (one offset; MAE m / median m / within 3 bins):

| Photons | final | area_tol5 | search end, 20 µm² | rule |
|---|---|---|---|---|
| 8 | 2.752 / 0.315 / 53.0% | 2.780 / 0.286 / 55.2% | 3.011 / 0.554 / 28.4% | 4.590 / 0.253 / 60.2% |
| 16 | 0.983 / 0.223 / 66.1% | 0.981 / 0.198 / 68.8% | 1.129 / 0.350 / 48.4% | 3.172 / 0.210 / 66.1% |
| 24 | 0.561 / 0.181 / 72.3% | 0.554 / 0.172 / 74.5% | 0.638 / 0.248 / 62.7% | 2.813 / 0.196 / 68.6% |
| 32 | 0.405 / 0.160 / 75.2% | 0.400 / 0.163 / 76.5% | 0.437 / 0.185 / 71.3% | 2.495 / 0.195 / 69.4% |
| 48 | 0.304 / 0.146 / 77.5% | 0.305 / 0.157 / 77.7% | 0.288 / 0.127 / 77.8% | 2.138 / 0.189 / 70.5% |
| 64 | 0.286 / 0.138 / 78.1% | 0.291 / 0.152 / 78.3% | 0.261 / 0.108 / 79.3% | 1.979 / 0.186 / 71.6% |
| 128 | 0.287 / 0.136 / 78.3% | 0.294 / 0.159 / 77.8% | 0.285 / 0.143 / 77.8% | 1.890 / 0.186 / 71.7% |
| 256 | 0.280 / 0.135 / 78.9% | 0.290 / 0.157 / 77.9% | 0.386 / 0.259 / 63.2% | 1.845 / 0.182 / 71.9% |

What the curves show:
- **Rule:** locks on early (60% within 3 bins at 8 photons, better than any learned circuit) but never corrects gross errors: MAE stays 1.8 to 3 m.
- **20 µm² circuit:** good at 48 to 96 photons, then gets worse. Its answer drifts by about 6 bins between 64 and 256 photons. "Settling" for this circuit is really a steadiness failure.
- **Final design and area_tol5:** flat from 64 photons on.

## 4. Cost and benefit

**Area objective, hard limit** (settle loss no worse than 5% above the start, on the search sample and on the fresh-pixel recheck):
- Cost: area 25.60 µm², against 23.90 µm² for the identical run without the limit (−4.6% against −10.9% from the start).
- Benefit: none. The control is as good or better at 16, 32 and 64 photons. Within 3 bins at 16 photons is 69.8% for the control against 68.8% with the limit, with a paired sd of about 0.6 points.
- Why: the settle loss on 2,048 search pixels is noisy, and the limit blocks area edits that do not actually hurt settling on validation.
- Side result: the 300-generation area control (23.90 µm², 16 flip-flops, MAE 0.364 m, offsets +0.1 to +0.4, parity 0) is smaller than the earlier `final-design-tol5` (24.68 µm²) at the same accuracy. One seed.

**Accuracy objective, weighted term** (weight 1, area capped at the start's estimate, selection on validation MAE + 1 × settle MAE among circuits no larger than the start):
- Both seeds gained, against the final design on the same photon draws:
  - Within 3 bins at 16 photons: +6.3 and +5.5 points (sd 0.6).
  - Within 3 bins at 32 photons: +3.4 and +3.2 points.
  - N70: 24 → 16.
  - MAE at 256 photons: −0.009 and −0.011 m.
  - Area: 25.88 and 25.54 µm² against 26.83.
  - Standard MAE: 0.371 and 0.359 m against 0.363, which is noise.
- MAE at 32 photons did not change (+0.001 and +0.009 m, sd about 0.02 to 0.03).
- Most of the gain comes with a flatter bias: per-count offsets of +1.6 → +1.1 bins against +1.6 → +2.6 for the final design, and a lower median error (0.135 against 0.151 m). It looks like a steadiness improvement as much as a settling one.
- **The seed-1 control without the settle term reached the same gains:** +6.2 points at 16 photons, N70 16, 26.16 µm². The seed-0 control found nothing. With 2 seeds, the term's effect cannot be told apart from search luck.

## 5. What failed or is uncertain, and how to reproduce

**What failed:**
- The plain accuracy-objective hard search (copied from `train_stream.py`) drifts worse from a converged start: validation MAE reached 0.445 m by generation 40. Taking the best of 96 mutants on one 4,096-pixel sample favours lucky mutants. The partial log is `accuracy_settle-w1_no-recheck.log`.
- I added a recheck: the winner must also score better on fresh pixels from both design splits. With it the search still wanders (0.37 to 0.45 m on validation), so the selection on validation does most of the work.
- Search loss and validation disagree: the Huber loss on clean train pixels is about 35 bins, against a validation MAE of about 3 bins. The two splits are weighted toward different pixels. I did not investigate this.

**What is uncertain:**
- Each configuration ran once per seed: the area runs 1 seed each, the accuracy runs 2 seeds each.
- The area runs used 300 generations and 2 synthesized candidates per generation, not 500 and 3. That kept the runs to about 20 minutes with 1 thread and 1 synthesis worker.
- Selection and reporting both use the validation pixels (the photon draws differ), so selected circuits are slightly optimistic.
- One run waited 430 s for a CPU slot and another 10 s. No other starvation.
- Run times: area_settle-limit 20.2 min, area_control 15.9 min, accuracy runs 5.4 to 6.5 min each.
- The settle streams replay real histograms, with no dead time or pile-up change at short exposure. That is the same limitation as the standard conditions.

**Code** (all in `constraints_lab/settle/`):
- `settle.py`: tracing simulators and curve metrics.
- `measure.py`: curves, repeatability, standard audit, synthesis and parity.
- `search.py`: copy of the hard-search loop with the settle terms, `--settle-limit`, `--settle-weight`, `--area-cap` and `--recheck`.
- `run_all.sh`: all the search runs.
- `check_trace.py`: checks the tracing simulators against the shared ones.

**Outputs** are in `runs/2026-11-11_constraints-lab/settle/`. `scores/settle_scores.json` holds every number above.

**Main run** (area objective with the settle hard limit):
```
../.venv/bin/python -m constraints_lab.slot -- ../.venv/bin/python -m constraints_lab.settle.search --out runs/2026-11-11_constraints-lab/settle/area_settle-limit --init-circuit runs/2026-11-10_kaggle-t4_batch3_fused-larger-search/random-s4-seed0/circuit.json --threads 1 --synth-workers 1 --compile-search default --population 192 --search-rays 4096 --seed 0 --objective area --settle-limit --settle-tolerance 0.05 --generations 300 --synth-candidates 2
```
- The control is the same command without `--settle-limit`.
- The accuracy runs use `--objective accuracy --settle-weight 1 --area-cap --recheck --generations 200`; the controls use `--settle-weight 0`.

**Measurement:**
```
../.venv/bin/python -m constraints_lab.slot -- ../.venv/bin/python -m constraints_lab.settle.measure --out runs/2026-11-11_constraints-lab/settle/scores name=path/circuit.json ... rule=rule
```
