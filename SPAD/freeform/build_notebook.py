"""Write train_free.ipynb with the model and trainer embedded, so the notebook is self-contained.

It needs only the existing private `spad-stream-design` Kaggle dataset (for the
photon data and the shared data-loading code); nothing new has to be uploaded.
Run from SPAD/ after changing free_model.py or train_free.py:
  ../.venv/bin/python freeform/build_notebook.py
"""
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
EMBED = ("__init__.py", "free_model.py", "train_free.py", "test_free.py")


def cell(kind, text):
    lines = text.strip("\n").splitlines(keepends=True)
    body = {"cell_type": kind, "metadata": {}, "source": lines}
    return body if kind == "markdown" else {**body, "outputs": [], "execution_count": None}


INTRO = """
# SPAD free-form core: no assumed architecture (T4 x2)

The other SPAD runs give the learner a fixed datapath (candidate register, comparator, confidence
counter) and learn a 48-gate controller. This run assumes none of it: the circuit sees each photon's
raw 10-bit arrival time plus its own flip-flops, and every gate and every wire is learned.

Attach the private **spad-stream-design** dataset (the same one as the earlier batches), choose
**GPU T4 x2**, then **Save Version > Save & Run All**. Download `freeform_runs.zip` when it finishes.

Training aids (curriculum, scoring the answer after photons 16/32/64/128, a per-bit loss and
larger search samples) are on by default; three jobs switch them off to measure what they add.
`plain-seed0` matches the first local trial's method.

Expect this to be much harder than the controller search. Each run prints a reference line: the
error of a circuit that ignores the photons. A run only means something if it beats that and passes
the time-shift test in its summary.
"""

SETUP = """
import glob, json, os, shutil, subprocess, sys

matches = glob.glob('/kaggle/input/**/code/spad/dataset/photons.py', recursive=True)
assert matches, 'Attach the spad-stream-design dataset'
BUNDLE = matches[0].rsplit('/code/', 1)[0]
WORK = '/kaggle/working'
CODE, DATA, RUNS = f'{WORK}/code', f'{BUNDLE}/data', f'{WORK}/freeform_runs'
SESSION_SECONDS = 8 * 3600   # stay safely below Kaggle's session limit

shutil.copytree(f'{BUNDLE}/code', CODE, dirs_exist_ok=True)
os.makedirs(f'{CODE}/freeform', exist_ok=True)
os.makedirs(RUNS, exist_ok=True)
splits = {k: v['split'] for k, v in json.load(open(f'{DATA}/processed/metadata.json'))['captures'].items()}
held_out = [k for k, v in splits.items() if v not in ('train', 'architecture', 'validation')]
assert not held_out, f'Held-out captures must not be here: {held_out}'
print(BUNDLE, len(splits), 'captures')
"""

GPU = """
import torch
assert torch.cuda.is_available(), 'Choose GPU T4 x2 under Accelerator'
GPUS = torch.cuda.device_count()
print(torch.__version__, GPUS, [torch.cuda.get_device_name(i) for i in range(GPUS)])
subprocess.run([sys.executable, '-m', 'unittest', 'freeform.test_free', '-v'], cwd=CODE, check=True)
"""

JOBS = """
# name, then train_free.py arguments. Two jobs run at once, one per GPU.
JOBS = [
    ('aids-seed0',          '--seed 0'),                      # curriculum + readouts + bit loss + larger samples
    ('aids-seed1',          '--seed 1'),
    ('aids-wide-seed0',     '--seed 0 --layers 6 --width 64 --state-bits 48'),
    ('no-curriculum-seed0', '--seed 0 --curriculum 0'),        # each aid switched off once, to see what it adds
    ('final-only-seed0',    '--seed 0 --readouts "" --bit-weight 0'),
    ('plain-seed0',         '--seed 0 --curriculum 0 --readouts "" --bit-weight 0 --resample-every 1 --search-rays 2048'),
]
STEPS, BATCH, GENERATIONS, POPULATION, SEARCH_RAYS = 1500, 512, 4000, 512, 4096
PER_JOB_SECONDS = int(SESSION_SECONDS * GPUS / len(JOBS) * .9)   # every job gets a fair share of the session

import queue, shlex, threading
todo = queue.Queue()
for job in JOBS:
    todo.put(job)

def worker(gpu):
    while True:
        try:
            name, flags = todo.get_nowait()
        except queue.Empty:
            return
        if os.path.exists(f'{RUNS}/{name}/summary.json'):
            continue
        os.makedirs(f'{RUNS}/{name}', exist_ok=True)
        command = [sys.executable, '-m', 'freeform.train_free', '--data', DATA, '--out', f'{RUNS}/{name}',
                   '--steps', str(STEPS), '--batch-size', str(BATCH), '--generations', str(GENERATIONS),
                   '--population', str(POPULATION), '--search-rays', str(SEARCH_RAYS),
                   '--max-seconds', str(PER_JOB_SECONDS), *shlex.split(flags)]
        with open(f'{RUNS}/{name}/log.txt', 'w') as log:
            done = subprocess.run(command, cwd=CODE, stdout=log, stderr=subprocess.STDOUT,
                                  env={**os.environ, 'CUDA_VISIBLE_DEVICES': str(gpu)})
        tail = open(f'{RUNS}/{name}/log.txt').read().splitlines()[-3:]
        print(f'[gpu {gpu}] {name} exit {done.returncode}:', *tail, sep='\\n   ', flush=True)

threads = [threading.Thread(target=worker, args=(gpu,)) for gpu in range(GPUS)]
[t.start() for t in threads]
[t.join() for t in threads]
"""

REPORT = """
rows = []
for path in glob.glob(f'{RUNS}/*/summary.json'):
    s = json.load(open(path))
    shift = s['audit']['time_shift_test']
    rows.append((s['validation']['mae_m'], os.path.basename(os.path.dirname(path)), s['validation']['median_m'],
                 s['reference_ignoring_photons']['mae_m'], shift['moves_with_photons_within_8_bins'],
                 s['gates']['live_gates'], s['gates']['flip_flops_used'], s['seconds']))
print(f"{'run':20s} {'MAE m':>7s} {'median':>7s} {'ignore-photons MAE':>19s} {'follows a time shift':>21s} {'gates':>6s} {'flops':>6s} {'min':>6s}")
for mae, name, median, ref, follows, gates, flops, seconds in sorted(rows):
    print(f'{name:20s} {mae:7.3f} {median:7.3f} {ref:19.3f} {follows:21.1%} {gates:6d} {flops:6d} {seconds/60:6.1f}')
print('For comparison, the fixed-datapath final design (10 Nov): MAE 0.363 m, median 0.151 m.')
shutil.make_archive(f'{WORK}/freeform_runs', 'zip', RUNS)
"""


def main():
    cells = [cell("markdown", INTRO), cell("code", SETUP),
             cell("markdown", "The model, trainer and tests, written into the working folder. "
                              "These cells are copies of the files in `SPAD/freeform/`.")]
    for name in EMBED:
        cells.append(cell("code", f"%%writefile /kaggle/working/code/freeform/{name}\n" + (HERE/name).read_text()))
    cells += [cell("markdown", "The three implementations (training pass, integer circuit, bit-packed search) must agree exactly on this GPU."),
              cell("code", GPU), cell("code", JOBS), cell("code", REPORT)]
    notebook = {"cells": cells, "nbformat": 4, "nbformat_minor": 5,
                "metadata": {"kernelspec": {"display_name": "Python 3", "language": "python", "name": "python3"},
                             "language_info": {"name": "python"}}}
    (HERE/"train_free.ipynb").write_text(json.dumps(notebook, indent=1) + "\n")
    print(f"wrote {HERE/'train_free.ipynb'} ({len(cells)} cells)")


if __name__ == "__main__":
    main()
