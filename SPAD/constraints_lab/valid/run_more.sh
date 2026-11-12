#!/bin/sh
# Valid-bit track: second seed of the main result (run C) and its ROC. Run from SPAD/.
PY=../.venv/bin/python
SLOT="$PY -m constraints_lab.slot --"
RUNS=runs/2026-11-11_constraints-lab/valid
FINAL=runs/2026-11-10_kaggle-t4_batch3_fused-larger-search/random-s4-seed0/circuit.json
$SLOT $PY -m constraints_lab.valid.search --objective accuracy --init-circuit $FINAL \
  --out $RUNS/accuracy-valid-w20-rangelim1-seed1 --valid-weight 20 --range-tolerance .01 --residual-min-bin 48 \
  --accuracy-tolerance .03 --generations 150 --population 128 --search-rays 2048 --background-rays 4096 \
  --validate-every 10 --seed 1 --threads 1 > $RUNS/accuracy-valid-w20-rangelim1-seed1.log 2>&1
$SLOT $PY -m constraints_lab.valid.roc --out $RUNS/roc_more --circuits \
  accuracy-valid-rangelim-seed1=$RUNS/accuracy-valid-w20-rangelim1-seed1/circuit.json \
  area-valid-search-end=$RUNS/area-valid-slack2-seed0/search_end_circuit.json > $RUNS/roc_more.log 2>&1
$SLOT $PY -m constraints_lab.valid.verilog_valid $RUNS/accuracy-valid-w20-rangelim1-seed0/circuit.json 'conf>=14' 'conf>=6' --verify \
  --out $RUNS/readout_synth/accuracy-valid-rangelim-seed0.json > $RUNS/readout_synth_rangelim.log 2>&1
echo more done
