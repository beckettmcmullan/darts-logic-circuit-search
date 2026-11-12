#!/bin/sh
# The four search runs of the settle track, one at a time, each through the CPU slot wrapper. Run from SPAD/.
set -e
PY=../.venv/bin/python
OUT=runs/2026-11-11_constraints-lab/settle
START=runs/2026-11-10_kaggle-t4_batch3_fused-larger-search/random-s4-seed0/circuit.json
COMMON="--init-circuit $START --threads 1 --synth-workers 1 --compile-search default --population 192 --search-rays 4096 --seed 0"
run() { name=$1; shift; mkdir -p $OUT/$name; $PY -m constraints_lab.slot -- $PY -m constraints_lab.settle.search --out $OUT/$name $COMMON "$@" > $OUT/$name.log 2>&1; }
# Done first (20 min): run area_settle-limit --objective area --settle-limit --settle-tolerance 0.05 --generations 300 --synth-candidates 2
# The plain accuracy loop (no --recheck) drifted to 0.445 m validation MAE by generation 40 and was stopped;
# its partial log is accuracy_settle-w1_no-recheck.log.
run accuracy_settle-w1    --objective accuracy --settle-weight 1 --area-cap --recheck --generations 200
run accuracy_control      --objective accuracy --settle-weight 0 --area-cap --recheck --generations 200
run area_control          --objective area --generations 300 --synth-candidates 2
# Second seed of the accuracy pair (added after the first pair finished).
COMMON="$(echo $COMMON | sed 's/--seed 0/--seed 1/')"
run accuracy_settle-w1_seed1 --objective accuracy --settle-weight 1 --area-cap --recheck --generations 200
run accuracy_control_seed1   --objective accuracy --settle-weight 0 --area-cap --recheck --generations 200
