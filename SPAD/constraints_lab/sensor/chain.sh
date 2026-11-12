#!/bin/zsh
# Sequential search runs for the sensor track (one job at a time, through the slot wrapper).
cd "$(dirname $0)/../.."
R=runs/2026-11-11_constraints-lab/sensor
P=../.venv/bin/python
run() { name=$1; shift; mkdir -p $R/$name; echo "start $name $(date +%T)"; $P -m constraints_lab.slot -- $P -m constraints_lab.sensor.search --out $R/$name --threads 1 "$@" > $R/$name.log 2>&1; echo "end $name $(date +%T) rc=$?"; }
run acc-mix-s0 --objective accuracy --share .5 --generations 300 --seed 0
run acc-clean-s0 --objective accuracy --share 0 --generations 300 --seed 0
run area-mix-cleanlimit-s0 --objective area --share .5 --clean-limit --generations 200 --seed 0
run acc-mix-s1 --objective accuracy --share .5 --generations 300 --seed 1
