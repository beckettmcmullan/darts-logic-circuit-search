# Constraints lab: which extra constraints should the fixed-comparator search use?

Six parallel tracks, one constraint each, on the fixed-datapath photon-stream core
(`spad/core/stream_model.py`: a hand-built candidate register, comparator flags and confidence
counter, plus a learned controller of 3 layers x 16 two-input gates). This file is the protocol
every track follows. Read it fully before starting.

## Background (2026-11-11)

Power and delay are not the limiting factors for this core (about 1 GHz, far faster than photons
arrive), so the search now optimizes area: `python -m spad.training.train_stream --objective area
--init circuit --init-circuit <circuit.json> --steps 0 ...` keeps the smallest circuit whose
validation error stays within `--accuracy-tolerance` of the start, with every accepted change
confirmed by real Yosys + ASAP7 synthesis. Read `runs/2026-11-11_local-cpu_area-objective/README.md`
first: it has the method, the numbers and the lesson that motivated this lab. In short:

| | Final design | Area-optimized | Search end without recheck |
|---|---|---|---|
| Circuit | `runs/2026-11-10_kaggle-t4_batch3_fused-larger-search/random-s4-seed0/circuit.json` | `runs/2026-11-11_local-cpu_area-objective/final-design-tol5/circuit.json` | `runs/2026-11-11_local-cpu_area-objective/final-design-tol5_no-recheck/search_end_circuit.json` |
| Area (Yosys, ASAP7) | 26.83 µm², 295 cells, 18 flip-flops | 24.68 µm², 253 cells, 17 flip-flops | 20.02 µm², 207 cells, 16 flip-flops |
| Mean / median error | 0.363 / 0.151 m | 0.364 / 0.162 m | 0.399 / 0.174 m |
| Within 3 bins | 76.2% | 76.9% | 72.1% |
| Offset, 16-32 ... 128-256 photons | 0.0 ... +0.6 steps | +0.6 ... +0.3 | +2.0 ... -1.3 |

The 20 µm² circuit lost its steadiness across photon counts because nothing in the objective
measured it. Each track asks, for one candidate constraint: can it be measured reliably, what do
the three circuits above score on it, what does adding it to the search cost in accuracy and area,
and should it be adopted (and as a hard limit or a weighted term)?

## The six tracks

| Track folder | Constraint |
|---|---|
| `steadiness` | Offset must stay within a limit (for example ±1 step) across photon counts 16-256 and across background levels |
| `settle` | Photons needed to settle: score the answer after 16, 32 and 64 photons, not only at the end |
| `valid` | A "no target" output: a valid bit with a false-alarm limit on background-only pixels |
| `tail` | Bad-case error: 90th-percentile error or share of pixels off by more than 1 m, not only the mean |
| `sensor` | Behaviour under sensor effects not modelled so far: dead time, pile-up, timing jitter |
| `flops` | Fewer flip-flops: count or cap state and counter bits separately from gate area |

## Shared code (do not edit; import it, or copy into your track folder to change it)

| File | What it has |
|---|---|
| `spad/core/stream_model.py` | `StreamConfig`, `simulate_stream` (integer reference), `simulate_population_packed` (fast exact population simulator), `pack_circuit`, `unpack_circuit`, `rule_circuit`, `input_names`, `ACTIONS` |
| `spad/training/train_stream.py` | The trainer: `Validator` (standard score and `audit()` with offset by photon bucket and the time-shift test), `mutate` (table / wire / prune edits), `population_losses`, the area-objective loop in `main()` |
| `spad/dataset/photons.py` | `load_rays(root, split)`, `sample_conditions` (random 16-256 photons, extra ambient 0-0.6), `sample_photons` |
| `spad/training/baselines.py` | `metrics` (MAE, median, within N bins), `BIN_METERS` |
| `spad/training/police.py` | Label-free physics check used as a training penalty |
| `spad/hardware/area_model.py` | Fitted whole-core area estimate (rough: it only shortlists) |
| `spad/hardware/synth.py`, `verilog.py`, `timing.py` | `synthesize` (real area, about 1.5 s), `verify` (netlist parity), `stream_verilog`, `analyse` (critical path) |

A circuit is a `circuit.json` in format `photon-stream-core-v1`. One range bin is 0.1124 m.

## Rules

- Work from `SPAD/`. Python is `../.venv/bin/python`; run code as modules
  (`../.venv/bin/python -m constraints_lab.<track>.<script>`).
- Your code goes in `constraints_lab/<track>/` (add an `__init__.py`). Your runs go in
  `runs/2026-11-11_constraints-lab/<track>/<run-name>/`. Do not edit any file outside those two
  folders. If you need a changed trainer or simulator, copy the part you need into your track folder.
- Data: train and architecture splits to score mutants, validation split only to select and report.
  Never load the test, fresh_test or scene_test splits.
- Report every circuit with the standard numbers: `Validator(..., seed=1234).audit(circuit)` on
  conditions (16, 256, 0.6) with 3 photon sets (MAE, median, within 3 bins, offset by photon
  bucket, time-shift test), plus real synthesized area, cells and flip-flops, plus your
  constraint's own measure. Check netlist parity (`verify`) for any circuit you recommend.
- CPU: total machine use must stay at or below 80% (8 of 10 cores), shared by these 6 tracks and
  3 other running jobs. Every command that computes for more than about 10 seconds must be run
  through the slot wrapper, which waits for a free core and holds it while the command runs:
  `../.venv/bin/python -m constraints_lab.slot -- ../.venv/bin/python -m constraints_lab.<track>.<script> ...`
  One job at a time per track, one thread per job (`--threads 1`, `--synth-workers 1`,
  `torch.set_num_threads(1)`); never start a job outside the wrapper while one is running. Expect an
  area-objective run of 500 generations, population 192, 4,096 rays to take 20-40 minutes, plus
  time waiting for a slot; size your experiments to finish the whole track in about 2 hours of
  compute. Note in your report if jobs were starved or waited long.
- No git commits. No new dependencies. Do not touch `asic/`, `docs/`, `kaggle/` or `freeform/`.
- Be honest: one seed is one seed; say so. Repeat your main result with a second seed if time
  allows. Report what failed as well as what worked. Validation has 5,505 rays per photon set (16,515 for the 3 sets);
  differences in MAE under about 0.02 m are noise.

## What each track hands back

`constraints_lab/<track>/REPORT.md`, written for someone who has not followed your work:

1. The outcome first: adopt, adopt with changes, or do not adopt, and in what form (hard limit or
   weight, with the value).
2. How the constraint is measured, and how repeatable the measure is (same circuit, different
   photon draws).
3. A table: the three reference circuits and your runs, with the standard numbers and your measure.
4. What the constraint costs (area, accuracy) and what it buys.
5. What failed or is uncertain, and the exact command to reproduce the main run.

Your final message is a short summary of the same outcome with the key numbers.
