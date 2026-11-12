#!/bin/sh
# Valid-bit track: the searches, one job at a time, each through the CPU slot wrapper. Run from SPAD/.
set -e
PY=../.venv/bin/python
SLOT="$PY -m constraints_lab.slot --"
RUNS=runs/2026-11-11_constraints-lab/valid
FINAL=runs/2026-11-10_kaggle-t4_batch3_fused-larger-search/random-s4-seed0/circuit.json

# A: accuracy objective (fixed-area style: light area weight as in the standard search), valid term weight 20,
#    backgrounds uniform + residual_far; select the best valid bit with validation MAE within 3% of the start.
$SLOT $PY -m constraints_lab.valid.search --objective accuracy --init-circuit $FINAL \
  --out $RUNS/accuracy-valid-w20-seed0 --valid-weight 20 --residual-min-bin 48 --accuracy-tolerance .03 \
  --generations 150 --population 128 --search-rays 2048 --background-rays 4096 --validate-every 10 --seed 0 --threads 1 \
  > $RUNS/accuracy-valid-w20-seed0.log 2>&1

# B: area objective with the valid bit as a hard limit (detection may drop at most 2 points), from the final design.
$SLOT $PY -m constraints_lab.valid.search --objective area --init-circuit $FINAL \
  --out $RUNS/area-valid-slack2-seed0 --residual-min-bin 48 --valid-slack .02 --accuracy-tolerance .05 \
  --generations 150 --population 96 --search-rays 2048 --background-rays 4096 --validate-every 10 --seed 0 \
  --synth-workers 1 --threads 1 > $RUNS/area-valid-slack2-seed0.log 2>&1
echo chain done
