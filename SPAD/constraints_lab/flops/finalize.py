"""Standard numbers and live registers for the selected search circuits (one process, slot-wrapped)."""
import json
import torch
from spad import ROOT
from constraints_lab.flops.common import (CONDITIONS, allow_small_counter, load_circuit, load_data, parity,
                                          short_audit, synth_circuit)
from constraints_lab.flops.structure import structure
from spad.training.train_stream import Validator

torch.set_num_threads(1)
allow_small_counter()
F = ROOT/"runs/2026-11-11_constraints-lab/flops"
circuits = {
    "base-s0 chosen": F/"base-s0/chosen_circuit.json",
    "cap2-s0 best": F/"cap2-s0/best_mae_circuit.json",
    "cap0-s0 best": F/"cap0-s0/best_mae_circuit.json",
    "w2-s0 chosen (g40)": F/"w2-s0/chosen_circuit.json",
    "w2-s0 search end (g110)": F/"w2-s0/trace/gen0110.json",
    "conf3-s0 best (g40)": F/"conf3-s0/best_mae_circuit.json",
    "conf3-s0 search end (g90)": F/"conf3-s0/trace/gen0090.json",
}
train, _, validation, police, _ = load_data()
v = Validator(train, validation, CONDITIONS, 3, police, seed=1234)
out = {}
for name, path in circuits.items():
    c = load_circuit(path)
    st = structure(c)
    row = {"audit": short_audit(v.audit(c)), "synth": synth_circuit(c), "parity": parity(c),
           "live_state_bits": st["live_state_bits"], "confidence_flags_read": st["confidence_flags_read"],
           "conf_bits": c["config"]["conf_bits"]}
    out[name] = row
    print(name, json.dumps(row), flush=True)
(F/"final_numbers.json").write_text(json.dumps(out, indent=2) + "\n")
