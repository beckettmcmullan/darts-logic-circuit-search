#!/bin/zsh
# Second chain: waits for the running control search, then evaluations and the remaining searches, one at a time.
cd "$(dirname $0)/../.."
R=runs/2026-11-11_constraints-lab/sensor
P=../.venv/bin/python
V=(clean jitter:1 jitter:2 jitter:4 pileup:2 pileup:4 pileup:8 mixpileup pileup:4+jitter:2 mix bits:0.01 bits:0.01@5)
while pgrep -f "sensor.search --out $R/acc-clean-s0" > /dev/null; do sleep 5; done
echo "end acc-clean-s0 $(date +%T)"
ev() { name=$1; shift; echo "start eval $name $(date +%T)"; $P -m constraints_lab.slot -- $P -m constraints_lab.sensor.evaluate --out $R/$name --variants $V "$@" > $R/$name.log 2>&1; echo "end eval $name $(date +%T) rc=$?"; }
run() { name=$1; shift; mkdir -p $R/$name; echo "start $name $(date +%T)"; $P -m constraints_lab.slot -- $P -m constraints_lab.sensor.search --out $R/$name --threads 1 "$@" > $R/$name.log 2>&1; echo "end $name $(date +%T) rc=$?"; }
ev eval-acc-s0 --circuit acc_mix_s0_selected=$R/acc-mix-s0/circuit.json --circuit acc_mix_s0_end=$R/acc-mix-s0/search_end_circuit.json --circuit acc_clean_s0_selected=$R/acc-clean-s0/circuit.json --circuit acc_clean_s0_end=$R/acc-clean-s0/search_end_circuit.json
run area-mix-cleanlimit-s0 --objective area --share .5 --clean-limit --generations 200 --seed 0
ev eval-area-s0 --no-references --circuit area_mix_s0_selected=$R/area-mix-cleanlimit-s0/circuit.json --circuit area_mix_s0_end=$R/area-mix-cleanlimit-s0/search_end_circuit.json
run acc-mix-cleanlimit-s1 --objective accuracy --share .5 --clean-limit --generations 300 --seed 1
ev eval-acc-s1 --no-references --circuit acc_mixcl_s1_selected=$R/acc-mix-cleanlimit-s1/circuit.json --circuit acc_mixcl_s1_end=$R/acc-mix-cleanlimit-s1/search_end_circuit.json
echo "chain2 done $(date +%T)"
