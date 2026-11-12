# Archive

Superseded or diagnostic material, kept for provenance. Nothing here is at the current
frontier, and no current result depends on it except where noted. Paths mirror the
live tree (`runs/`, `asic/results/`, `kaggle/batches/`).

## runs/

| Folder | What it is |
|---|---|
| 2026-11-05_pilot-smoke-test | A few steps of the histogram pilot, to check the pipeline |
| 2026-11-05_pilot-resume-check | Checks that pilot training resumes from a checkpoint |
| 2026-11-05_histogram-pilot | Original histogram-scanning design (superseded). `spad.evaluation.final_eval --pilot` still defaults to its `best.pt` |
| 2026-11-05_photon-stream-first-partial-run | First photon-stream jobs, stopped early |
| 2026-11-07_local-cpu_64-photons | First photon-stream sweep, M5 CPU, fixed 64 photons, rollback on |
| 2026-11-07_local-cpu_64-photons_no-rollback | Same, rollback off (ablation) |
| 2026-11-07_kaggle-t4_64-photons | First Kaggle batch, fixed 64 photons |
| 2026-11-08_local-cpu_physics-police_random-conditions | Police + randomized conditions on M5 CPU; superseded by the Kaggle runs of the same jobs |

## asic/results/

| Folder | What it is |
|---|---|
| 2026-11-10_random-s4-seed1_asap7_1500ps | First layout (2026-11-08 Kaggle random-s4-seed1), replaced by the batch-3 final design |

## kaggle/batches/

| Folder | What it is |
|---|---|
| 2026-11-08-police-randomized | Bundle, notebook and jobs for the 2026-11-08 Kaggle batch |

## video/

| File | What it is |
|---|---|
| spad_training_explainer_voice1.mp4, `_cinematic.mp4` | 2026-11-10 explainer covering every batch; replaced by `docs/video/spad_explainer.mp4`. Gitignored (17 and 50 MB) |
