"""Tail and audit of a circuit, or of the search-end circuit in a train_stream state.pt (seed 1234)."""
import json
import sys

import torch

from spad import ROOT
from spad.core.stream_model import simulate_stream
from spad.hardware.synth import synthesize
from spad.hardware.verilog import stream_verilog
from spad.training.train_stream import Validator

from constraints_lab.tail.common import CONDITIONS, setup, tail_stats


def main():
    torch.set_num_threads(1)
    path = sys.argv[1]
    if path.endswith(".pt"):
        circuit = torch.load(path, map_location="cpu", weights_only=False)["run"]["search_circuit"]
    else:
        circuit = json.loads(open(path).read())
    train, routing, validation, police = setup()
    validator = Validator(train, validation[:2], CONDITIONS, 3, police, seed=1234)
    audit = validator.audit(circuit)
    prediction = simulate_stream(circuit, validator.photons).float() - validator.offset(circuit)
    synth = synthesize(stream_verilog(circuit), "photon_core", ROOT/"data")
    print(json.dumps({"tail": tail_stats(prediction - validator.targets.float()),
                      "synth": {k: v for k, v in synth.items() if k != "report"},
                      "recall_3": audit["overall"]["recall_3_bins"],
                      "offsets": [round(audit[k]["median_signed_bins"], 1) for k in audit if k.startswith("photons_")]}))


if __name__ == "__main__":
    main()
