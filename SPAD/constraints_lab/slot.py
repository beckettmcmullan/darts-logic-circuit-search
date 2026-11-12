"""Run a command only when a CPU slot is free, so all tracks together stay under 80% of the machine.

Usage (from SPAD/):  ../.venv/bin/python -m constraints_lab.slot -- <command> [args...]

The machine has 10 cores; the budget is 8 busy cores. Slots = 8 minus the other heavy jobs
already running (the free-form lab). The wrapper waits for a slot, holds it while the command
runs (one thread per command), and passes through the command's exit code.
"""
import fcntl
import os
from pathlib import Path
import subprocess
import sys
import time

BUDGET = 8
FOLDER = Path(__file__).resolve().parent/".slots"


def other_heavy_jobs():
    listing = subprocess.run(["ps", "-A", "-o", "command"], capture_output=True, text=True).stdout
    return sum("freeform.lab" in line and "constraints_lab.slot" not in line for line in listing.splitlines())


def main():
    command = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else sys.argv[1:]
    if not command:
        sys.exit(__doc__)
    FOLDER.mkdir(exist_ok=True)
    waited = time.time()
    while True:
        for index in range(max(BUDGET - other_heavy_jobs(), 1)):
            handle = open(FOLDER/f"slot{index}.lock", "w")
            try:
                fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                handle.close()
                continue
            if time.time() - waited > 5:
                print(f"[slot] waited {time.time() - waited:.0f} s for a CPU slot", file=sys.stderr, flush=True)
            env = {**os.environ, "OMP_NUM_THREADS": "1", "MKL_NUM_THREADS": "1", "VECLIB_MAXIMUM_THREADS": "1"}
            sys.exit(subprocess.run(command, env=env).returncode)
        time.sleep(5)


if __name__ == "__main__":
    main()
