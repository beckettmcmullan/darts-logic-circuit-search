"""Hardware side of the SPAD project.

synthesis/ turns a trained circuit.json into Verilog, checks it against the Python
simulator, maps it to ASAP7 cells with Yosys, and estimates area and timing. The
OpenROAD layout flow (run_flow.sh, designs/, results/) lives next to it in this folder.
"""
from pathlib import Path

# The SPAD project folder; data/ and runs/ live here.
ROOT = Path(__file__).resolve().parents[1]
