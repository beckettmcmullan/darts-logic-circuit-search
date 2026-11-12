# Batch 2026-11-08: physics police + randomized photon conditions

Everything needed to run this batch on Kaggle (T4 x2).

| File | What it is |
|---|---|
| `spad-stream-design.zip` | Dataset bundle: code, `costs.json`, design captures 1-6 and the train/architecture scenes. No held-out data (7-10, parking). |
| `train.ipynb` | Notebook. Writes `spad_runs_police.zip`. |
| `jobs.txt` | The 8 jobs, for reference (the bundle carries its own copy). |

## Steps

1. On Kaggle, open the `spad-stream-design` dataset, choose **New Version**, and upload
   `spad-stream-design.zip`. Keep it **Private** (CC BY-NC-SA 4.0). The old version
   lacks `police.py` and the new scenes, so this notebook will not run on it.
2. **New Notebook > File > Import Notebook**, pick `train.ipynb` from this folder.
3. Attach the new dataset version under **Input**, set **Accelerator** to **GPU T4 x2**.
4. **Save Version > Save & Run All**.
5. Download `spad_runs_police.zip`, unzip it into `SPAD/runs/2026-11-08_kaggle-t4_physics-police_random-conditions/`, then:

```sh
cd SPAD
../.venv/bin/python -m spad.hardware.synth runs/2026-11-08_kaggle-t4_physics-police_random-conditions/*/circuit.json --out runs/2026-11-08_kaggle-t4_physics-police_random-conditions/synthesis.json
```

## What is different from the first batch

- Photon streams are up to 256 long instead of 64, so each pass costs about 4x.
  The notebook lowers the defaults to batch 1024, population 128, search rays 1024,
  600 generations. Check the benchmark cell: if `circuits_per_second` is still rising
  at the largest population, raise `POPULATION`.
- Each run's `summary.json` has `audit_fresh_photons`: police violation rate, error by
  photon count and ambient level, and the time-shift test.
- Comparing `rule-s4-seed0` with `rule-s4-seed0-nopolice` shows what the police changes.

Baseline on the same randomized validation photons (old circuits, trained at 64 fixed):
best old circuit 0.559 m MAE, police violations 11%; hand rule 2.25 m.
