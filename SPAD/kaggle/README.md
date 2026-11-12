# Training on Kaggle (T4 x2)

Kaggle runs the search only. Synthesis and held-out scoring stay on your machine.

## 1. Build the bundle

```sh
.venv/bin/python SPAD/kaggle/pack.py
```

This writes `SPAD/kaggle/dist/spad-stream-design.zip`. It holds the code, `costs.json`
and captures 1-6, and it refuses captures 7-10 so that a cloud run cannot see them.
Rebuild it whenever the code changes.

## 2. Upload it

On Kaggle, choose **Datasets > New Dataset**, upload the zip, and keep it **Private**.
The data is CC BY-NC-SA 4.0, so keep the dataset's attribution and terms.

## 3. Run the notebook

1. Import `SPAD/kaggle/train.ipynb` as a new notebook.
2. Attach the dataset under **Input**.
3. Set **Accelerator** to **GPU T4 x2**.
4. Use **Save Version > Save & Run All**, which keeps running with the browser closed.

The notebook stops if CPU and CUDA disagree, then benchmarks before training.
`SESSION_SECONDS` stops work cleanly below the session limit. Check Kaggle's current
limits, because published figures disagree (9-12 hours per session, about 30 per week).

Read the benchmark output on the first run. If larger batches do not raise
`rays_per_second`, lower `BATCH`. If `circuits_per_second` is still rising at the
largest population, raise `POPULATION`.

## 4. Continue an unfinished sweep

Attach the previous version's output as an input, set `PREVIOUS` to its `runs` folder,
and run again. Finished jobs are skipped and unfinished jobs resume from `state.pt`.

## 5. Bring results back

Download `spad_runs.zip`, unzip it into `SPAD/runs/<date>_kaggle-t4_<what>/` (add a README.md describing the batch) (keep the zip there too), then synthesize:

```sh
cd SPAD && ../.venv/bin/python -m spad.hardware.synth runs/<date>_kaggle-t4_<what>/*/circuit.json --out runs/<date>_kaggle-t4_<what>/synthesis.json
```

Run `python -m spad.evaluation.final_eval` only after the design is frozen. It writes one result and refuses to overwrite it.
