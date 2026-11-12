#!/usr/bin/env bash
# Open the OpenROAD GUI (or KLayout) from the ORFS Docker image through XQuartz.
# One-time setup (already done): XQuartz installed, network clients allowed, indirect GLX on.
#
# Usage (from SPAD/):
#   asic/open_gui.sh                 OpenROAD GUI on the latest run in asic/flow
#   asic/open_gui.sh klayout FILE    KLayout on a GDS file under SPAD/asic, e.g.
#                                    asic/open_gui.sh klayout results/2026-11-10_final_batch3-random-s4-seed0_asap7_1500ps/6_final.gds
set -euo pipefail
ASIC="$(cd "$(dirname "$0")" && pwd)"
XHOST=/opt/X11/bin/xhost
export DISPLAY=:0

# Start XQuartz if it is not running, and wait for it.
if ! pgrep -qf "Xquartz :0"; then
  open -a XQuartz
  for _ in $(seq 20); do pgrep -qf "Xquartz :0" && break; sleep 1; done
  sleep 2
fi

# Allow windows from this Mac only (the container arrives as localhost), and remove
# that permission again however the script ends.
"$XHOST" +127.0.0.1 > /dev/null
"$XHOST" +localhost > /dev/null
trap '"$XHOST" -127.0.0.1 > /dev/null; "$XHOST" -localhost > /dev/null' EXIT

RUN=(docker run --rm -it --platform linux/amd64
     -e DISPLAY=host.docker.internal:0 -e QT_X11_NO_MITSHM=1 -e LIBGL_ALWAYS_INDIRECT=1
     -v "$ASIC":/work openroad/orfs:latest)

if [ "${1:-}" = "klayout" ]; then
  "${RUN[@]}" klayout -l /OpenROAD-flow-scripts/flow/platforms/asap7/KLayout/asap7.lyp "/work/${2:?give a GDS path under SPAD/asic}"
else
  "${RUN[@]}" bash -c "cd /OpenROAD-flow-scripts && source ./env.sh > /dev/null && cd flow &&
    make DESIGN_CONFIG=/work/designs/photon_core/config.mk WORK_HOME=/work/flow gui_final"
fi
