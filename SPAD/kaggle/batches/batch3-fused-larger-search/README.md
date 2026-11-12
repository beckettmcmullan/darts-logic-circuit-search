# Batch 3: fused gradient step + compiled search, larger search

| File | What it is |
|---|---|
| `spad-stream-design.zip` | Dataset bundle (code + design captures and scenes; no held-out data) |
| `train.ipynb` | Notebook. Writes `spad_runs_batch3.zip` |
| `jobs.txt` | The 8 jobs (same as batch 2; the three rule police jobs that crashed are fixed) |

## Steps
1. Kaggle: open the `spad-stream-design` dataset, **New Version**, upload `spad-stream-design.zip`. Keep it Private.
2. Import `train.ipynb`, attach the new dataset version, Accelerator **GPU T4 x2**.
3. **Save Version > Save & Run All**.
4. Download `spad_runs_batch3.zip` and unzip into `SPAD/runs/<date>_kaggle-t4_batch3-fused-larger-search/`
   and add a README.md describing the batch, like the other run folders.

## What changed since batch 2
- **Fused gradient step.** Same maths (checked against the old forward), roughly half the
  operations per photon, so far fewer GPU kernel launches. 2.1x faster on the M5 CPU.
- **Compiled exact search.** The bit-packed simulator's per-photon step is fused with
  `torch.compile`; results are bit-identical. About 55x the batch-1 search speed on the M5 CPU.
- **Automatic settings.** The benchmark cell times each `torch.compile` mode for the gradient
  step and the search on the T4, skips any that fail, and trains with the fastest.
  Its choice is saved in `benchmark_t4.json`.
- **Larger search:** population 512 (was 128), 1500 generations (was 600), 2048 search rays.
- **Fix:** a NaN answer no longer crashes the police on CUDA (the 3 crashed batch-2 jobs).
- **Fix:** training skips non-finite steps and rolls back if weights become non-finite.

GPU timings are not measured yet; the benchmark cell prints them first. If the 8 jobs do not
finish inside `SESSION_SECONDS` (8 h), unfinished jobs pause cleanly: rerun with `PREVIOUS`
set to the earlier output to resume them.
