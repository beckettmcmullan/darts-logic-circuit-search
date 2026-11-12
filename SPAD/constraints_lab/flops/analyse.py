"""Part 1: where the flip-flops and the logic that serves them go, for reference and batch-3 circuits.

For every circuit: standard audit, real synthesis (area, cells, flops, flop cell area), which state
bits and confidence flags are live, register activity on validation photons, and synthesis with
registers cut out (see common.cut_verilog). For the three reference circuits also: accuracy with
each live state bit forced to 0, and with a 3- or 2-bit confidence counter (no retraining).

Run (from SPAD/):
  ../.venv/bin/python -m constraints_lab.slot -- ../.venv/bin/python -m constraints_lab.flops.analyse
"""
import copy
import json
from pathlib import Path

import torch

from spad import ROOT
from spad.core.stream_model import StreamConfig, pack_circuit
from spad.hardware.area_model import usage, probe_photons, CONFIDENCE_FLAGS
from spad.core.stream_model import input_names
from constraints_lab.flops.common import (CONDITIONS, allow_small_counter, cut_verilog, load_circuit, load_data,
                                          parity, register_activity, short_audit, synth, synth_circuit)

BATCH3 = ROOT/"runs/2026-11-10_kaggle-t4_batch3_fused-larger-search"
AREA = ROOT/"runs/2026-11-11_local-cpu_area-objective"
REFERENCES = {
    "final_design": BATCH3/"random-s4-seed0/circuit.json",
    "area_optimized": AREA/"final-design-tol5/circuit.json",
    "search_end_no_recheck": AREA/"final-design-tol5_no-recheck/search_end_circuit.json",
}
OTHERS = {name: BATCH3/name/"circuit.json" for name in
          ("random-s2-seed0", "rule-s0-seed0", "random-s4-seed1", "random-s4-seed0-nopolice",
           "rule-s4-seed0", "rule-s4-seed1", "rule-s4-seed0-nopolice")}
OUT = ROOT/"runs/2026-11-11_constraints-lab/flops/analysis"


def liveness(circuit):
    c = StreamConfig(**circuit["config"])
    inputs, codes = pack_circuit(circuit)
    features = usage(c, inputs[None], codes[None], probe_photons())[0]
    from spad.hardware.area_model import feature_names
    names = feature_names(c)
    get = lambda n: float(features[names.index(n)])
    flags = [n for n in CONFIDENCE_FLAGS if get(f"flag_{n}")]
    return {"live_state_bits_model": int(get("state_flops")), "counter_read": bool(get("confidence_counter")),
            "confidence_flags_read": flags}


def kill_state(circuit, bits):
    """Force the next-value gate of each state bit in `bits` to constant 0 (the bit stays 0)."""
    out = copy.deepcopy(circuit)
    const0 = out["inputs"].index("const0")
    for i in bits:
        out["layers"][-1]["inputs"][i] = [const0, const0]
        out["layers"][-1]["truth_tables"][i] = [0, 0, 0, 0]
    return out


def with_counter(circuit, bits):
    out = copy.deepcopy(circuit)
    out["config"]["conf_bits"] = bits
    return out


def main():
    torch.set_num_threads(1)
    OUT.mkdir(parents=True, exist_ok=True)
    data = load_data()
    from spad.training.train_stream import Validator
    train, _, validation, police, _ = data
    validator = Validator(train, validation, CONDITIONS, 3, police, seed=1234)
    audit = lambda c: short_audit(validator.audit(c))
    mae = lambda c: validator(c)["mae_m"]
    sample = validator.photons[:6000]
    results = {}
    for name, path in {**REFERENCES, **OTHERS}.items():
        circuit = load_circuit(path)
        c = StreamConfig(**circuit["config"])
        row = {"path": str(path.relative_to(ROOT)), "state_bits_configured": c.state_bits}
        row["audit"] = audit(circuit)
        row["synth"] = full = synth_circuit(circuit)
        row.update(liveness(circuit))
        row["activity"] = register_activity(circuit, sample)
        cuts = {}
        for i in range(c.state_bits):
            cut = synth(cut_verilog(circuit, drop_state=[i]))
            cuts[f"state{i}"] = {"area_saved": round(full["area"] - cut["area"], 3), "flops_saved": full["flops"] - cut["flops"]}
        if c.state_bits:
            cut = synth(cut_verilog(circuit, drop_state=range(c.state_bits)))
            cuts["all_state"] = {"area_saved": round(full["area"] - cut["area"], 3), "flops_saved": full["flops"] - cut["flops"]}
        cut = synth(cut_verilog(circuit, drop_conf=True))
        cuts["confidence_counter"] = {"area_saved": round(full["area"] - cut["area"], 3), "flops_saved": full["flops"] - cut["flops"]}
        cut = synth(cut_verilog(circuit, no_step=True))
        cuts["candidate_stepper"] = {"area_saved": round(full["area"] - cut["area"], 3), "flops_saved": full["flops"] - cut["flops"]}
        cut = synth(cut_verilog(circuit, open_all=True))
        cuts["all_registers_open"] = {"area_saved": round(full["area"] - cut["area"], 3), "flops_saved": full["flops"] - cut["flops"],
                                      "per_flop_overhead_beyond_cell": round((full["area"] - cut["area"] - full["flop_area"]) / max(full["flops"], 1), 4)}
        row["cuts"] = cuts
        # Live state bits by synthesis: cutting a live bit removes at least its own flop.
        row["live_state_bits_synth"] = [i for i in range(c.state_bits) if cuts[f"state{i}"]["flops_saved"] >= 1]
        if name in REFERENCES:
            row["state_bit_ablation_mae"] = {f"state{i}": round(mae(kill_state(circuit, [i])), 4) for i in range(c.state_bits)}
            row["state_bit_ablation_mae"]["all"] = round(mae(kill_state(circuit, range(c.state_bits))), 4)
            allow_small_counter()
            for bits in (3, 2):
                small = with_counter(circuit, bits)
                row[f"conf_bits_{bits}_no_retrain"] = {"audit": audit(small), "synth": synth_circuit(small),
                                                      "parity_mismatches": parity(small)}
        results[name] = row
        print(name, json.dumps({k: row[k] for k in ("synth", "live_state_bits_synth", "confidence_flags_read")}),
              row["audit"]["mae_m"], flush=True)
        (OUT/"analysis.json").write_text(json.dumps(results, indent=2) + "\n")


if __name__ == "__main__":
    main()
