"""Run a job list across devices: independent jobs, one queue, safe to rerun.

Each GPU runs its own jobs through CUDA_VISIBLE_DEVICES, with no DataParallel.
A job with summary.json is skipped and any other job resumes from state.pt,
so rerunning this after a session ends continues the sweep.
"""
import argparse
import os
from pathlib import Path
import queue
import subprocess
import sys
import threading
import time

# Code root holding the spad package (SPAD locally, the copied bundle on Kaggle).
CODE_ROOT = Path(__file__).resolve().parents[1]
TRAIN = "spad.training.train_stream"


def parse_jobs(path):
    jobs = []
    for line in path.read_text().splitlines():
        if line.strip() and not line.startswith("#"):
            name, *arguments = line.split()
            jobs.append((name, arguments))
    return jobs


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--jobs", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--data", type=Path)
    parser.add_argument("--gpus", type=int, default=0, help="Number of GPUs; 0 runs on CPU")
    parser.add_argument("--workers-per-device", type=int, default=1)
    parser.add_argument("--cpu-workers", type=int, default=4)
    parser.add_argument("--threads", type=int, default=2)
    parser.add_argument("--max-seconds", type=float, default=0, help="Session limit for the whole launch")
    args, extra = parser.parse_known_args()
    args.out.mkdir(parents=True, exist_ok=True)
    started = time.monotonic()
    pending = queue.Queue()
    for name, arguments in parse_jobs(args.jobs):
        if (args.out/name/"summary.json").exists():
            print(f"skip {name}: finished", flush=True)
        else:
            pending.put((name, arguments))

    def worker(gpu):
        while True:
            try:
                name, arguments = pending.get_nowait()
            except queue.Empty:
                return
            remaining = args.max_seconds - (time.monotonic() - started) if args.max_seconds else 0
            if args.max_seconds and remaining < 60:
                print(f"left for next session: {name}", flush=True)
                continue
            command = [sys.executable, "-m", TRAIN, "--out", str(args.out/name), "--resume",
                       "--threads", str(args.threads), "--device", "cpu" if gpu is None else "cuda",
                       *(["--data", str(args.data)] if args.data else []),
                       *(["--max-seconds", str(int(remaining))] if args.max_seconds else []),
                       *extra, *arguments]
            environment = dict(os.environ, PYTHONDONTWRITEBYTECODE="1")
            if gpu is not None:
                environment["CUDA_VISIBLE_DEVICES"] = str(gpu)
            print(f"start {name} on {'cpu' if gpu is None else f'gpu {gpu}'}", flush=True)
            with (args.out/f"{name}.log").open("a") as log:
                code = subprocess.run(command, stdout=log, stderr=subprocess.STDOUT, env=environment,
                                      cwd=CODE_ROOT).returncode
            done = (args.out/name/"summary.json").exists()
            print(f"{name}: {'finished' if done else 'paused' if code == 0 else f'FAILED, exit {code}'}", flush=True)

    slots = ([gpu for gpu in range(args.gpus) for _ in range(args.workers_per_device)]
             if args.gpus else [None]*args.cpu_workers)
    threads = [threading.Thread(target=worker, args=(gpu,)) for gpu in slots]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    finished = sum((args.out/name/"summary.json").exists() for name, _ in parse_jobs(args.jobs))
    print(f"{finished} of {len(parse_jobs(args.jobs))} jobs finished", flush=True)


if __name__ == "__main__":
    main()
