# Flops track report: fewer flip-flops

## 1. Outcome

**Do not adopt a flip-flop constraint in any form tested: no hard cap on state bits, no 2x flip-flop weight, no 3-bit confidence counter.** The plain area objective already removes the one flip-flop that costs no accuracy (the reference 24.68 µm² design keeps 17 of the final design's 18). No variant found a better area/accuracy point than plain area within the 5% validation-MAE budget. Each result is one seed.

| Variant (from the final design, 150 generations) | Result against `base-s0` (24.68 µm², 17 flip-flops, MAE 0.364 m) |
|---|---|
| State cap 2 | Do not adopt. Best circuit is 20.32 µm² and 16 flip-flops, but MAE is 0.416 m (+14%), within 3 bins 69.5%, and the offset drifts to +1.3 steps at 128–256 photons. Nothing within budget. |
| State cap 1 or 0 | Do not adopt. MAE 0.791 m (+117%), 23.59 µm², 14 flip-flops. Cap 1 turned into cap 0: `state1` and `state2` only work as a pair, so dropping one drops both. |
| 2x flip-flop weight | Do not adopt as a default. Selected circuit is 24.06 µm², 16 flip-flops, MAE 0.380 m (+4.2%), within 3 bins 74.4%, the steadiest offset of any run (+0.45 to +0.51 steps). That is 0.62 µm² and one flip-flop less than base for 0.016 m more MAE, a trade along the same curve rather than a better point. |
| 3-bit confidence counter | Do not adopt. Repair could not recover the halved hysteresis: best MAE 0.464 m (+27%) at 24.90 µm², which is larger than base. Nothing within budget. |

If flip-flop count must fall (clock load, scan), use a weight rather than a cap. At the same 16 flip-flops, the 2x weight keeps MAE at 0.380 m against 0.416 m for cap 2. It lets the search drop the same two state bits (`state0`, `state3`) gradually and re-learn around them, while a cap forces them off at the start.

**Best register to save:** `state0`, then `state3`. They are the only flip-flops that can go at or near the accuracy budget. The confidence counter is the largest flip-flop subsystem (4.94 µm², 6 flip-flops) but cannot shrink without losing accuracy. The 10-bit candidate register is fixed by the 672 range bins.

## 2. How the constraint is measured, and how repeatable it is

**Flip-flops and area.**
- Measured with real Yosys + ASAP7 synthesis (`DFF*` cell count and area). Synthesis is deterministic.
- Live state bits and counter use come from structural liveness (`constraints_lab/flops/structure.py`):
  - It follows truth-table dependence back from the actions.
  - It counts inc/dec only when a live gate reads a confidence flag.
  - It treats a state bit whose next value is constant 0 as dead.
- It matched the synthesized flip-flop count on 9 of 10 existing circuits. The miss: it predicted 18 for the 24.68 µm² design, which synthesizes to 17.

**Logic that serves a register.**
- Measured by re-synthesizing with that register cut out (`common.cut_verilog`): its output becomes a free input and its next-value logic is dropped.
- With every register opened, each flip-flop costs 0.365 µm² of cell plus 0.02–0.26 µm² of load/reset logic.
- ABC is noisy, so single-bit cuts are good to about ±0.5–1.6 µm²; whole-register cuts are more reliable.

**Accuracy.**
- Measured with the standard `Validator(seed=1234).audit`: 3 photon sets of 5,505 rays each.
- Search selection uses the trainer's seed-7 photon sets. The same circuit scored on the two sets usually differs by 1–3% MAE (for example 0.3731 and 0.3642 m for the base pick). For tail-heavy circuits it can differ by up to 9% (`conf3-s0` best: 0.426 and 0.464 m).
- Differences under about 0.02 m are noise.

## 3. Table

Every circuit below has 0 netlist parity mismatches and a time-shift test of 99.9% or more. Offsets are in steps for the photon buckets 16–32 / 32–64 / 64–128 / 128–256.

**Searches, run from the final design** (population 192, 4,096 rays, 150 generations, seed 0):

| Circuit | Area µm² | Cells | Flip-flops | Live state bits | Counter bits | MAE m | Median m | Within 3 bins | Offset |
|---|---|---|---|---|---|---|---|---|---|
| Final design (start) | 26.83 | 295 | 18 | 0,1,2,3 | 4 | 0.363 | 0.151 | 76.2% | +0.0/+0.4/+0.6/+0.6 |
| `base-s0` chosen (plain area) | 24.68 | 253 | 17 | 1,2,3 (synth) | 4 | 0.364 | 0.162 | 76.9% | +0.6/+0.5/+0.3/+0.3 |
| `cap2-s0` best (none within budget) | 20.32 | 216 | 16 | 1,2 | 4 | 0.416 | 0.207 | 69.5% | −0.3/+0.2/+0.7/+1.3 |
| `cap1-s0` = `cap0-s0` best (none within budget) | 23.59 | 250 | 14 | none | 4 | 0.791 | 0.125 | 76.8% | +0.9/+0.3/+0.0/−0.0 |
| `w2-s0` chosen (generation 40) | 24.06 | 251 | 16 | 1,2 | 4 | 0.380 | 0.180 | 74.4% | +0.5/+0.5/+0.5/+0.5 |
| `w2-s0` search end (generation 110, +5.5% on selection, just over budget) | 20.44 | 208 | 16 | 1,2 | 4 | 0.391 | 0.165 | 73.1% | +1.8/+0.7/−0.3/−1.2 |
| `conf3-s0` best (generation 40, none within budget) | 24.90 | 263 | 17 | 0,1,2,3 | 3 | 0.464 | 0.152 | 75.8% | +0.1/+0.4/+0.5/+0.5 |
| `conf3-s0` search end (generation 90) | 20.38 | 219 | 16 | 0,1,2 | 3 | 0.498 | 0.166 | 72.7% | +1.7/+0.6/−0.3/−1.1 |

**Two consistency checks.**
- `base-s0` reproduces the reference area-optimized circuit (`final-design-tol5`) exactly: same 24.68 µm², 253 cells and MAE 0.364 m.
- Every search end near 20.3 µm² loses steadiness: an offset of about +1.8 to −1.2 steps, the same pattern as the reference's 20.02 µm² no-recheck circuit. That holds for `w2-s0`, `conf3-s0` and the reference run. `cap2-s0` keeps the 16–64 photon buckets steady but drifts to +0.7 and +1.3 steps at 64–256 photons.

**Existing circuits (Part 1), with register costs from synthesis cuts.**
- "Saved" is the area (and flip-flops) removed when that register is cut out.
- "Live state" is a count, with the configured state bits in brackets.
- The counter count includes state bits that only feed the counter.

| Circuit | Live state | Flip-flops | Area µm² | Flip-flop cell µm² | MAE m | Median m | Within 3 bins | All state saved (flip-flops) | Counter saved (flip-flops) | ±1 stepper saved |
|---|---|---|---|---|---|---|---|---|---|---|
| Final design | 4 (4) | 18 | 26.83 | 6.56 | 0.363 | 0.151 | 76.2% | 2.77 (4) | 4.94 (6) | 6.82 |
| Area-optimized | 3 (4) | 17 | 24.68 | 6.20 | 0.364 | 0.162 | 76.9% | 0.96 (3) | 4.77 (6) | 4.93 |
| Search end, no recheck | 2 (4) | 16 | 20.02 | 5.83 | 0.399 | 0.174 | 72.1% | 0.12 (2) | 6.92 (6) | 2.30 |
| random-s2-seed0 | 1 (2) | 15 | 22.76 | 5.47 | 0.473 | 0.186 | 71.9% | 0.90 (1) | 9.29 (5) | 5.79 |
| rule-s0-seed0 | 0 (0) | 14 | 22.51 | 5.10 | 0.537 | 0.143 | 76.2% | – | 2.04 (4) | 6.66 |
| rule-s4-seed1 | 2 (4) | 16 | 25.70 | 5.83 | 0.373 | 0.153 | 75.2% | 0.82 (2) | 4.94 (5) | 4.55 |
| rule-s4-seed0 | 4 (4) | 18 | 25.92 | 6.56 | 0.376 | 0.160 | 76.9% | 1.46 (4) | 5.39 (7) | 5.21 |
| rule-s4-seed0-nopolice | 3 (4) | 17 | 26.23 | 6.20 | 0.380 | 0.187 | 72.2% | 0.79 (3) | 2.55 (5) | 5.69 |
| random-s4-seed0-nopolice | 4 (4) | 18 | 26.71 | 6.56 | 0.390 | 0.182 | 71.2% | 3.35 (4) | 4.40 (5) | 7.09 |
| random-s4-seed1 | 4 (4) | 18 | 26.65 | 6.56 | 0.478 | 0.196 | 70.3% | 3.29 (4) | 4.93 (5) | 5.95 |

**Forcing bits off without retraining** (validation MAE, m):

| Change | Final design | Area-optimized |
|---|---|---|
| `state0` forced to 0 | 0.475 | 0.364 |
| `state3` forced to 0 | 0.756 | 0.828 |
| `state1` or `state2` forced to 0 | 9.25 | 9.12 |
| 3-bit counter | 0.441 (25.47 µm²) | 0.455 |
| 2-bit counter | 1.142 | 1.142 |

The counter sits at its maximum of 15 for 60–71% of photon steps in most circuits.

**Accuracy is not ordered by flip-flop count.** rule-s4-seed1 has 16 flip-flops and MAE 0.373 m. rule-s0-seed0 has 14 flip-flops and a median of 0.143 m, but its MAE of 0.537 m comes from bad-case pixels.

## 4. What the constraint costs and what it buys

**Flip-flops cost more than their cells.**
- The final design's 18 flip-flops are 6.56 µm² of cells (24%), or 9.96 µm² (37%) with their load/reset logic: about 0.55 µm² each.
- `dfflibmap` maps them to DFFHQx4 (0.3645 µm²), though DFFHQNx1 is 0.2916 µm². Using the smaller cell could save about 1.3 µm² with no logic change. This is an untested synthesis-flow idea, outside this track.

**What each constraint did, against plain area (`base-s0`).**
- **Cap 2:** saves 4.4 µm² and 1 flip-flop, but costs +14% MAE and steadiness at high photon counts. Forcing the bits off at the start costs more accuracy than the search can repair in 75 generations (repair reached 0.429 m).
- **Cap 1 / 0:** forcing the essential pair off costs 9 m. The repair brings that back to 0.79 m, but the logic it adds makes the circuit bigger than base (23.59 µm²).
- **2x weight:** saves 0.62 µm² and 1 flip-flop at +0.016 m MAE inside the budget. Beyond the budget it reaches 20.44 µm² at +5.5% (on the selection photon sets) and +7.4% MAE on the standard audit, but the offset there swings +1.8 to −1.2 steps.
  - Plain area stalled at 24.68 µm² over 150 generations; the weighted run kept shrinking.
  - Both runs share the same random stream until generation 10, so the weight changed the path. With one seed I cannot say whether it systematically reaches smaller circuits.
- **3-bit counter:** saves nothing at matched accuracy. The counter's depth acts as hysteresis: the counter reads 15 most of the time, and a hit is undone only after 14 net decrements.

## 5. What failed or is uncertain, and how to reproduce

**The drift in my first runs was not a bug in my copy of the search.**
- In trainer-matching mode the copy reproduces the unmodified `train_stream.py --objective area` exactly at every checkpoint, on seeds 0 and 1.
- The two copy differences (tie-break by loss relative to the anchor, one extra mutant per kind) do not cause drift (A/B on seeds 1 and 2).
- Scoring, the packed simulator and compile were all verified.

**The cause is that the design splits and validation disagree.** The search guards accuracy on train/architecture pixels, but validation reacts 2–3 times as strongly to the same edits, sometimes in the opposite direction. MAE relative to the anchor, on 4×8,192 fresh pixels per design split:

| Circuit | Train | Architecture | Validation (two photon sets) |
|---|---|---|---|
| Seed-1, generation 10 | ×0.97 | ×0.96 | ×1.09 / ×1.05 |
| Reference no-recheck end | ×1.04 | ×1.03 | ×1.08 / ×1.10 |

- Clean and non-clean validation pixels degrade by similar fractions, so this is a shift between captures, not the clean mask.
- Smaller searches (population 96, 2,048 rays) drift faster: seed 1 reached +9% by generation 10, against +2.3% at 192 / 4,096.
- `conf3-s0` shows the gap directly: it "repaired" to the anchor's level on the design splits while validation stayed 16% worse.
- **This applies to every track using the area search:** a 5% budget on the design splits does not bound validation MAE. Only validation-based selection does.

**Invalid or uninformative runs** (archived in `runs/2026-11-11_constraints-lab/flops/_superseded_2026-11-11/`):
- `base-s0_all-labelled-rays`: invalid. Scoring on all labelled rays put the loss near 85 against about 3 bins of MAE, so the 5% budget was huge slack.
- `base-s0_clean-rays-only` and the two `*_abandoned.log` files: uninformative. At 96 / 2,048 they drifted 14–21% and selected the start circuit.
- `cap2-s0_incomplete`: killed.
- `_diag`, `_match*`, `_tiebreak_ab` and `_trainer_check` are diagnosis evidence only.

**Uncertain or limited.**
- One seed per variant, and 150 generations against the reference's 500.
- 1.5x weight was not run.
- Cap 1 could not be tested separately with forcing, because `state1` reads `state2`. random-s2-seed0 (1 live bit, 15 flip-flops, 0.473 m) is the only 1-bit data point.
- The shared area model's activity probe misreads live state bits or counter use on 6 of 10 circuits (it reports no state flip-flops and no counter for the 24.68 µm² design). Any flip-flop term should use structural liveness.
- CPU waits on 2026-11-11 were 20 to 465 s; on 2026-11-12 there were none.

**Reproduce (from `SPAD/`).**

Part 1:
```
../.venv/bin/python -m constraints_lab.slot -- ../.venv/bin/python -m constraints_lab.flops.analyse
```

Main runs (about 3.5–10 minutes each):
```
C="--generations 150 --population 192 --search-rays 4096 --check-rays 4096 --mae-check 0 --validate-every 10"
zsh constraints_lab/flops/queue.sh "base-s0 $C" "cap2-s0 --state-cap 2 $C" "cap0-s0 --state-cap 0 $C" "cap1-s0 --state-cap 1 $C" "w2-s0 --flop-weight 2 $C" "conf3-s0 --conf-bits 3 $C"
```
Each run is slot-wrapped and writes to `runs/2026-11-11_constraints-lab/flops/<name>/`.

Collect and audit:
```
../.venv/bin/python -m constraints_lab.flops.collect base-s0 cap2-s0 cap0-s0 cap1-s0 w2-s0 conf3-s0
../.venv/bin/python -m constraints_lab.slot -- ../.venv/bin/python -m constraints_lab.flops.finalize
```
The second command writes `final_numbers.json`.

Code is in `constraints_lab/flops/`: `common.py`, `structure.py`, `analyse.py`, `search.py`, `queue.sh`, `diagnose.py`, `collect.py`, `finalize.py`.
