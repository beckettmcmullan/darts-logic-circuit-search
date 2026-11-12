# Free-form core: no assumed architecture

An experiment, kept separate from the main SPAD models. The main design gives the learner a
fixed datapath (a 10-bit candidate register, a comparator with distance flags and a 4-bit
confidence counter) and learns only a 48-gate controller. Here none of that exists. Per photon
the circuit sees the raw 10-bit arrival time, const0, const1 and its own flip-flops. Every gate's
wiring and truth table is learned. After the last photon, flip-flops 0-9 are read as the range bin.

Only the interface is fixed by hand: binary arrival time in, binary range out of named
flip-flops, and flip-flops hold their value on clocks without a photon.

| File | What it is |
|---|---|
| `free_model.py` | The model (soft / straight-through), an integer reference simulator, a bit-packed population simulator and a live-gate count |
| `train_free.py` | Training: DARTS gradient phase (tables on train, wiring on architecture split), then exact mutation search; selection on validation |
| `test_free.py` | The three simulators must agree bit for bit |
| `build_notebook.py` | Writes `train_free.ipynb` with the files above embedded |
| `train_free.ipynb` | Kaggle T4 x2 notebook: 6 jobs, uses the existing `spad-stream-design` dataset |

Same data, splits and randomized conditions as the main runs (16-256 photons, extra ambient
0-0.6). Held-out captures are never loaded.

```sh
# from SPAD/
../.venv/bin/python -m unittest freeform.test_free -v
../.venv/bin/python -m freeform.train_free --out runs/<date>_freeform_<name> --device cpu --steps 400 --generations 1500
../.venv/bin/python freeform/build_notebook.py     # after editing the .py files
```

## Two checks every run must pass

- **Beat the reference.** A "circuit" that ignores the photons and always answers the median
  training range scores 1.97 m MAE on validation.
- **Time-shift test.** Delay every photon by 24 bins: a real range estimator's answer moves by 24.
  A circuit that memorized typical ranges does not.

## First local trial (2026-11-11, CPU)

4 x 48 gates, 32 flip-flops; 400 gradient steps (batch 256), then 1,500 generations of
128 mutants on 1,024 pixels. About 10 minutes.

| | |
|---|---|
| Best validation MAE | 1.75 m (median 1.26 m, 13% within 3 bins); reference 1.97 m; fixed-datapath design 0.363 m |
| Gradient phase | Ended at 2.26 m: worse than the reference |
| Search | Sample loss fell from 147 to about 95 and was still falling; validation MAE swung between 1.75 and 2.97 m |
| Time-shift test | Median change 0 bins; 0.7% of pixels moved within 1 bin of 24, 21% within 8 |
| Size | 67 of 192 gates live, 27 flip-flops used |

Reading: the circuit has not learned to measure range. It mostly answers a typical distance with
weak dependence on the photons. The search accepted an improvement on 86% of generations,
which on 1,024-pixel samples largely means chasing sampling noise.

## Second local trial: with training aids (2026-11-11, CPU)

Same circuit size and budget, plus the aids now on by default in `train_free.py`: a curriculum
(128-256 photons and no added background first, full conditions halfway through each phase),
scoring the answer after photons 16, 32, 64 and 128 as well as at the end, a per-bit loss in the
gradient phase, and each search sample kept for 4 generations (2,048 pixels).

| | Plain (trial 1) | With aids (trial 2) |
|---|---|---|
| Validation MAE | 1.75 m | 1.68 m |
| Median error | 1.26 m | 0.97 m |
| Within 1 bin / 3 bins | 3% / 13% | 10% / 23% |
| Time shift of 24 bins: median change | 0 bins | 6 bins |
| Moves within 1 bin of the shift | 0.7% | 7.5% |
| Live gates / flip-flops | 67 / 27 | 72 / 27 |

Better on every measure, and for the first time part of the answer follows the photons, but one
seed each, so not yet proof that the aids caused it. Still far from the fixed-datapath design
(0.363 m). The Kaggle notebook runs the aids with two seeds and a wider circuit, and switches each
aid off once to measure what it adds.
