#!/usr/bin/env bash
# Run OpenROAD-flow-scripts (ORFS) on the photon core, inside the ORFS Docker image.
# The flow goes: synthesis -> floorplan -> placement -> clock tree -> routing -> GDSII.
#
# Usage (from SPAD/accuracy-focused/):  asic/run_flow.sh [make target]
#   With no target the whole flow runs. A target such as "synth", "floorplan" or
#   "clean_all" runs only that step (it is passed straight to ORFS's make).
#
# Environment variables (all optional):
#   ORFS_IMAGE     Docker image to use           (default: the 2026-11-10 image the saved layout used)
#   ORFS_CPUS      CPU cap for the container     (default: no cap)
#   ORFS_PLATFORM  flag passed to "docker run"   (default: --platform linux/amd64)
#
# Inputs:  asic/designs/photon_core/{config.mk,constraint.sdc,photon_core.v}
# Outputs: asic/flow/{results,reports,logs}/asap7/photon_core/base/
#          (asic/flow/ is scratch and not tracked in git; copy what you want to keep
#          into asic/layout/.)
set -euo pipefail

# Absolute path of the folder holding this script (asic/), whatever the caller's cwd.
ASIC="$(cd "$(dirname "$0")" && pwd)"
IMAGE="${ORFS_IMAGE:-openroad/orfs@sha256:3ec2759c9be0fe43556ac2ce6894a7a7dfb44006c6211bbdc5beb3e0f09d494f}"
PLATFORM_FLAG="${ORFS_PLATFORM:---platform linux/amd64}"

# asic/ is mounted at /work in the container. That is why config.mk refers to
# /work/designs/... and why results come back to asic/flow on the host.
# $PLATFORM_FLAG is deliberately unquoted so "--platform linux/amd64" splits into two words.
# The quoted script below is run by bash inside the container; ${1:-} expands here, on the host.
docker run --rm ${ORFS_CPUS:+--cpus $ORFS_CPUS} $PLATFORM_FLAG -v "$ASIC":/work "$IMAGE" bash -c "
  cd /OpenROAD-flow-scripts && source ./env.sh > /dev/null &&
  cd flow &&
  make DESIGN_CONFIG=/work/designs/photon_core/config.mk WORK_HOME=/work/flow ${1:-}
"
