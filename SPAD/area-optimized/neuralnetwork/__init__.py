"""The neural network that learns the SPAD photon-stream range circuit.

Subpackages, in pipeline order: dataset (download and label real SPAD captures),
core (the gate-network model and its integer simulators), training (gradient
phase then exact search). The hardware side (Verilog, Yosys, area, timing) is the
asic.synthesis package in ../asic/synthesis/. See README.md in this folder for the
data flow and the command line entry points.

Time bins are 750 ps wide. One bin is about 0.1124 m of range
(see neuralnetwork.dataset.prepare.BIN_METERS).
"""
from pathlib import Path

# The SPAD folder, one level above each circuit folder. data/ and runs/ live there,
# shared by both circuits.
ROOT = Path(__file__).resolve().parents[2]
