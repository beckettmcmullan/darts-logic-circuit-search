# The `training` package

Python code that trains a learned per-pixel range circuit for single-photon (SPAD) lidar:
the dataset, the gate-network model and its simulators, and the training.
A conventional pipeline builds a 672-bin histogram of photon arrival times for each
pixel and then takes the peak. This package instead trains a small circuit that keeps
one running range estimate per pixel and updates it as each photon arrives. No
histogram is stored.

Units: one time bin is 750 ps, which is about 0.1124 m of range
(`training.dataset.prepare.BIN_METERS`). A histogram has 672 bins. Ranges are stored as
bin indices and reported in metres.

All commands below run from `SPAD/area-optimized/` (the parent of this folder), which is the
package root. The dataset goes to `SPAD/data/`, shared with the accuracy-focused circuit.

## What the circuit is

The per-pixel state is a candidate bin (10 bits), a saturating confidence counter
(4 bits) and 4 learned memory bits. For each photon, a fixed comparator (not learned)
compares the arrival bin with the candidate and produces flags:

- `near1`, `near2`, `near4`, `near8`, `near16`: the arrival is within that many bins
  of the candidate
- `gt`, `lt`: the arrival is later / earlier than the candidate
- `zero`, `conf2`, `conf4`, `conf8`, `full`: the confidence count is 0, at least 2, 4, 8,
  or at its maximum
- two constants (0 and 1), and the 4 memory bits

These 18 signals feed 3 layers of 16 two-input gates (defaults in
`StreamConfig`). Layers 2 and 3 can also read the previous layer's outputs. Each gate has a
learned 4-entry truth table and learned choice of its two inputs. The last layer's
outputs are the next memory bits plus five actions: `replace` (candidate becomes the
arrival), `up` / `down` (candidate +1 / -1), `inc` / `dec` (confidence +1 / -1).
After the photon budget, the candidate is the range estimate. A photon marked `-1`
is padding and changes nothing.

## Package map

| Subpackage | Module | Purpose |
|---|---|---|
| `core/` | `stream_model.py` | The photon-stream circuit: the differentiable `StreamCore` for training, and three integer simulators (`simulate_stream`, `simulate_population`, bit-packed `simulate_population_packed`) that must agree exactly. Also `rule_circuit`, a hand-written circuit used as a baseline and starting point. |
| | `model.py` | `GateLayer` and `light_gate`, the learnable two-input-gate layer shared by everything. Also an older histogram-scanning model (`RecurrentLogic`) that the stream pipeline does not use. |
| `dataset/` | `download.py` | Download a pinned, size-capped subset of SP-TransientBench and the ASAP7 libraries. |
| | `prepare.py` | Project the Livox reference point cloud into the SPAD image, convert ranges to target bins, sample labelled rays per capture. Defines `BIN_METERS`. |
| | `calibration.py` | Refit the six camera numbers (fx, fy, cx, cy, k1, k2) on training captures; write refined labels and an `edge_free` mask. |
| | `scenes.py` | Add multi-view Reconstruction scenes as extra captures, split by scene. |
| | `photons.py` | Replay photon streams from recorded histograms (`sample_photons`, `sample_conditions`), build histograms from photons, and load a split (`load_rays`). |
| `training/` | `train_stream.py` | The training script (both phases). |
| | `police.py` | A label-free plausibility check used during training (see below). |
| | `baselines.py` | Reference methods: histogram peak, box filter, bias table, a small CNN, and the hand-written streaming rules. |

The hardware code (Verilog export, Yosys/ASAP7 synthesis, timing, the area model and
the circuit diagrams) is the `asic.synthesis` package in [`../asic/synthesis/`](../asic/synthesis/README.md).
It imports `training.core` to check the hardware against the Python simulator, and the
area objective in `train_stream.py` imports its area model.

## Data flow

```
dataset/download  ->  dataset/prepare  ->  dataset/calibration  ->  dataset/scenes
 raw files            processed/N.npz       labels_N.npz            more captures
 + ASAP7 .lib         + metadata.json       + calibration_report    (optional)
        |
        |  asic/synthesis/costs  ->  data/asap7/costs.json
        v
dataset/photons.load_rays(split)  ->  histograms [rays, 672] + target bins
        |
        |  sample_conditions: every training step draws fresh photon streams
        v
photons [rays, steps] (arrival bin, or -1)
        |
        v
training/train_stream
   phase 1: gradient (StreamCore, soft routing, then straight-through)
   phase 2: exact evolutionary search (packed simulator)
        |
        v
runs/NAME/circuit.json  ->  asic/synthesis: verilog, synth, timing, diagram
```

### Dataset

`download` fetches the raw histograms and Livox clouds for depth captures 1-10, with
SHA-256 checks and a byte budget (default 1.2 GB). `prepare` assigns captures to
splits (`SPLITS` in `download.py`): train 1-4, architecture 5, validation 6, test 7-8,
fresh_test 9-10. Routing, truth tables and checkpoint choice each use their own split.
`calibration` fits the lens numbers on the training captures by minimizing the median
distance between each histogram peak and its projected reference range, then writes the
final labels. The histogram peak is therefore used as an alignment reference, so the
labels are not independent of peak-based methods. `scenes` adds Reconstruction views
(whole scenes assigned to train, architecture or `scene_test`), dropping views whose
labels disagree with the histogram peak by more than `--max-label-error`.

### Photon streams

A histogram does not keep arrival order, so `sample_photons` draws arrivals at random
with replacement from each pixel's histogram. `sample_conditions` then randomizes the
exposure: each ray gets a photon count that is log-uniform in `[min, max]` (training
default 16 to 256) and an ambient level `b` uniform in `[0, max_background]` (default
0.6); each photon is replaced with probability `b` by a uniformly random bin. This is
repeated for every step, so the circuit never sees the same stream twice.

### Training (`training/train_stream.py`)

Phase 1, gradient training (`--steps`, default 1500):

- Each step does two updates. The routing logits are updated on a batch from the
  architecture split; the truth-table logits are then updated on a batch from the
  train split. Both use the Huber loss on the range (delta 4 bins), plus the police
  penalty and a small gate-area term.
- Routing is a softmax over source signals. A gate's truth table is four sigmoid
  probabilities and the gate output is the multilinear blend of them
  (`light_gate`). The softmax temperature falls geometrically from 2.0 to 0.15.
- From 30% of the steps (`--harden-after`) the forward pass uses the straight-through
  estimator: the comparator flags and gate routing and tables are rounded to hard
  values in the forward pass, while gradients flow as if they were soft.
- Every `--eval-every` steps (default 100) the hardened circuit is scored on the
  validation split. If, after the straight-through phase starts, its error is more
  than `--rollback-factor` (1.25) times the best so far, or any weight is non-finite,
  the model is restored to the best gradient state and the optimizer state is reset.

Phase 2, exact search (`--generations`, default 1000; `--population`, default 128):

- Works on the hardened circuit, scored exactly with
  `simulate_population_packed`, which holds 64 rays per machine word and does the
  subtractors, comparators, gates and counters as bitwise logic on bit-planes.
- Each generation makes `population/2` table mutants (flip a truth-table bit) and
  `population/2` wire mutants (re-route a gate input), scores table mutants on a fresh
  train batch and wire mutants on a fresh architecture batch, and keeps the best
  mutant only if it scores no worse than the current circuit. Scores are the Huber loss
  after removing each circuit's own median offset, plus the police violation rate and an
  area term.
- The best circuit by validation error is written out. Validation also fits a constant
  offset on train photons; it is stored as `offset_bins` in `circuit.json`.

`--objective area` switches phase 2 to shrink the circuit: it adds `prune` mutations,
estimates whole-core area with `asic/synthesis/area_model.py`, and keeps the smallest circuit
whose error stays within `--accuracy-tolerance` (default 5%) of the starting circuit.
When Yosys is installed, `--synth-candidates` shortlisted mutants are synthesized per
generation and a change is accepted only if real synthesis confirms it is smaller.
Start it from a trained circuit with `--init circuit --init-circuit PATH`.

Runs can be stopped with `--max-seconds` and continued with `--resume` (state in
`state.pt`).

### Police (`training/police.py`)

A training-only check that is not part of the chip and never sees labels. Given only the
photons, it builds the set of ranges the physics could explain: bins where a
cell-averaging CFAR detector finds a statistically significant return, and bins whose
Poisson-process likelihood is within a chi-squared cut of the best bin. A circuit's
answer is a violation if it lies more than `tolerance` (3) bins from every accepted
range (or from every CFAR detection, when there is one). The gradient phase adds a
differentiable hinge on that distance; the search adds the violation rate. The pulse
shape comes from the training histograms. The violation rate and a time-shift test are
reported in the audit, not used to select the final circuit.

### Hardware

See [`../asic/synthesis/README.md`](../asic/synthesis/README.md).

## Entry points

Run each as a module from `SPAD/area-optimized/`:

| Command | What it does |
|---|---|
| `python -m training.dataset.download [--root DIR] [--budget-bytes N]` | Fetch the pinned data subset. |
| `python -m training.dataset.prepare [--captures N ...] [--max-rays N] [--seed N]` | Project labels and sample rays. |
| `python -m asic.synthesis.costs [--root DIR]` | Build `data/asap7/costs.json` (needs the downloaded ASAP7 libraries). |
| `python -m training.dataset.calibration [--root DIR]` | Refine intrinsics, write labels. |
| `python -m training.dataset.scenes [--scenes ...] [--rays-per-view N]` | Add Reconstruction scenes. |
| `python -m training.training.baselines [--cnn-seconds S] [--out DIR]` | Reference methods; writes `design_metrics.json`. |
| `python -m training.training.train_stream --out runs/NAME [options]` | Train a circuit (below). |
| `python -m asic.synthesis.synth runs/NAME/circuit.json ...` | Verify and synthesize circuits plus the rule baseline. |
| `python -m asic.synthesis.timing runs/NAME/circuit.json ...` | Critical-path estimate. |
| `python -m asic.synthesis.area_model --circuits 400` | Refit `area_model.json` (slow: runs Yosys). |

`train_stream` options worth knowing (run with `--help` for all):

| Option | Default | Meaning |
|---|---|---|
| `--device` | `cpu` | `cpu` or `cuda`. |
| `--steps`, `--batch-size` | 1500, 256 | Gradient phase length and batch. |
| `--start-temperature`, `--end-temperature` | 2.0, 0.15 | Softmax temperature schedule. |
| `--harden-after` | 0.3 | Fraction of steps before the straight-through estimator starts. |
| `--rollback-factor` | 1.25 | Rollback trigger; 0 disables. |
| `--generations`, `--population` | 1000, 128 | Exact search length and size. |
| `--search-rays` | 1024 | Rays per search batch. |
| `--min-photons`, `--max-photons`, `--max-background` | 16, 256, 0.6 | Photon-stream randomization. |
| `--police-weight`, `--police-search-weight` | 1, 4 | Police weights; 0 disables. |
| `--init` | `random` | `random`, `rule` (from the hand-written rule), or `circuit`. |
| `--objective` | `accuracy` | `accuracy` or `area`. |
| `--compile`, `--compile-search` | `none`, `default` | `torch.compile` the gradient step / the search step. |
| `--resume`, `--max-seconds` | off, 0 | Continue from `state.pt`; pause after a time limit. |

Example:

```
python -m training.training.train_stream --out runs/my-run --device cuda
python -m training.training.train_stream --out runs/my-area-run --objective area \
    --init circuit --init-circuit runs/my-run/circuit.json
python -m asic.synthesis.synth runs/my-area-run/circuit.json
```

## Circuit file format

`circuit.json` is a `photon-stream-core-v1` dictionary: `config` (a `StreamConfig`),
`inputs` (names of the base signals), `actions`, and `layers`. Each layer lists, for
each gate, the two source indices (`inputs`) and the truth table
(`truth_tables`, order 00, 01, 10, 11). Layer 0 indexes the base signals; later layers
index the base signals followed by the previous layer's outputs. The trainer also adds
`offset_bins`, `budget` and `conditions`.

## Dependencies

`numpy` and `torch` for everything. `yowasp-yosys` for `asic/synthesis/synth.py`,
`timing.py` and the area objective's synthesis check. `asic/synthesis/costs.py` calls `tar` to read
`.7z` library archives (macOS `bsdtar` can; GNU tar may need `7z`).
