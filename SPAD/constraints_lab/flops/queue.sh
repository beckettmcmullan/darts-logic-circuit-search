#!/bin/zsh
# Runs the flops track's searches one after another, each through the CPU slot wrapper.
# From SPAD/:  zsh constraints_lab/flops/queue.sh "<name> <args>" ...
# Each argument is a run name followed by search.py options; logs go next to the run folder.
cd "$(dirname "$0")/../.."
ROOT=runs/2026-11-11_constraints-lab/flops
for spec in "$@"; do
  name=${spec%% *}
  opts=${spec#* }
  [[ "$opts" == "$name" ]] && opts=""
  mkdir -p $ROOT/$name
  echo "start $name $(date +%H:%M:%S)"
  ../.venv/bin/python -m constraints_lab.slot -- ../.venv/bin/python -m constraints_lab.flops.search \
      --out $ROOT/$name --threads 1 ${=opts} > $ROOT/$name.log 2>&1
  echo "done $name exit $? $(date +%H:%M:%S)"
done
