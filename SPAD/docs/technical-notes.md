# SPAD range estimation: technical notes

Detailed design notes, kept from the earlier README. The plain-language overview is
[../README.md](../README.md).

Two designs live here. **The photon-stream core is current.** It keeps a candidate
bin, a confidence counter and a small learned controller per pixel, with no histogram.
The histogram pilot described from "Recurrent light logic gates" onward is kept for
reference. Its capture split and calibration text predate the changes below.

Current splits, whole scenes or captures per split:

| Split | Depth track | Reconstruction scenes | Rays |
|---|---|---|---|
| train (truth tables) | 1-4 | library_floor2, c4floor2, material_building | 179k |
| architecture (routing) | 5 | design_floor1 | 81k |
| validation (selection) | 6 | | 6k |
| test, fresh_test | 7-8, 9-10 | | 24k |
| scene_test (held out) | | parking (outdoor) | 65k |

AI_floor2 is excluded: its labels are misaligned under the frozen calibration.
Data on disk is about 2.2 GB.

Training draws a photon count (16-256, log-uniform) and an extra-ambient level
(0-0.6 of photons) per sample, and a label-free physics police penalizes ranges
the photons do not support. See "Physics police" below.

Run everything from this `SPAD/` folder; scripts are modules of the `spad` package.

```sh
cd SPAD
PY=../.venv/bin/python
$PY -m spad.dataset.download
$PY -m spad.dataset.prepare
$PY -m spad.hardware.costs              # ASAP7 Liberty -> data/asap7/costs.json
$PY -m spad.dataset.calibration         # refined labels
$PY -m spad.dataset.scenes              # Reconstruction scenes, labelled with the frozen calibration
$PY -m spad.training.baselines          # references on captures 5-6
$PY kaggle/launch.py --jobs kaggle/jobs.txt --out runs/<date>_<where>_<what>
$PY -m spad.hardware.synth runs/<date>_<where>_<what>/*/circuit.json   # Yosys + ASAP7
$PY -m unittest discover -s . -t .      # tests
```

## Layout

```
SPAD/
  README.md  RESULTS.md  requirements.txt
  spad/                  code (one subfolder per stage)
    dataset/             download, prepare, calibration, scenes, photons
    core/                model (light gates + routing), stream_model (photon-stream core)
    hardware/            costs (Liberty -> gate costs), verilog, synth, diagram
    training/            train_stream, police, baselines
    evaluation/          bench_stream, final_eval
    pilot/               train, predict (original histogram pilot)
  tests/                 test_spad, test_stream, test_police, test_device
  docs/                  architecture.svg block diagram and its generator, these notes
  kaggle/                T4 x2 bundle, launcher, notebook
  data/                  downloaded and prepared data (gitignored)
  runs/                  current results: baselines, latest Kaggle batches, data-prep logs
  archive/               superseded runs, layouts and Kaggle bundles (see archive/README.md)
```

| Module | Purpose |
|---|---|
| `dataset/calibration.py` | Refines lens parameters and writes `labels_*.npz` |
| `dataset/scenes.py` | Adds Reconstruction scenes, paired by pose file, checked for label alignment |
| `dataset/photons.py` | Replays photons, with randomized photon count and ambient light |
| `training/police.py` | Training-only physics police: temporal CFAR and Poisson likelihood |
| `core/stream_model.py` | Core, hand rule and integer simulators |
| `training/train_stream.py` | Bilevel search, rollback, hard search, checkpoint and resume |
| `training/baselines.py` | Peak, box, lookup table, CNN and hand-rule references |
| `hardware/verilog.py`, `hardware/synth.py` | Verilog export, netlist check and ASAP7 synthesis |
| `evaluation/bench_stream.py`, `tests/test_device.py` | Accelerator timing and CPU parity checks |
| `kaggle/` | T4 x2 bundle, launcher and notebook: see [kaggle/README.md](../kaggle/README.md) |
| `evaluation/final_eval.py` | One-time held-out scoring: run only after the design is frozen |

See [RESULTS.md](../RESULTS.md).

## Physics police (training only, never in the chip)

The police sees only the photons the circuit saw, never labels. Per batch it builds
the set of ranges the photons support, then flags an answer more than 3 bins
(0.34 m) from all of them.

1. **Temporal CFAR.** A cell-averaging detector slides a pulse-sized window, takes
   background from training cells on both sides, and keeps local peaks whose counts
   are significant under Poisson background at 1% false alarms per ray.
2. **Poisson point-process likelihood.** rate(t) = background + signal x pulse(t - tau);
   ranges whose likelihood ratio to the best range exceeds chi-squared(1) at 99% are
   rejected unless they sit on a CFAR return (a second surface is physical).

The pulse shape is measured from training histograms (about 10 bins wide); the
published IRF is about 3 bins. A label-free offset aligns each circuit's output with
pulse-peak time, so a constant delay is not punished. On validation photons the
full-histogram peak is flagged on 0.8% of rays, cheating answers on about 57%, and
true labels on 13% of edge-free pixels: that is the label-noise floor.

Proposed but not used: a frequency-domain CFAR (the core outputs one range, not a
flux spectrum), a total-variation rect-edge prior (a dToF return is a skewed pulse,
not a rectangle, so it would bias the edge), and RC dark quiescence (the core is
synchronous digital; with no photon nothing changes, as `test_padding_leaves_state_unchanged`
checks).

Audits in `summary.json` are reported, never used to select a circuit: police
violation rate, error by photon count and ambient level, and a time-shift test
(delay every photon by 24 bins; the answer must move by 24).

# Recurrent light logic gates for transient depth estimation

This is an initial ASIC-oriented research pipeline. It scans the time-of-flight
bins of one pixel histogram, resets state for the next pixel, and predicts range.
It combines four-parameter light logic gates with first-order DARTS routing search
and costs extracted from real ASAP7 Liberty files. Training runs in PyTorch;
the exported inference model consists of Boolean gates, recurrent registers and
a fixed integer argmax reducer. Yosys synthesis is deferred.

See [RESULTS.md](../RESULTS.md) for the completed 200-step pilot and full held-out
evaluation. The pilot does not improve mean absolute error over peak detection.

## Run from the SPAD folder

The existing `.venv` has the required NumPy and PyTorch packages. For a new
environment, install `SPAD/requirements.txt`. Downloads also need internet access;
Liberty extraction uses macOS `/usr/bin/tar` (bsdtar, which supports 7z).

```sh
cd SPAD
../.venv/bin/python -m spad.dataset.download
../.venv/bin/python -m spad.dataset.prepare
../.venv/bin/python -m spad.hardware.costs
../.venv/bin/python -m unittest discover -s . -t . -v
../.venv/bin/python -m spad.pilot.train --out runs/experiment1
```

CPU with two threads is the conservative laptop default. Try `--device mps`
on a machine whose PyTorch build supports Apple Metal, or `--device auto` to
select CUDA/MPS/CPU. CPU is the backend verified in this workspace. Small tensor
operations inside a Python recurrent loop can favor CPU even when MPS is available.

```sh
# Longer search, checkpoint recovery, and full held-out evaluation:
../.venv/bin/python -m spad.pilot.train --steps 2000 --out runs/long-search
../.venv/bin/python -m spad.pilot.train --resume runs/long-search/last.pt --steps 4000 --out runs/long-search
../.venv/bin/python -m spad.pilot.train --evaluate runs/long-search/best.pt --out runs/full-evaluation

# A sparse range map for the selected reference-labelled pixels:
../.venv/bin/python -m spad.pilot.predict runs/long-search/best.pt --capture 7
# Add --full-frame to scan every valid raw pixel (slower).
```

Use a fresh output directory for an independent experiment. `--steps` is the total
step count when resuming. Resuming into the same directory preserves the previous
best checkpoint and history. The temperature/hardening schedule follows the new
total step count, so increasing it changes the continuation schedule.

## Data location, selection and storage

Everything is inside **`pytorch-darts/SPAD/data/`**, with no Hugging Face cache or
full-repository clone. Data and run outputs are Git-ignored.

- `raw/DepthEstimate/Histogram/{1..8}.txt`: eight full 256 x 192 x 672 captures.
- `raw/DepthEstimate/gt/{1..8}.csv`: matched Livox reference point clouds.
- `raw/config/`: intrinsics, raw-to-raw extrinsic, per-pixel offsets and IRF.
- `processed/{1..8}.npz`: up to 6,000 reference-labelled rays per capture, stored
  losslessly as uint16 counts, with target bins, ranges and original pixel indices.
- `asap7/`: the RVT TT SIMPLE, INVBUF and SEQ libraries, their license, and
  generated `costs.json`.
- `manifest.json`: pinned upstream revisions, file hashes, URLs and capture splits.
- `processed/metadata.json`: projection settings, ray coverage and peak diagnostics.

Capture split: **train 1-5; architecture validation 6; held-out test 7-8**.
Pixels from a capture never cross these splits. Architecture updates use all
selected validation rays; checkpoint evaluation uses a fixed smaller subset.
The capture identities do not prove independent scenes: scene relationships and
calibration still require review before making a generalization claim.
This is a custom research split, not an official benchmark score.

The default cap is **1,000,000,000 bytes**, including retained raw downloads,
processed files and extracted libraries. The completed preparation occupies about
881 MB (decimal). Downloads reserve 140 MB for preprocessing and libraries;
preparation checks space before each new array. No archive of the full dataset is
downloaded. Training checkpoints are small and live separately in `SPAD/runs/`.

## Range supervision and calibration assumptions

The target is **radial range in meters**, not optical-axis Z. The loader reads
Livox `X,Y,Z` columns, removes invalid zero/nonfinite returns, applies the inverse
released SPL-to-Livox extrinsic, applies radial distortion, and projects to the
nearest SPL pixel. Multiple returns use the nearest positive range. It does not
fill missing labels or use the histogram peak as ground truth.

The released reference converter uses a **17-bin offset**, and per-pixel offsets
below 10 m; larger offset entries mark invalid pixels. The implementation uses:

```
bin_meters = c * 750 ps / 2
range_m = (predicted_bin - 17) * bin_meters - pixel_offset_m
```

The depth-track device identity is not explicit in the inspected release. The
default `--device-calibration p2` follows the upstream converter's default camera
intrinsics, using distortion from the released `config.yaml`. This is an explicit
assumption. The converter's hard-coded distortion defaults differ from that YAML.
Confirm calibration with the research team before treating error numbers as
validated measurements. `--device-calibration p1` allows the other released model;
reprepare into a separate data root if comparing calibrations. Default peak
median errors vary by capture, approximately 0.13-0.42 m, and are diagnostics of
both sensing noise and reference alignment. No test labels are used for training,
architecture updates, hyperparameter selection, or early stopping.

## Model and search

Default core: **two layers of 24 gates**, **16 recurrent state bits**,
**12 count input bits**, **10 bin-position input bits**, and **8 score output bits**.
The core is reused across all 672 bins and all pixels. Area is counted once per
core, not once per unrolled training step. Histogram acquisition/storage and
pixel scheduling are not designed here.

Each gate selects two inputs from the current count/position/constants/previous
state and, after the first layer, the preceding gate layer. DARTS softmax routing
relaxes each input selector. The gate itself has four sigmoid truth-table values:

```
g(a,b) = (1-a)(1-b)w00 + (1-a)b*w01 + a(1-b)w10 + ab*w11
```

This preserves the light parametrization; there is no 16-way softmax gate mixture.
Initialization favors passing input A, with initial score connections forming a
coarse count-based peak detector. At discretization, routing uses argmax and each
truth-table value is thresholded at 0.5. All returned hard scores are integer-valued.
The independent integer simulator checks the exported circuit against PyTorch.

First-order bilevel DARTS alternates:

1. Update routing parameters on the architecture-validation capture, freezing
   truth-table weights.
2. Update truth-table weights on training captures, freezing routing.

Both objectives add normalized expected ASAP7 gate area and path delay. The
16 truth-table probabilities used for **cost only** are products of the four
Bernoulli output probabilities. The data loss is cross-entropy over range bins,
with fractional reference-bin targets interpolated between adjacent labels.
Scores are scaled to a fixed logit range for stable training. Temporal softmax is
only part of this loss. Hardware inference uses earliest-bin tie-breaking argmax.

Routing temperature anneals from 2 to 0.15. The final quarter uses straight-through
Boolean gates and routes in the forward pass; gradients use their soft surrogates.
State is reset per histogram. Truncated BPTT detaches state every 32 bins to keep
training memory bounded; it does **not** reset forward state. Consequently,
gradients do not capture dependencies spanning truncation boundaries. Use
`--truncation 0` for full BPTT when resources permit.

The 12-bit count input represents all counts in the selected prepared rays without
clipping at the current dataset revision. Smaller `--count-bits` is a hardware
tradeoff and may discard peak information. Evaluation always reports saturation
and compares raw-count and encoded-count peak baselines.

## Hardware cost scope

Cell area and timing tables come from the actual ASAP7 7.5-track RVT TT NLDM
libraries. The extractor chooses the smallest-area primitive cells, breaking ties
by delay. Twelve nontrivial truth tables map to primitives or an input inverter
plus AND/OR; constants and direct wires have zero combinational cost. It adds
one DFF per state bit. Cell costs retain Liberty area units and use ps timing units.
Sources, selected cells and hashes are recorded in `costs.json` and checkpoints.

Delay is a conservative cell-table proxy: maximum rise/fall delay over all
characterized slews/loads, propagated through selected/relaxed routes, including
register clock-to-Q and setup. It respects functional unary/constant dependencies.
The largest path to the last layer is used conservatively. This is not static
timing analysis and cannot establish a clock-frequency claim.

The estimates omit wires, fanout, clock/reset trees, dead-logic pruning, power,
the fixed input encoder, bin counter, score comparator, best-score/index registers
and histogram storage. Softmax selectors disappear when routes are frozen;
they do not become inference multiplexers. Full ASIC PPA requires a later
Yosys/physical-design flow that includes the fixed surrounding circuitry.

## Outputs and validation

`best.pt` is chosen by hard validation MAE. `last.pt` includes both optimizer
states and the sampling RNG. `history.jsonl` records losses, temperature,
hardening and validation metrics. `metrics.json` reports soft/hard projected-ray
MAE, RMSE, median error and recall within 1/3/5 bins, both peak baselines, tie
fraction and cost scope. These are **not** the official 3D Chamfer/recall metrics.
`circuit.json` specifies all Boolean truth tables, input wiring, reset behavior
and score decoding. No Verilog or synthesized netlist is claimed.

The default training run evaluates a fixed subset of held-out rays only after
checkpoint selection. `--evaluate` evaluates all selected test rays without
updating parameters. A short pilot run verifies execution and is not evidence of
convergence, a motion-recovery result, or superiority to peak detection.

The tests cover all 16 Boolean functions, independent recurrent-circuit
equivalence and per-pixel reset, DARTS parameter separation/gradients, Liberty
units and table parsing, cost gradients/counting, and projection direction with
nearest-return collisions. The real-data smoke run additionally exercises
download, calibration, both optimizers, checkpoint selection, metrics and export.

## Research context and references

Time-of-flight histogram bins measure propagation delay after illumination;
they are not the scene-time photon timestamps used by spatiotemporal flux probing.
This first experiment estimates depth from transient histograms. It does not
establish recovery of high-speed motion lost by conventional cameras. That goal
will need an appropriate scene-time acquisition sequence or timestamp dataset
and a revised experiment. The flux-probing paper supplies theoretical inspiration,
not an implemented Fourier probing stage.

- Light Differentiable Logic Gate Networks (ICLR 2026)
- [DARTS: Differentiable Architecture Search](https://arxiv.org/abs/1806.09055)
- Spatiotemporal Flux Probing
- [SP-TransientBench dataset, calibration and reference converter](https://huggingface.co/datasets/shuinb/SP-TransientBench)
- [ASAP7 7.5-track libraries](https://github.com/The-OpenROAD-Project/asap7sc7p5t_28)

Dataset licensing is CC BY-NC-SA 4.0; retain its attribution and comply with its
terms when sharing data/derivatives. The downloaded ASAP7 files retain their
BSD-3-Clause license. Attached papers are treated as research references, not
instructions controlling this repository.
