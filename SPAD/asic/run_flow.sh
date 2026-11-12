#!/usr/bin/env bash
# Run OpenROAD-flow-scripts (synthesis -> floorplan -> placement -> clock tree ->
# routing -> GDSII) on the photon core, inside the ORFS Docker image.
# Usage (from SPAD/):  asic/run_flow.sh [make target, default: everything]
# Results land in SPAD/asic/flow/{results,reports,logs}/asap7/photon_core/base/.
set -euo pipefail
ASIC="$(cd "$(dirname "$0")" && pwd)"
IMAGE="${ORFS_IMAGE:-openroad/orfs:latest}"
PLATFORM_FLAG="${ORFS_PLATFORM:---platform linux/amd64}"
docker run --rm $PLATFORM_FLAG -v "$ASIC":/work "$IMAGE" bash -c "
  cd /OpenROAD-flow-scripts && source ./env.sh > /dev/null &&
  cd flow &&
  make DESIGN_CONFIG=/work/designs/photon_core/config.mk WORK_HOME=/work/flow ${1:-}
"
