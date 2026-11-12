# Sensor track: behaviour under timing jitter, pile-up / dead time, and wire bit errors

## 1. Outcome

**Adopt with changes: as checks when choosing the final circuit, not as training data.**

- **Don't train on perturbed streams.** I tried mixing perturbed streams into the mutant score in two ways: a mixed batch with one shared offset, and the same with a hard limit on clean accuracy. Neither gave robustness beyond what an ordinary clean search gives. Both made clean accuracy worse:
  - Every accuracy-objective circuit trained on the mix lost clean MAE (+0.04 to +0.19 m on the standard draws, 2 seeds). The clean control search improved it (-0.012 m).
  - In the area objective, the mixed run reached the same area as the existing clean-searched circuit (24.61 vs 24.68 µm²). It was 5 points worse on within-3-bins and barely more pile-up robust.
- **Do add two hard limits when choosing the final circuit.** They are cheap and repeat to about 0.1 bin. Apply them to circuits that already pass the accuracy tolerance:
  1. **Pile-up walk: |offset shift at pile-up k = 4| ≤ 3 bins**, with the clean (factory) calibration.
     - Final design: -3.8 (fails). area_tol5: -2.8 (passes). Clean control search: -2.1. Histogram peak: -1.8.
  2. **Jitter tolerance: within-3-bins at σ = 2 bins extra jitter, after recalibration, may drop at most 3 points from clean.**
     - Final design: -1.9. area_tol5: -2.4. The 20 µm² search-end circuit: -6.7 (fails). The new 21.2 µm² area-search end: -6.5 (fails).
     - This check probably overlaps with the steadiness track. The circuits that fail it are the ones whose offset drifts with photon count.
- **No bit-error constraint.** A 1% per-photon flip on the worst arrival wire (bit 5) adds about 0.02 m MAE. Within-3-bins doesn't move. All learned circuits respond alike.

All of this rests on **models** of sensor effects applied to the replayed photons, not on measurements from a second sensor. The results say how the circuits respond to an effect of a given form. They do not say how strong that effect is on a real device.

**Answer to "which effect hurts most":**
- **Pile-up hurts most.** With factory calibration at k = 4, the final design falls from 76.2% to 38.8% within 3 bins.
  - Almost all of that is a constant offset: refitting the offset gives 77.7%. The offset is the same across photon counts (spread ≤ 0.3 bin) and across range thirds (spread ≤ 0.8 bin).
  - The part calibration can't fix appears when pile-up differs per pixel, as it does in a real scene. With every pixel on its own k in 1-4 ("mixpileup"), the final design reaches 62.9% factory and 71.5% recalibrated, against 76.2% clean.
  - The learned circuits are about twice as pile-up-sensitive in offset as a histogram peak: -3.8 vs -1.8 bins at k = 4. On a real sensor this would show up as brightness-dependent range walk.
- **Jitter causes real accuracy loss that recalibration doesn't recover**, but only at 2 bins and above (≥ 1.5 ns rms), well beyond a realistic SPAD plus TDC. At ≤ 1 bin it costs ≤ 0.5 points of within-3-bins and ≤ 0.01 m MAE.

## 2. How it is measured, and how repeatable it is

### Perturbation models (`constraints_lab/sensor/perturb.py`)

How the perturbations are applied:
- The replay draws arrivals independently from each pixel's measured histogram, in random order. It then replaces a random share b (0-0.6) by uniform ambient.
- Whatever pile-up and jitter the capture had is already in the histogram.
- Each model below is applied on top of the standard replayed photons, after the ambient replacement, so ambient photons are perturbed too.
- Labels are unchanged: the surface hasn't moved, only the sensor has changed.

| Model | What it does | Strengths | What it ignores |
|---|---|---|---|
| Timing jitter | Each arrival moves by round(N(0, σ²)) bins, clamped to 0-671 | σ = 0.5, 1, 2, 4 (8 as a stress test) | The one-sided late diffusion tail of real SPADs; jitter shared by all photons of a laser cycle (trigger jitter); sub-bin effects. The capture's own IRF is already in the histogram; this is extra |
| Pile-up / dead time within a cycle | First-photon detection: each detected arrival is the earliest of k independent replay draws (same pixel histogram, same ambient share). k = 1 is the replay itself | k = 2, 4, 8 (16 as a stress test). "mixpileup": every pixel draws its own k uniformly from 1-4 | A Poisson (not fixed) number of photons per cycle; empty cycles; dead time spanning several cycles (with independent cycles these only thin the stream); multi-event TDCs that also catch a later photon; afterpulsing; crosstalk; the link between k and ambient flux |
| Combined | Pile-up first (which photon is detected), then jitter (noise on its timestamp) | k = 2 + σ = 1; k = 4 + σ = 2. "mix": half the pixels get k uniform 1-4 and σ uniform 0-2 | As above |
| Arrival-wire bit error (fault check) | With probability p per photon, one wire of the 10-bit arrival bus flips (a random wire, or a fixed one: 0 = LSB, 5, 9 = MSB). Values up to 1023 reach the core unchanged; the 672-bin peak baseline drops them | p = 0.001, 0.01, 0.05 | Stuck-at faults, bursts, errors in the core's own registers |

Scale:
- One bin is 0.1124 m, or 750 ps round trip.
- Extra jitter of 0.5-1 bin (375-750 ps rms) is already pessimistic for a SPAD plus TDC. 2-4 bins is a stress test.
- k is photons arriving per laser cycle relative to the capture. k = 2-4 corresponds to a strongly lit, or bright and near, pixel.

### Scoring (`constraints_lab/sensor/evaluate.py`)

The clean photons are exactly the standard audit draws: `Validator(..., seed=1234)`, 16-256 photons, extra ambient 0-0.6, 3 sets of the 5,505 validation rays (16,515 rays). The clean row reproduces the reference audit exactly (final design 0.363 / 0.151 / 76.2%).

Each perturbation is applied to those same photons (paired), with its own fixed random generator. Each case is scored two ways:
- **Factory:** the constant offset is fitted on clean training photons. This is the full damage to a chip calibrated without the effect.
- **Recalibrated:** the offset is refitted on equally perturbed training photons. What remains is loss that a constant offset cannot remove.

Reported for each case: MAE, median, within 3 bins, the median signed error and its shift from clean, signed error by photon bucket and by target-range third, and the time-shift test. Circuits are simulated with the packed exact simulator; each circuit was checked against `simulate_stream` before scoring.

### Repeatability

Run `eval-references-repeat` re-scored the same circuits on independent photon draws and independent perturbation draws (seeds 99 / 150):
- **Offset shifts repeat within 0.1 bin.** Final design at k = 4: -3.8 both times. area_tol5: -2.8 both times.
- **Within-3-bins repeats within about 0.6 points; median error within 0.003 m.**
- **MAE does not repeat.** The same final design scores 0.363 m clean on the standard draws and 0.433 m on the second draws. A few rays hundreds of bins off dominate the mean, and how many there are depends on the draw.

So both proposed limits use the offset shift and within-3-bins, not MAE. The evaluation is fast: about 5 s per perturbation for six circuits and baselines.

## 3. Results

### 3a. Reference circuits and baselines under each perturbation

Run: `eval-references` (+ `eval-references-mix`). Shift is in bins, factory calibration. Within 3 bins is shown as factory / recalibrated.

| Circuit | Offset shift jit 1 / 2 / 4 | Offset shift k 2 / 4 / 8 | Within 3 clean | Within 3 jit 2 | Within 3 jit 4 | Within 3 k = 4 | Within 3 mixpileup | Within 3 k4 + jit2 | MAE change, bits 1% wire 5 |
|---|---|---|---|---|---|---|---|---|---|
| final design | +0.0 / +0.3 / +0.9 | -1.4 / -3.8 / -6.3 | 76.2 | 74.0 / 74.3 | 66.3 / 69.8 | 38.8 / 77.7 | 62.9 / 71.5 | 47.2 / 78.4 | +0.021 m |
| area_tol5 | +0.0 / +0.1 / +0.4 | -1.2 / -2.8 / -4.6 | 76.9 | 74.2 / 74.5 | 69.9 / 70.7 | 61.1 / 79.4 | 72.0 / 75.3 | 60.8 / 78.1 | +0.017 m |
| search end 20 µm² | -0.3 / -1.0 / -2.4 | -1.0 / -2.0 / -3.4 | 72.1 | 63.7 / 65.4 | 43.9 / 52.7 | 56.9 / 62.7 | 65.2 / 66.5 | 41.6 / 56.5 | +0.014 m |
| rule_circuit (w8) | +0.0 / +0.1 / +0.4 | -1.3 / -2.5 / -3.6 | 70.0 | 66.9 / 67.2 | 58.9 / 59.0 | 64.4 / 79.0 | 69.5 / 73.9 | 62.9 / 77.3 | +0.089 m |
| histogram peak | +0.2 / +0.4 / +0.5 | -0.9 / -1.8 / -2.6 | 71.6 | 67.0 / 68.4 | 58.0 / 59.0 | 78.3 / 79.3 | 76.7 / 75.4 | 73.4 / 76.8 | +0.001 m |
| box8 peak | -0.0 / -0.0 / +0.1 | -0.8 / -1.7 / -3.1 | 79.7 | 77.9 / 77.7 | 71.1 / 71.0 | 77.1 / 80.5 | 79.5 / 79.3 | 72.1 / 80.0 | +0.000 m |

Further points:
- **Jitter.** Recalibration buys back little: final design at σ = 4 is 66.3 → 69.8, against 76.2 clean. This is real loss.
  - At σ = 0.5-1 every learned circuit loses ≤ 0.6 points and ≤ 0.01 m MAE.
  - The 20 µm² circuit is fragile: at σ = 4 its offset differs across photon buckets by 6.9 bins (+1.5 ... -5.5).
- **Pile-up.** The factory-calibration loss is almost all offset.
  - Final design MAE at k = 2 / 4 / 8: 0.295 / 0.461 / 0.791 factory, and 0.275 / 0.285 / 0.368 recalibrated (0.363 clean).
  - Pile-up at k = 2 improves MAE for every method. In this model the earliest-of-k draw removes late ambient photons and so removes far outliers. Treat this as a feature of the model, not a promise about real pile-up.
  - At k = 16 even recalibration fails: final design 1.25 m, against 0.57 m for the histogram peak.
  - For the 20 µm² circuit, pile-up also makes the offset depend on photon count (+0.8 ... -2.8 bins at k = 2), so recalibration can't repair it.
- **Bit errors.** Flipping a random wire at 0.1% / 1% / 5% per photon changes the final design's MAE by +0.000 / +0.004 / +0.020 m. Within-3-bins is unchanged.
  - A fixed wire at 1%: wire 0 (LSB) +0.00 m, wire 5 +0.02 m, wire 9 (MSB) +0.006 m.
  - Mid-order flips (±32 bins) look like plausible near photons. MSB flips land far away and are rejected like ambient.
  - The hand rule is the most fragile. Its clean MAE of 2.25 m is already outlier-dominated.

### 3b. Search runs, standard numbers plus the sensor measures

Standard numbers come from `Validator(seed=1234).audit`, with Yosys + ASAP7 synthesis and `verify` netlist parity. Every circuit below has **0 parity mismatches** and a time-shift test of 100% (area_mix end: 99.9%). Sensor measures come from `eval-acc-s0`, `eval-area-s0` and `eval-acc-s1`, all with the same standard draws.

| Circuit | Area, cells, flip-flops | MAE / median (m) | Within 3 | Offset by photons (16-32 ... 128-256) | k = 4 shift | Within 3, mixpileup factory | Within 3, jit 2 recal (drop) | Within 3, jit 4 recal |
|---|---|---|---|---|---|---|---|---|
| final design (start) | 26.83 µm², 295, 18 | 0.363 / 0.151 | 76.2% | +0.0 +0.4 +0.6 +0.6 | -3.8 | 62.3 | 74.6 (-1.6) | 69.6 |
| area_tol5 (clean area search, reference) | 24.68 µm², 253, 17 | 0.364 / 0.162 | 76.9% | +0.6 +0.5 +0.3 +0.3 | -2.8 | 71.5 | 75.0 (-1.9) | 70.3 |
| `acc-clean-s0` (accuracy search, clean control, 300 generations) | 26.83 µm², 276, 17 | 0.351 / 0.134 | 77.5% | +0.9 +0.3 +0.0 +0.0 | -2.1 | 76.6 | 75.6 (-1.9) | 70.4 |
| `acc-mix-s0` selected (generation 40) | 25.70 µm², 264, 17 | 0.419 / 0.162 | 76.4% | +0.6 +0.3 +0.1 +0.1 | **-0.9** | **78.3** | 74.1 (-2.3) | 69.1 |
| `acc-mix-s0` search end (generation 300) | 26.49 µm², 287, 17 | 0.557 / 0.143 | 76.6% | +1.0 +0.2 +0.0 -0.0 | -2.3 | 75.5 | 74.2 (-2.4) | 68.6 |
| `acc-mix-cleanlimit-s1` search end (selected = start; no checkpoint passed the clean limit) | 25.40 µm², 273, 17 | 0.467 / 0.142 | 77.0% | +0.8 +0.2 +0.0 -0.0 | -2.2 | 75.9 | 75.1 (-1.9) | 70.2 |
| `area-mix-cleanlimit-s0` selected (area objective, 5% tolerance) | 24.61 µm², 257, 18 | 0.393 / 0.195 | 71.8% | +0.5 +0.5 +0.5 +0.5 | -2.5 | 69.5 | 70.4 (-1.4) | 66.4 |
| `area-mix-cleanlimit-s0` search end | 21.20 µm², 224, 17 | 0.392 / 0.165 | 73.1% | +1.8 +0.7 -0.3 -1.2 | -1.9* | 66.0 | 66.6 (-6.5) | 54.2 |
| histogram peak (baseline) | n/a | 0.354 / 0.184 | 71.6% | +0.3 +0.4 +0.5 +0.5 | -1.8 | 76.5 | 68.9 | 58.4 |

\* For the 21.2 µm² circuit the k = 4 shift depends on photon count (bucket spread 4.9 bins), so one number understates the damage.

Values in 3b for the reference circuits differ from 3a by up to 0.6 points. Each evaluation run seeds perturbations by variant position, so the perturbation draws differ.

### Second mixed-search seed: trajectory

`acc-mix-s1` has `--share .5`, seed 1, and no clean limit. It was stopped by the 2026-11-11 halt at generation 220 of 300. Checkpoints were scored in `eval-acc-mix-s1-trajectory`.

- **Pile-up shift wanders and returns to the start value.** The k = 4 shift goes -1.0 (generation 20), -1.7, -1.9, -1.6, -2.1, -1.9, -2.2, -2.4, -2.2, -2.2, then **-3.8** (generation 220, the start value).
- **The clean tail is worse at every checkpoint.** Clean MAE is 0.415-0.873 m on the standard draws, against 0.363 at the start.
- **The most pile-up-robust point is worse on everything else.** At generation 20 (-1.0 bins, mixpileup 75.0%), clean within-3-bins is 67.2% and jitter σ = 4 recalibrated is 55.7%.

So the seed-0 generation-40 circuit (-0.9 bins at 76.4% clean) was a lucky snapshot. It did not reproduce.

## 4. What the constraint costs and what it buys

**Training on perturbed streams (the form tested in part 3): it costs and doesn't reliably buy.**
- **Accuracy objective (300 generations, population 192, 4,096 rays):**
  - The clean control already cut the k = 4 shift from -3.8 to -2.1 bins and improved clean numbers (MAE 0.351, median 0.134, within-3 77.5%).
  - The mixed runs ended at -2.2 / -2.3. Their only better point (-0.9) did not reproduce on seed 1. Clean MAE was 0.42-0.56 m.
  - The extra error is in the tail: median and within-3 hold, so it is a few far-off rays.
  - Area is unchanged within ±1.4 µm²; this objective doesn't target area.
- **Area objective (200 generations, 5% tolerance):**
  - It reached 24.61 µm², the same as the clean-searched area_tol5 (24.68).
  - Clean accuracy was worse: within-3 71.8% vs 76.9%, median 0.195 vs 0.162 m.
  - Pile-up robustness barely changed: -2.5 vs -2.8 bins.
  - The one gain is a perfectly flat offset across photon counts (+0.5 in every bucket).
  - Its search end (21.2 µm²) shows the same failure as the earlier 20 µm² circuit: photon-count-dependent offset and jitter fragility.
- **Robust to one effect, worse on another?** For the seed-0 generation-40 circuit, no: jitter, bit errors and the time-shift test match the start. For the seed-1 generation-20 checkpoint, yes: pile-up improved while jitter σ = 4 got much worse (55.7% vs 69.6%).
- **Simulation cost:** the mixed batch adds about 10-20% per generation for the extra replay draws. The circuits are simulated only once, since clean and perturbed rays share one batch.

**The proposed selection checks (adopt):**
- **Cost:** two extra validation simulations per candidate, about 1 s each with the packed simulator. No training change.
- **Buys:**
  - The pile-up limit rejects circuits whose range would walk with brightness by more than about 0.34 m at k = 4. It rejects the current final design (-3.8 bins) and accepts area_tol5 and the clean-control circuit.
  - The jitter limit rejects the over-shrunk circuits (the 20 and 21.2 µm² ones).
- **Values:** 3 bins for pile-up and 3 points for jitter. They sit about 1 bin and 1 point above what area_tol5 and the clean control achieve, and the measures repeat within 0.1 bin and 0.6 points.

## 5. What failed or is uncertain, and how to reproduce

**What failed or is uncertain:**
- **Seeds.** One seed for the area run and the clean control. Two seeds for the mixed accuracy search, one of them stopped at generation 220/300. The negative training result is consistent across the 4 accuracy runs, but each run is still one seed.
- **Greedy acceptance drift.** The accuracy search drifts with or without perturbations. Validation MAE on its own selection draws wandered between 0.37 and 0.62 m.
- **The clean hard limit selected nothing.** In the seed-1 clean-limit run no checkpoint passed the limit, so it kept the start circuit.
- **Mixed-stream MAE hides clean damage.** Mixed-stream validation MAE is a poor selection score: perturbed rays have fewer outliers, so it masks clean tail damage. That is why I added a clean validation limit, which only seed 1 had.
- **The area comparison is not fully controlled.** area_tol5 came from `train_stream.py`, which includes the police penalty (search weight 4) and ran 500 generations. My copy has no police term and ran 200 generations.
- **Code changed between runs.**
  - `acc-mix-s0` and `acc-clean-s0` ran on an earlier `search.py`, in which member 1 of each accuracy population was a mutant rather than the start circuit.
  - `area-mix-cleanlimit-s0` applied its clean limit only to search batches, not to validation selection; selection-time clean limits were added afterwards.
  - Rerunning with the current `search.py` therefore won't reproduce those runs bit for bit.
- **Selection draws differ between runs.** The selection validator's draws differ between `--share 0` and `--share .5` because the generator is consumed differently. This does not affect the standard numbers, which are always on the seed-1234 audit draws.
- **The models are simple.** Fixed k, Gaussian jitter, k independent of ambient. In particular, real pile-up rises with ambient flux and so is range- and scene-dependent. The mixpileup test only approximates that.
- **Not tested:** a weighted pile-up-walk term inside the area objective. It could be worth trying, given that a clean search already halves the walk.
- **CPU:** all jobs ran one at a time with one thread through `constraints_lab.slot`. Slot waits were ≤ 40 s and there was no starvation. Two short overlaps occurred when I re-queued my driver scripts; no two compute jobs of mine ran at once. The 2026-11-11 stop killed `acc-mix-s1` at generation 220. I did not rerun it, because its checkpoints answer the question it was started for.

**Reproduce (from `SPAD/`):**
```
# Part 2: references under every perturbation (about 2 min)
../.venv/bin/python -m constraints_lab.slot -- ../.venv/bin/python -m constraints_lab.sensor.evaluate \
  --out runs/2026-11-11_constraints-lab/sensor/eval-references --time-shift --variants clean jitter:0.5 \
  jitter:1 jitter:2 jitter:4 jitter:8 pileup:2 pileup:4 pileup:8 pileup:16 pileup:2+jitter:1 \
  pileup:4+jitter:2 bits:0.001 bits:0.01 bits:0.05 bits:0.01@0 bits:0.01@5 bits:0.01@9
# Part 3: main search runs (about 12 min each; area about 20 min)
../.venv/bin/python -m constraints_lab.slot -- ../.venv/bin/python -m constraints_lab.sensor.search \
  --out runs/2026-11-11_constraints-lab/sensor/acc-mix-s0 --threads 1 --objective accuracy --share .5 --generations 300 --seed 0
#   control: --share 0 --out .../acc-clean-s0
#   area:    --objective area --share .5 --clean-limit --generations 200 --out .../area-mix-cleanlimit-s0
# Score any circuit: evaluate.py --circuit name=path ; standard numbers + area + parity: finalize.py name=path --out X.json
```

Code is in `constraints_lab/sensor/`:
- `perturb.py`: the models.
- `evaluate.py`: scoring.
- `search.py`: copy of the hard-search loops with mixed batches, `--clean-limit` and checkpoint saving.
- `finalize.py`: standard audit, synthesis, parity.
- `table.py`: tables.
- `chain*.sh`: the run queues used.

Runs are in `runs/2026-11-11_constraints-lab/sensor/`. The standard numbers for all search circuits are in `standard.json`.
