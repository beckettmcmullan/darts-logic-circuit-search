# Valid-bit track: a "no target" output

## 1. Outcome: adopt with changes

- **Adopt the output.** Add `valid_out = confidence >= 8` to the core. That is the confidence counter's top bit, which already feeds the existing `conf8` flag, so it adds no flip-flops.
  - With background-only pixels drawn uniformly over the 672 bins, the final design gives **97.6% detection at 0.10% false alarms**. That is 10 times inside a 1% limit.
  - Synthesized area moves by +0.31 to +0.42 µm², which is within Yosys/ABC run-to-run noise.
  - Netlist parity: 0 mismatches on the candidate and 0 on the valid bit.
  - The threshold that just fits the limit is `conf>=6` (98.6% detection at 0.90%). It sits too close to the limit: on a second photon draw its false-alarm rate was 1.00%.
- **Add it to the search only as a hard limit at selection time, not as a weight.** The limit: on uniform background-only validation pixels, false alarms ≤ 1% with detection ≥ 97% for the `conf>=8` readout.
  - No area search so far has moved this number: 97.5-97.6% at 0.08-0.10% for all three reference circuits, including the 20 µm² search end.
  - It is therefore a cheap guard rail (one extra simulation per selection), not something that steers the search.
- **Do not adopt a structured-stray-light valid term (weighted or limited) for now.** It can be bought, but it costs range accuracy:
  - Seed 0: validation error (MAE) +8.5% on fresh photons and RMSE +20%.
  - Seed 1: no checkpoint stayed within the error limit, so selection kept the start circuit.
  - The result also depends entirely on how the synthetic background is built.
- **Extra logic tried for structured background did not pay off.**
  - A wider "shadow" confidence counter costs +5.6 to +7.5 µm² and does not help.
  - A minimum-range blank does not help either.
  - If needed later, the most promising extra logic is a small photon counter (see section 4). It was not synthesized.

## 2. How the measure works and how repeatable it is

**Real-return pixels.** The standard `Validator(seed=1234)` photons: validation split, 3 photon sets, 16-256 photons, extra ambient 0-0.6. Note that validation has **5,505 rays per set (16,515 total)** in this checkout, not the 11,010 the protocol states.

**Background-only pixels.** Built from validation only for reporting, and from train/architecture only for scoring mutants. All are at the same log-uniform 16-256 photon counts (`constraints_lab/valid/background.py`). Each construction makes a different assumption:

| Set | Construction | Assumption |
|---|---|---|
| uniform | Every photon uniform over the 672 bins | No-target light is flat in time: low-flux ambient, no pile-up, no crosstalk. This is the limit (b = 1) of the training data's own extra-ambient model. |
| residual | Per-capture mean of return-removed histograms. The window target−12 to target+30 is cut from every pixel, then normalized and averaged. Extra ambient 0-0.6 on top. | The label marks the only target, and stray light in a no-target pixel has the capture-average time profile. |
| residual_far | Same as residual, with bins below 48 (about 3.5 m) also dropped | The early crosstalk zone is blanked or ignored. |
| pixel | Each pixel's own return-removed histogram (pixels with ≥128 residual photons) | Stress test only. These are not no-target pixels: they hold second surfaces, and re-drawing inflates peaks. Every circuit fails it (about 20% false alarms even at conf=15). |

**What the residual actually contains.** It is not ambient light. These indoor captures have very little ambient: in the median pixel 97% of photons are in the return.
- In train/architecture captures, 59-66% of the residual is an early peak at bins 16-48 (crosstalk or near clutter, 17-23 times the uniform level). The rest is a broad hump at bins 64-200 from scene stray light; the flat floor is only 10-20%.
- In the single validation capture, the early peak is only 12% and the hump dominates.
- So the design and validation residuals have different shapes.
- At the same exposure, a true no-target pixel here would receive only about 2-8% of a return pixel's photons. Using equal photon counts is the hard case (bright ambient filling the budget).

**Readouts** need no new logic: `confidence >= k` for k = 1..15, and each state bit or its inverse, read at the end of the stream. The score is the best detection whose false-alarm rate is ≤ 1%. For search and selection I linearly interpolate the confidence ROC exactly to the limit, because the hard number jumps between 0 and about 0.77 when one threshold crosses 1%. Reports give the hard number.

**Repeatability** (same circuit, new photons for real and background pixels, seed 999):
- Uniform: detection changes by ≤ 0.4 points and false alarms by about 0.1 point. Binomial standard error at a 1% false-alarm rate with 16,515 rays is 0.08 points.
- The pass/fail decision is fragile when a threshold sits near the limit. Final design `conf>=15` on residual: 0.99% (passes, 76.8% detection) on one draw, above 1% (fails) on the other.
- Hence the recommended 10× margin (`conf>=8`).

**Simulators.** `constraints_lab/valid/sim.py` holds copies of `simulate_stream` and the packed population simulator that also return confidence and state. Both were asserted equal to the shared simulator on candidates, and to each other on all registers.

## 3. Results table

All numbers come from the standard audit (seed 1234, conditions 16-256 photons and 0.6 ambient, 3 sets) plus Yosys/ASAP7 synthesis of the core without the extra output port. Detection columns are % detected at the stated false-alarm (FA) rate. "Offset" is offset in steps for the photon buckets 16-32 / 32-64 / 64-128 / 128-256. All circuits pass the time-shift test at 100%.

| Circuit | Area µm² / cells / flops | MAE / median m | Within 3 bins | Offset | Uniform, `conf>=8` | Uniform, best at ≤1% | Uniform + residual, best at ≤1% | residual_far, best at ≤1% |
|---|---|---|---|---|---|---|---|---|
| Final design | 26.83 / 295 / 18 | 0.363 / 0.151 | 76.2% | 0.0 / 0.4 / 0.6 / 0.6 | 97.6% at 0.10% | 98.6% (`conf>=6`, 0.90%) | 76.8% (`conf>=15`, 0.99%) | none |
| Area-tol5 | 24.68 / 253 / 17 | 0.364 / 0.162 | 76.9% | 0.6 / 0.5 / 0.3 / 0.3 | 97.6% at 0.10% | 98.6% | 82.4% (`conf>=15`) | none |
| Search end, 20 µm² | 20.02 / 207 / 16 | 0.399 / 0.174 | 72.1% | 2.0 / 0.7 / −0.3 / −1.3 | 97.5% at 0.08% | 98.5% | 81.7% (`conf>=15`) | none |
| A: accuracy, valid weight 20, gen 10 | 27.22 / 293 / 18 | 0.465 / 0.164 | 76.1% | 0.7 / 0.4 / 0.3 / 0.3 | 90.7% at 0.28% | 95.8% | 80.4% | 76.2% |
| A: gen 120 | 27.12 / 280 / 18 | 0.484 / 0.185 | 72.7% | 1.1 / 0.4 / 0.3 / 0.3 | 92.3% at 0.28% | 96.6% | 86.4% | 80.1% |
| **C: accuracy, weight 20, range loss ≤ +1%, seed 0 (selected)** | 26.48 / 276 / 18 | **0.394** / 0.130 | 77.9% | 0.9 / 0.2 / 0.0 / 0.0 | 94.8% at 0.01% | 97.3% (`conf>=6`, 0.25%) | **88.7%** (`conf>=11`, 0.84%) | **77.1%** (`conf>=14`) |
| C, seed 1 | No checkpoint within 3% error; start kept | | | | | | | |
| B: area objective plus valid limit (selected) | 25.44 / 266 / 17 | 0.354 / 0.148 | 77.6% | 0.5 / 0.3 / 0.3 / 0.3 | 97.6% at 0.10% | 98.6% | 76.3% | none |
| B: search end | 20.40 / 222 / 16 | 0.391 / 0.165 | 73.1% | 1.8 / 0.7 / −0.3 / −1.2 | 97.6% at 0.08% | 98.6% | 81.9% | none |

**Q2: existing state as a valid bit (ROC for the final design).**

| k | Detection | FA uniform | FA residual | FA residual_far |
|---|---|---|---|---|
| 5 | 98.9% | 2.06% | 25.6% | 42.4% |
| 6 | 98.6% | 0.90% | 19.8% | 36.6% |
| 7 | 98.2% | 0.27% | 15.5% | 31.9% |
| 8 | 97.6% | 0.10% | 12.3% | 27.8% |
| 10 | 95.6% | 0.02% | 6.7% | 19.7% |
| 12 | 91.7% | 0.01% | 3.7% | 13.2% |
| 14 | 84.4% | 0.00% | 1.7% | 7.7% |
| 15 | 76.8% | 0.00% | 1.0% | 4.8% |

Area-tol5 and the 20 µm² search end are within about 1 point of these at every k up to 13; at k = 14-15 they detect 4-6 points more.

By photon bucket, `conf>=8` on the final design:

| Photons | Detection | FA uniform | FA residual |
|---|---|---|---|
| 16-32 | 92.2% | 0.05% | 6.7% |
| 32-64 | 98.6% | 0.09% | 11.4% |
| 64-128 | 99.6% | 0.19% | 14.8% |
| 128-256 | 99.7% | 0.07% | 16.0% |

- Uniform false alarms barely depend on photon count; the weak spot is detection at 16-32 photons.
- With residual background, false alarms grow with photon count, because stray light keeps pushing the 4-bit counter to saturation. Within the 64-256 photon buckets no threshold meets 1% (conf=15 gives 1.1-1.7%).
- On the design captures (`design_check.json`), residual false alarms are 34-50% even at conf=15, because the crosstalk peak looks like a return.
- State bits are poor valid bits. One exception: the 20 µm² circuit's `~state0` gives 97.3% at 0.08% on uniform, but that bit is otherwise unused, so reading it out costs a flip-flop.
- The valid bit flags "a return is present", not "the range is right": valid-and-within-3-bins is 75.0% against 76.2% within 3 bins overall.

## 4. What it costs and what it buys

**The readout, synthesized.** Every variant passed netlist parity with 0 mismatches.

| Circuit | Readout | Area change | Flops |
|---|---|---|---|
| Final design | `conf>=6` | −0.15 µm² | unchanged |
| Final design | `conf>=8` | +0.42 µm² | unchanged |
| Final design | `conf>=15` | +0.55 µm² | unchanged |
| Area-tol5 | `conf>=6` / `conf>=8` / `conf>=15` | +0.76 / +0.31 / +0.19 µm² | unchanged |
| 20 µm² search end | `conf>=6` | +0.79 µm² | unchanged |
| 20 µm² search end | `~state0` | +0.83 µm² | +1 |
| Run C | `conf>=6` / `conf>=14` | −0.15 / +0.25 µm² | unchanged |

**Inside the area objective (run B).**
- The valid limit never bound. The search shrank to 20.4 µm² exactly like the plain area run (same steadiness loss: offset +1.8 to −1.2 steps), and selection kept 25.44 µm² for error reasons.
- Every area-searched circuit keeps the uniform valid bit at about 97.6% (`conf>=8`).
- So protecting the valid bit costs no area.
- Caveat: the run used residual_far, where the start circuit already scores about 0 (hard number), so that part of the limit was empty. Run B was 150 generations at population 96, so its area is not comparable with the 500-generation tol5 run.

**Fixed-area accuracy objective with a valid weight (runs A and C).**
- The search finds controllers whose confidence rises less on stray light: residual_far detection goes from 0 to 77-80%, residual from 77% to 86-89%.
- Without a range limit (A), MAE rose 28-36% and selection kept the start circuit.
- With the range loss capped at +1% on the same pixels (C, seed 0), the selected circuit had MAE +2.7% on the selection photons but **+8.5% on fresh photons** (0.394 m, about 1.5 times the 0.02 m noise floor). It is better on typical pixels (median 0.130 m, within 3 bins 77.9%) and worse in the tail (RMSE 2.55 m against 2.12 m). Low-photon detection also drops (16-32 photons: 82.7% at `conf>=8`).
- Seed 1 of C found the same kind of valid gain (73% detection) only at MAE +25%, so selection kept the start.
- Summary: the valid bit against structured stray light can be improved, but on these two seeds not without hurting range error.

**Minimal extra output logic for structured background.**
- *Shadow counter* (`shadow.py`): a 5-7 bit counter with the same increment/decrement as confidence, which the controller never sees. It costs +5.6 to +7.5 µm² (+21-28%) and 5-7 flip-flops, and passes parity. It does not help: uniform + residual detection is 70.3% at 5 bits against 76.8% for plain `conf>=15`. On residual_far it reaches 43-55% at 6-7 bits. The confidence update rule counts stray-light hits as well as return hits.
- *Minimum-range blank* (`candidate >= B` and confidence ≥ k): no help on validation, where false-alarm candidates sit at bins 110-146. On design captures it would need B ≈ 48, which blanks roughly a third of real design targets.
- *What would likely work* if no-target pixels really arrive at a fixed exposure: a per-pixel photon count gate. With the same exposure, a no-target pixel here gets about 2-8% of a return pixel's photons. I did not synthesize it; going by the 5-bit shadow counter, a saturating up-counter should cost a few µm².

## 5. What failed or is uncertain, and how to reproduce

**Dependence on the synthetic pixels.**
- The adopt decision rests on the uniform set. That set matches the training data's own ambient model, but no real no-target capture exists in the design splits.
- The structured-light conclusions rest on residual profiles that differ between design captures (crosstalk-dominated) and validation (hump-dominated).
- Real no-target data (sky or open-door pixels, or a scene with the target removed) would decide both. Until then, treat stray-light false-alarm rates as unknown.

**Search caveats.**
- One seed per configuration, except C, which has two that disagree.
- Selecting on validation over 15 checkpoints overfits: +2.7% error at selection became +8.5% on fresh photons.
- The design-split range loss is noisy (±10% between batches), so a 1% range limit on it does not hold validation MAE within 1%.

**Other notes.**
- CPU starvation: the first smoke test waited more than 10 minutes for a slot and run A waited 319 s; other jobs started within seconds.
- `pkill` of the smoke test also killed my own wait loops; this did not affect any reported run.
- Repeat draws for the first `roc_all` table lack residual_far columns. Fixed in `roc.py`; `roc_more` has them.

**Commands (from SPAD/, all through the slot wrapper).**
- `../.venv/bin/python -m constraints_lab.slot -- ../.venv/bin/python -m constraints_lab.valid.roc` gives the Q2 ROC of the three references (`runs/.../valid/roc/roc.json`). `constraints_lab/valid/summarize.py <roc.json>` prints the tables.
- Main search (run C):
  `../.venv/bin/python -m constraints_lab.slot -- ../.venv/bin/python -m constraints_lab.valid.search --objective accuracy --init-circuit runs/2026-11-10_kaggle-t4_batch3_fused-larger-search/random-s4-seed0/circuit.json --out runs/2026-11-11_constraints-lab/valid/accuracy-valid-w20-rangelim1-seed0 --valid-weight 20 --range-tolerance .01 --residual-min-bin 48 --accuracy-tolerance .03 --generations 150 --population 128 --search-rays 2048 --background-rays 4096 --validate-every 10 --seed 0 --threads 1`
- The full chains are in `constraints_lab/valid/run_all.sh` (A, B), `run_after.sh` (C, readout synthesis, shadow counter, final ROC) and `run_more.sh` (C seed 1).
- Readout synthesis and parity: `python -m constraints_lab.valid.verilog_valid <circuit.json> 'conf>=8' --verify`.

## Short summary

- **Adopt** `valid_out = confidence >= 8` (the counter's top bit; no new flip-flops; area within about ±0.5 µm² synthesis noise; parity clean). Use it with a **hard selection limit**: false alarms ≤ 1% on uniform background-only pixels, detection ≥ 97%.
  - Final design: 97.6% detection at 0.10% false alarms (98.6% at 0.90% with `conf>=6`). Detection falls to 92% at 16-32 photons.
  - Every area-shrunk circuit, down to 20 µm², keeps this, so the limit costs nothing today.
- **Do not adopt** a structured-stray-light valid term. Against return-removed backgrounds, no confidence threshold holds 1% false alarms beyond 64 photons (best overall: 77-82% detection at conf=15).
  - The search can push this to 89% (residual) and 77% (residual_far), but on seed 0 that cost +8.5% MAE on fresh photons and +20% RMSE; seed 1 found no circuit within the error limit.
  - A wider shadow counter (+5.6 to +7.5 µm²) does not fix it.
- **Confidence in these conclusions:** strong under the flat-ambient assumption; stray-light behaviour is unknown until real no-target captures exist.
