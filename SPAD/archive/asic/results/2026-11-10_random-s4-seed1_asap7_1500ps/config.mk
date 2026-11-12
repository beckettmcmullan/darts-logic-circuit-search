# OpenROAD-flow-scripts configuration: one photon-stream core on ASAP7.
# Paths are inside the Docker container, where SPAD/asic is mounted at /work.
# Settings follow the ORFS ASAP7 example (designs/asap7/gcd), with lower utilization:
# the core is tiny (~250 cells) and its 24 pins need room on the edge.
export PLATFORM          = asap7
export DESIGN_NAME       = photon_core
export DESIGN_NICKNAME   = photon_core

export VERILOG_FILES     = /work/designs/photon_core/photon_core.v
export SDC_FILE          = /work/designs/photon_core/constraint.sdc

export CORE_UTILIZATION  = 45
export CORE_ASPECT_RATIO = 1
export CORE_MARGIN       = 0.5
export PLACE_DENSITY     = 0.6
export GPL_PLACE_IOS     = 1
