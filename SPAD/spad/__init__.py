"""SPAD photon-stream range core: data, gate models, training, hardware and evaluation.

Subpackages, in pipeline order: dataset (download and label real SPAD captures),
core (the gate-network model and its integer simulators), training (gradient
phase then exact search), hardware (area, timing, Verilog, Yosys). See README.md
in this folder for the data flow and the command line entry points.

Time bins are 750 ps wide. One bin is about 0.1124 m of range
(see spad.dataset.prepare.BIN_METERS).
"""
from pathlib import Path

# The SPAD project folder; data/ and runs/ live here.
ROOT = Path(__file__).resolve().parents[1]
