# Tail track: bad-case error

## 1. Outcome

**Adopt with changes. Measure the tail as the share of pixels off by more than 1 m (`over_1m`), and use it as a hard limit at selection, not as a strict search-time limit.**
- **Where it applies:** the validation pick must have `over_1m` no higher than the start circuit's plus 0.2 points (about 2 paired standard deviations).
- **In the search itself:** add no tail limit, or one with slack of about 0.25 points. With slack 0 (one seed), the limit cost area: the pick was 25.34 µm², against 24.68 µm² for the control without the limit. The pick's tail was no better (2.64% against 2.67%).
- **Report alongside:** p90, p95, p99 and the share off by more than 3 m (`over_3m`).
- **Do not adopt:** a capped loss as the search objective, or the 95th or 99th percentile as a limit.

Key findings:
- **The tail is mostly not the circuit's fault.**
  - 55% of the final design's misses over 1 m are on pixels whose label is flagged not clean.
  - 47% are also missed by an 8-bin box-filtered histogram peak that sees the same photons all at once.
  - If every miss that box peak gets right were fixed, `over_1m` would fall from 3.1% to 1.4%. That is about the reachable floor with these photons.
  - Five pixels with labels beyond 20 m (15 rays, all not clean) carry 39% of the squared error. Removing them alone drops RMSE from 2.12 m to 1.66 m and MAE by 0.037 m.
- **`over_1m` is repeatable, and the area search already moves it.**
  - Across photon draws on validation it is 3.10% ± 0.10%. Paired differences between circuits vary by ±0.04 to 0.15 points.
  - The 24.7 µm² area-optimized design has the lowest tail of the three references (2.7%). The 20 µm² search end has the highest (3.4%).
  - The 99th percentile rests on about 165 rays and moves ±0.06 m between draws. At search size it is meaningless.
- **The search's pixels are not like validation.**
  - The design splits have about 10% of labels beyond 20 m and 4-6% of rays off by more than 3 m (validation: 0.5%). Most of those the box peak misses too.
  - These rays dominate the Huber loss, which grows linearly with the size of a miss. So the search partly optimizes where it lands when it is hopelessly wrong.
  - `over_1m` counts each such ray once, and they cancel in paired comparisons.
- **The capped loss cuts the tail but needs the MAE limit.** As the accuracy objective at fixed area, Huber capped at 1 m gave at the pick:
  - `over_1m` 3.06% → 2.48%, p95 0.849 → 0.809 m.
  - Area −6.5%, MAE +4%.
  - Because the loss ignores how far a lost ray lands, the remaining gross misses drift: `over_3m` went from 0.50% to 0.60-0.81%, and MAE reached +46% mid-run. Only the MAE limit at selection held it back.
- **The slack-0 tail limit stops area cuts from growing the tail, but it mostly stops the area cuts.**
  - Its search ended at 25.09 µm² with `over_1m` 2.94%. The control's search end was 20.43 µm² at 3.43%.
  - The control's MAE-based selection already rejected that 20.43 µm² circuit, so the tail limit never decided the pick in this data.

## 2. How the tail is measured, and how repeatable it is

Error is the circuit's answer minus the label, after the standard score's constant offset (a median fitted on 8,000 train rays), in metres. One bin is 0.1124 m.

The measures are:
- the 90th, 95th and 99th percentiles of |error|;
- the share with |error| > 1 m (8.9 bins);
- the share with |error| > 3 m.

Validation uses `Validator(seed=1234)` on conditions (16, 256, 0.6) with 3 photon sets. Validation has 5,505 labelled pixels, so 3 sets give **16,515 rays**. That is not the 33,030 implied by the protocol's "11,010 per set". The protocol's number looks wrong.

**Full validation, 8 photon draws (seeds 1234-1241), mean ± SD:**

| | MAE | median | p90 | p95 | p99 | > 1 m | > 3 m |
|---|---|---|---|---|---|---|---|
| Final design | 0.378 ± 0.015 | 0.149 ± 0.002 | 0.650 ± 0.004 | 0.853 ± 0.008 | 1.39 ± 0.06 | 3.10% ± 0.10 | 0.49% ± 0.04 |
| Area-optimized (tol5) | 0.379 ± 0.014 | 0.160 ± 0.001 | 0.633 ± 0.003 | 0.829 ± 0.005 | 1.36 ± 0.04 | 2.72% ± 0.10 | 0.49% ± 0.04 |
| Search end (20 µm²) | 0.405 ± 0.015 | 0.172 ± 0.001 | 0.673 ± 0.005 | 0.897 ± 0.009 | 1.48 ± 0.03 | 3.64% ± 0.18 | 0.50% ± 0.05 |
| Paired, tol5 − final | +0.002 ± 0.002 | +0.011 ± 0.001 | −0.017 ± 0.005 | −0.023 ± 0.007 | −0.04 ± 0.03 | −0.38 ± 0.04 pt | 0.00 ± 0.01 pt |
| Paired, search end − final | +0.028 ± 0.004 | +0.023 ± 0.002 | +0.023 ± 0.003 | +0.045 ± 0.007 | +0.09 ± 0.04 | +0.54 ± 0.15 pt | +0.01 ± 0.01 pt |

The MAE's spread between draws (0.015 m) comes from the 15 far-label rays. Paired comparisons are 5-10 times tighter. `over_1m` and p90 separate the circuits clearly; p99 does not.

**Search-sized batches: 4,096 rays, offset by each circuit's batch median as `population_losses` does, 30 batches per split:**

| Split | Final design: MAE / p90 / p95 / p99 / > 1 m / > 3 m | Paired tol5 − final, > 1 m | Paired search end − final, > 1 m; p90 | Huber(4): paired SD / mean |
|---|---|---|---|---|
| train | 1.09 m / 0.58 / 1.32 ± 0.27 / 26.3 / 5.9% ± 0.4 / 4.1% | +0.08 ± 0.14 pt | +0.54 ± 0.24 pt; +0.10 ± 0.02 m | 0.42 / 34.5 (1.2%) |
| architecture | 1.26 m / 0.78 / 8.2 ± 2.7 / 22.8 / 9.2% ± 0.4 / 6.1% | −0.05 ± 0.10 pt | +0.57 ± 0.18 pt; +0.19 ± 0.05 m | 0.46 / 40.5 (1.1%) |

- **`over_1m` at 4,096 rays:** the paired SD is 0.10-0.24 points. A real regression of 0.55 points shows up at 2-3 SD in one batch. A slack-0 limit therefore also rejects about half of the neutral mutants by chance, which slows area cuts. That matches what the search run showed.
- **p95 and p99 at search size:** they fall inside the gross-miss population. On the architecture split p95 is 8 ± 2.7 m and bimodal. They are unusable there. p90 is usable (paired SD 0.014-0.05 m).
- **Design splits versus validation** (`design_tail.py`):
  - Train and architecture have 10% of labels beyond 20 m; validation has 0.1%.
  - 3.9-6.3% of their rays are off by more than 3 m; validation has 0.6%.
  - 53-76% of those rays have labels beyond 20 m, and 70-75% are missed by the box peak too.
  - Below 20 m, train looks like validation: MAE 0.34 m, `over_1m` 3.0%.

## 3. Where the large misses come from (validation, seed 1234, 16,515 rays)

| | MAE | median | p90 | p95 | p99 | RMSE | > 1 m | > 3 m |
|---|---|---|---|---|---|---|---|---|
| Final design | 0.363 | 0.151 | 0.652 | 0.849 | 1.353 | 2.118 | 3.06% | 0.50% |
| Area-optimized (tol5) | 0.364 | 0.162 | 0.632 | 0.834 | 1.352 | 2.129 | 2.67% | 0.50% |
| Search end, 20 µm² | 0.399 | 0.174 | 0.675 | 0.900 | 1.477 | 2.308 | 3.42% | 0.50% |
| Histogram peak, same photons | 0.354 | 0.184 | 0.684 | 0.897 | 1.461 | 1.580 | 3.5% | 0.5% |
| 8-bin box peak, same photons | 0.264 | 0.119 | 0.603 | 0.770 | 1.194 | 1.400 | 2.1% | 0.2% |
| Final design, clean labels only | 0.283 | 0.130 | 0.502 | 0.710 | 1.205 | 1.644 | 1.8% | 0.4% |
| Box peak, clean labels only | 0.181 | 0.100 | 0.441 | 0.619 | 0.951 | 0.456 | 0.9% | 0.2% |

The circuit's tail is already as good as a plain histogram peak's on the same photons. The 8-bin box peak, a matched filter that sees all photons at once, is the useful reference.

**Share off by more than 1 m, by bucket.** Final design first, box peak in brackets. The last column is that bucket's share of all misses over 1 m.

| Bucket | Share of rays | > 1 m | Share of big misses |
|---|---|---|---|
| 16-32 photons | 24% | 4.1% (2.2%) | 32% |
| 32-64 | 26% | 3.0% (2.3%) | 25% |
| 64-128 | 25% | 2.5% (1.9%) | 20% |
| 128-256 | 25% | 2.7% (2.1%) | 22% |
| extra ambient 0-0.2 | 33% | 2.4% (2.1%) | 26% |
| 0.2-0.4 | 33% | 2.6% (1.8%) | 28% |
| 0.4-0.6 | 34% | 4.2% (2.5%) | 46% |
| expected signal photons < 4 | 3.5% | 42% (37%) | 48% |
| 4-8 | 7.0% | 10.6% (5.7%) | 24% |
| 8-16 | 21% | 2.3% (1.3%) | 16% |
| 16-32 | 25% | 1.2% (0.6%) | 9% |
| ≥ 32 | 44% | 0.2% (0.0%) | 3% |
| label clean | 77% | 1.8% (0.9%) | 45% |
| label not clean | 23% | 7.5% (6.4%) | 55% |
| full-capture peak within 1 m of label | 97% | 1.5% (0.6%) | 47% |
| full-capture peak > 1 m from label | 3% | 52% (51%) | 53% |

"Expected signal photons" is photon count × (1 − extra ambient) × the pixel's signal share at the label in its full capture histogram. It is the best single explanation of the tail: 72% of big misses fall on the 10% of rays with fewer than 8 expected signal photons. Photon count alone and ambient alone each roughly double the miss rate from best to worst bucket. Range within the validation scene does not matter: 2.9% at 0-10 m, 3.1% at 10-20 m.

**Causes of the final design's misses over 1 m** (exclusive, first match wins):

| Cause | Share of misses |
|---|---|
| Label not clean | 55% |
| Label clean, but the full capture's strongest return is elsewhere (a second surface or a label problem) | 15% |
| Answer sits on a significant second return in the full capture (> 5 SD excess within ±2 bins) | 23% |
| Answer sits on background | 7% |

80% of the misses are late (after the label) and 20% early.

**How much a perfect circuit could remove.** Replace only the misses over 1 m that the box peak on the same photons gets right:

| Measure | Now | If those misses were fixed |
|---|---|---|
| > 1 m | 3.1% | 1.4% |
| p95 | 0.85 m | 0.79 m |
| p99 | 1.35 m | 1.16 m |
| > 3 m | 0.5% | 0.2% |
| RMSE | 2.12 m | 1.46 m |

p90 and the median barely move (0.62 m and 0.15 m). About half the tail is reachable in principle. The rest is unclean or far labels and pixels with too little signal.

## 4. Adding the tail to the search: what it costs and what it buys

`constraints_lab/tail/search.py` copies the hard search from `train_stream.py`. It keeps the same `mutate`, the fresh-pixel recheck on both design splits and the Yosys confirmation, with no gradient phase. It adds these options:
- **`--loss huber|capped|huber+share`:** the search loss.
- **`--tail-limit` with `--tail-slack`:** a mutant's `over_1m` must be no worse than the start circuit's on the same pixels, both in the population and on the recheck pixels.
- **`--tail-slack-validation`:** the validation pick must also have `over_1m` ≤ start + slack.
- **`--objective accuracy`:** minimize the chosen loss at fixed area. The estimated area must not exceed the start's estimate, and real area must not exceed 26.83 µm². A change must beat the current circuit on fresh pixels of both splits. The pick is the lowest validation `over_1m` with MAE within 5%.

**All circuits.** Standard numbers from `Validator` seed 1234 with 3 photon sets, plus the tail:

| Circuit | Area µm² / cells / flip-flops | MAE | median | within 3 bins | offset by photons, 16-32 … 128-256 (bins) | time shift | p90 | p95 | p99 | > 1 m | > 3 m | parity |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| Final design (start) | 26.83 / 295 / 18 | 0.363 | 0.151 | 76.2% | 0.0, 0.4, 0.6, 0.6 | 100% | 0.652 | 0.849 | 1.353 | 3.06% | 0.50% | 0 |
| Area-optimized tol5 (control, no tail limit) | 24.68 / 253 / 17 | 0.364 | 0.162 | 76.9% | 0.6, 0.5, 0.3, 0.3 | 100% | 0.632 | 0.834 | 1.352 | 2.67% | 0.50% | 0 |
| tol5 control, search end (not picked) | 20.43 / 207 / 16 | 0.399 | 0.174 | 72.1% | 2.0, 0.7, −0.3, −1.3 | – | 0.674 | 0.900 | 1.477 | 3.43% | 0.52% | – |
| Search end without recheck | 20.02 / 207 / 16 | 0.399 | 0.174 | 72.1% | 2.0, 0.7, −0.3, −1.3 | 100% | 0.675 | 0.900 | 1.477 | 3.42% | 0.50% | 0 |
| **accuracy-capped9** (fixed area, capped loss), pick at generation 40 | 25.09 / 278 / 16 | 0.379 | 0.148 | 77.8% | 0.5, 0.3, 0.2, 0.3 | 100% | 0.629 | 0.809 | 1.351 | 2.48% | 0.60% | 0 |
| accuracy-capped9, search end at generation 300 (not picked) | 26.19 | 0.424 | 0.129 | – | – | – | 0.618 | 0.805 | 1.666 | 2.54% | 0.81% | – |
| **area-tol5-taillimit** (Huber within 5%, slack-0 tail limit), pick at generation 460 | 25.34 / 263 / 18 | 0.358 | 0.162 | 76.8% | 0.7, 0.4, 0.3, 0.3 | 99.95% | 0.631 | 0.827 | 1.336 | 2.64% | 0.47% | 0 |
| area-tol5-taillimit, search end at generation 500 (not picked) | 25.09 | 0.385 | 0.196 | – | – | – | 0.649 | 0.861 | 1.353 | 2.94% | 0.48% | – |

**Accuracy objective: can the tail be reduced at fixed area?** Yes, modestly. On the selection photons:
- `over_1m` fell from 3.00% to 2.49% by generation 20 and to 2.34% at generation 280.
- The median fell from 0.152 m to 0.129 m.

The capped loss does not care how far a lost ray lands, so gross misses wandered. Validation MAE reached 0.53 m at generation 80 and ended at 0.41 m. `over_3m` rose from 0.50% to 0.81%. The 5% MAE limit therefore picked generation 40.

Net at the pick, against the start:

| Measure | Change |
|---|---|
| `over_1m` | −0.6 points (−19%) |
| p90 | −0.02 m |
| p95 | −0.04 m |
| p99 | unchanged |
| MAE | +0.016 m (+4%) |
| median | −0.003 m |
| area | −1.7 µm² (−6.5%), 16 flip-flops |
| offsets | steady |

That is only slightly better than the 2.67% the area-optimized design reached without trying. One seed.

**Area objective: does the limit stop area cuts from growing the tail?** Partly, and at a price.

| | Tail-limited run | Control (no tail limit) |
|---|---|---|
| Search end | 25.09 µm², `over_1m` 2.94% | 20.43 µm², `over_1m` 3.43% (+0.37 points over the start; MAE +10%) |
| Pick | 25.34 µm² (−5.5%), `over_1m` 2.64% | 24.68 µm² (−8.0%), `over_1m` 2.67% |

- **Area cost:** about 0.7 µm² more area at the pick, for no better tail and the same MAE (0.358 against 0.364, which is within noise).
- **Why the cuts slowed:** at generation 100 the tail-limited run was at 25.57 µm², while the control had reached 24.73 µm² by generation 40. A 4,096-ray, slack-0 `over_1m` limit rejects neutral mutants by chance about half the time.
- **Why the limit bought nothing at the pick:** the control's MAE-based selection had already refused the tail-grown 20.43 µm² circuit.
- **Caveat:** the two runs use different random trajectories, and there is one seed each.

## 5. What failed or is uncertain

- **One seed per run.** No second seed was run.
  - The capped-loss trajectory was not monotone (`over_1m` went 2.5% → 3.1% → 2.3%), so its pick is partly luck.
  - The area difference between the tail-limited run and the control may be partly trajectory.
- **The capped loss alone is unsafe** (MAE was +46% at one point). Any change of loss shape must keep a linear term or an MAE limit. A `huber+share` weighted variant is implemented (`--loss huber+share --tail-weight 100`) but was not run.
- **Slack choice.** A slack-0 search-time limit is noise-limited at 4,096 rays. If a search-time limit is wanted, use slack ≈ 0.0025, about 2 paired SD. This has not been tested.
- **Cause attribution is a proxy.** It relies on the full capture histogram, and a wrong label on a pixel flagged clean shows up as "strongest return elsewhere".
- **Validation scope.** Validation is one near scene (4-13 m), so its tail numbers do not speak for far ranges, which dominate the search's design splits.
- **CPU.** Every job ran through `constraints_lab.slot` with one thread; slot waits were 5-10 s per job. A generation took about 2.6 s for the accuracy run and about 5.3 s for the area run (which runs Yosys). Total time was about 2 h 10 min.

**Reproduce (from `SPAD/`):**

```
../.venv/bin/python -m constraints_lab.slot -- ../.venv/bin/python -m constraints_lab.tail.analyse
../.venv/bin/python -m constraints_lab.slot -- ../.venv/bin/python -m constraints_lab.tail.repeat
../.venv/bin/python -m constraints_lab.slot -- ../.venv/bin/python -m constraints_lab.tail.design_tail
../.venv/bin/python -m constraints_lab.slot -- ../.venv/bin/python -m constraints_lab.tail.search \
    --out runs/2026-11-11_constraints-lab/tail/area-tol5-taillimit \
    --init-circuit runs/2026-11-10_kaggle-t4_batch3_fused-larger-search/random-s4-seed0/circuit.json \
    --objective area --loss huber --tail-limit --tail-slack 0 --tail-slack-validation 0 \
    --generations 500 --threads 1
../.venv/bin/python -m constraints_lab.slot -- ../.venv/bin/python -m constraints_lab.tail.search \
    --out runs/2026-11-11_constraints-lab/tail/accuracy-capped9 \
    --init-circuit runs/2026-11-10_kaggle-t4_batch3_fused-larger-search/random-s4-seed0/circuit.json \
    --objective accuracy --loss capped --cap-bins 9 --generations 300 --threads 1
../.venv/bin/python -m constraints_lab.slot -- ../.venv/bin/python -m constraints_lab.tail.score \
    runs/2026-11-11_local-cpu_area-objective/final-design-tol5/state.pt
```
