"""Hardware side of the SPAD project.

synthesis/ turns a trained circuit.json into Verilog, checks it against the Python
simulator, maps it to ASAP7 cells with Yosys, and estimates area and timing. The
OpenROAD layout flow (run_flow.sh, designs/, results/) lives next to it in this folder.
"""
from pathlib import Path

# The SPAD folder, one level above each circuit folder. data/ and runs/ live there,
# shared by both circuits.
ROOT = Path(__file__).resolve().parents[2]
