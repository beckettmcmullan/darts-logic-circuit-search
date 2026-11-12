#!/bin/sh
# Valid-bit track, after the searches: readout synthesis + parity, shadow counter, final ROC. Run from SPAD/.
PY=../.venv/bin/python
SLOT="$PY -m constraints_lab.slot --"
RUNS=runs/2026-11-11_constraints-lab/valid
FINAL=runs/2026-11-10_kaggle-t4_batch3_fused-larger-search/random-s4-seed0/circuit.json
TOL5=runs/2026-11-11_local-cpu_area-objective/final-design-tol5/circuit.json
END=runs/2026-11-11_local-cpu_area-objective/final-design-tol5_no-recheck/search_end_circuit.json

# C: accuracy objective with the range loss held as a hard limit (within 1% of the start on the same pixels).
$SLOT $PY -m constraints_lab.valid.search --objective accuracy --init-circuit $FINAL \
  --out $RUNS/accuracy-valid-w20-rangelim1-seed0 --valid-weight 20 --range-tolerance .01 --residual-min-bin 48 \
  --accuracy-tolerance .03 --generations 150 --population 128 --search-rays 2048 --background-rays 4096 \
  --validate-every 10 --seed 0 --threads 1 > $RUNS/accuracy-valid-w20-rangelim1-seed0.log 2>&1

$SLOT $PY -m constraints_lab.valid.verilog_valid $FINAL 'conf>=6' 'conf>=8' 'conf>=15' --verify --out $RUNS/readout_synth/final-design.json > $RUNS/readout_synth_final.log 2>&1
$SLOT $PY -m constraints_lab.valid.verilog_valid $TOL5 'conf>=6' 'conf>=8' 'conf>=15' --verify --out $RUNS/readout_synth/area-tol5.json > $RUNS/readout_synth_tol5.log 2>&1
$SLOT $PY -m constraints_lab.valid.verilog_valid $END 'conf>=6' '~state0' --verify --out $RUNS/readout_synth/search-end.json > $RUNS/readout_synth_end.log 2>&1
$SLOT $PY -m constraints_lab.valid.shadow --bits 5 6 7 --circuits final-design=$FINAL area-tol5=$TOL5 > $RUNS/shadow.log 2>&1
$SLOT $PY -m constraints_lab.valid.roc --out $RUNS/roc_all --circuits final-design=$FINAL area-tol5=$TOL5 search-end-20um2=$END \
  accuracy-valid-g10=$RUNS/accuracy-valid-w20-seed0/gen10_circuit.json accuracy-valid-g120=$RUNS/accuracy-valid-w20-seed0/gen120_circuit.json area-valid=$RUNS/area-valid-slack2-seed0/circuit.json \
  accuracy-valid-rangelim=$RUNS/accuracy-valid-w20-rangelim1-seed0/circuit.json > $RUNS/roc_all.log 2>&1
echo after done
