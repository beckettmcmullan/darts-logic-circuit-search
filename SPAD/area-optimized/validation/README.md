# Validation scores

The scores behind the area-optimized circuit's accuracy numbers. Neither file
uses the held-out test recordings.

| File | What it is |
|---|---|
| [`batch3.csv`](batch3.csv) | The eight jobs of training batch 3, scored on the same validation photons. The chosen circuit is `random-s4-seed0`. |
| [`large_runs.json`](large_runs.json) | Four large validation runs (v1-v4) of this circuit and three histogram methods, split by recording set and photon count |

A **ray** is one pixel of one recording: its recorded photon histogram and its
reference distance. A **stream** is one random sample of photons drawn from a
ray's histogram, with extra background light mixed in; "20 draws" means 20
streams per ray in each photon-count band. One bin is 0.1124 m.

## batch3.csv

One row per job. Job names give the start (`rule` = hand-written rule,
`random` = random gates), the number of memory bits (`s0`, `s2`, `s4`) and the
seed; `nopolice` jobs trained without the physics check.

| Column | Meaning |
|---|---|
| `mean_error_m`, `median_error_m` | Error against the reference distance, in metres |
| `within_3_bins_pct` | Share of rays within 3 bins (34 cm) of the reference distance |
| `physics_check_flags_pct` | Share of answers the label-free physics check flags as not supported by the photons |
| `offset_bins_16_32_to_128_256_photons` | Average offset of the answers from the reference distance, in bins (positive = reads late), at 16-32 photons, then at 128-256 photons |
| `logic_area_um2`, `cells` | ASAP7 area and cell count of the logic after synthesis, before layout |
| `critical_path_ps` | Slowest-path estimate after synthesis, without wires ([`asic/synthesis/timing.py`](../asic/synthesis/timing.py)) |

## large_runs.json

```
bin_m                       one bin in metres (0.1124)
note                        what the runs are and what each metric means
runs
  v1-long-streams … v4-all-recordings-trusted
    what                    which rays, photon counts, draws and target
    bands
      "<split> <photons>"   e.g. "architecture 16-32"
        "<method>"          "histogram, tallest bar", "histogram, 8-bin box",
                            "histogram, sub-bin fit", "area-optimized circuit"
          streams, mae_m, median_m, recall_half_bin, recall_1_bins,
          recall_3_bins, over_1m, moved_target_mae_m
```

| Field | Meaning |
|---|---|
| `streams` | Number of streams scored |
| `mae_m`, `median_m` | Mean and median error, in metres |
| `recall_half_bin`, `recall_1_bins`, `recall_3_bins` | Share of streams within 0.5, 1 or 3 bins of the target (0 to 1) |
| `over_1m` | Share of streams more than 1 m off (0 to 1) |
| `moved_target_mae_m` | Mean error with every stream delayed by 300 bins. It should stay close to `mae_m`; a circuit that learned typical distances instead of tracking photons would get worse. |

The splits are `train`, `architecture` (the design recordings) and `validation`.
The tallest bar reads the highest histogram bin, the 8-bin box the highest sum
of 8 neighbouring bins, and the sub-bin fit reads the peak between bins.

| Run | Rays | Photons per stream | Draws | Target |
|---|---|---|---|---|
| v1 | at least 4,096 recorded photons | 16 to 4,096 | 6 | reference distance |
| v2 | every labelled ray | 16 to 256 | 20 | reference distance |
| v3 | trusted, at least 4,096 recorded photons | 16 to 4,096 | 6 | full-recording fit |
| v4 | every trusted ray | 16 to 256 | 20 | full-recording fit |

**Trusted rays.** The reference distances come from a separate lidar, and on
many rays they disagree with the SPAD pixel's own data. The dataset step marks
a ray *clean* when the reference distances of its neighbouring pixels agree
within 0.3 m, so it is not on an object edge
([`calibration.py`](../training/dataset/calibration.py), `edge_free`).
Even so, a sub-bin fit of every recorded photon is more than 9 bins (about 1 m)
off the reference distance on 0.8% of clean validation rays, 7.9% of clean
design rays and over 40% of the other rays. So v3 and v4 keep only *trusted*
rays, a stricter test that does not use the clean mark: at least 1,024 recorded
photons, and a full-recording fit within 3 bins of the reference distance. They
score against that fit. v1 and v2 score against the reference distances, so
every method's error is much larger there.

## Key numbers

Mean error on trusted rays of the design recordings:

| Photons | Area-optimized circuit | Tallest bar | 8-bin box | Sub-bin fit |
|---|---|---|---|---|
| 16-32 (v4) | 0.453 m | 0.295 m | 0.132 m | 0.104 m |
| 128-256 (v4) | 0.101 m | 0.129 m | 0.061 m | 0.032 m |
| 128-256 (v3) | 0.097 m | 0.103 m | 0.054 m | 0.028 m |
| 2048-4096 (v3) | 0.097 m | 0.059 m | 0.036 m | 0.007 m |

In v3 the circuit stays at about 0.097 m from 128 to 4,096 photons, while the
histogram methods keep improving. v4 covers more rays, so its 128-256 value
differs slightly.

The batch 3 scores (0.363 m mean for the chosen circuit) are on different photons
and against the reference distances, so they do not compare directly with this
table.

## Where they came from

- **`batch3.csv`**: training batch 3, eight jobs on a Kaggle T4 on 2026-11-10,
  about 30 minutes each.
- **`large_runs.json`**: four runs on Kaggle (2× T4) on 2026-11-18 with
  [`../../accuracy-focused/validation/eval_large.py`](../../accuracy-focused/validation/eval_large.py).
  The same runs also scored the accuracy-focused circuits; this file keeps the
  area-optimized circuit and the histogram methods. To score again, run
  `python -m validation.eval_large --help` from `SPAD/accuracy-focused/`.
