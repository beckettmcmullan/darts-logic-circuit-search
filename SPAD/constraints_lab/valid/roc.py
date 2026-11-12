"""Question 2: how well does existing state work as a valid bit, with no new hardware?

For each circuit: standard audit, then final confidence and state on real-return validation pixels
(the standard seed-1234 photons) and on three background-only sets, and the false-alarm /
detection rate of every no-new-logic readout, overall and by photon-count bucket. A repeat with
different photon draws measures repeatability.
"""
import argparse
import json
from pathlib import Path

import torch

from spad import ROOT
from spad.core.stream_model import pack_circuit, simulate_stream, StreamConfig
from spad.dataset.photons import sample_conditions

from constraints_lab.valid.common import (BUCKETS, CONDITIONS, REFERENCES, design_data, detection_at_limit,
                                          load_circuit, readouts, run_full, standard_validator,
                                          validation_backgrounds)
from constraints_lab.valid.sim import simulate_population_full


def evaluate(circuit, validator, backgrounds, real=None, limit=.01):
    """Valid-bit measure on given real and background photons. Returns a JSON-able dict."""
    photons, counts, targets = real if real is not None else (validator.photons, validator.counts, validator.targets)
    cand, conf, state = run_full(circuit, photons)
    offset = validator.offset(circuit)
    correct = ((cand.float() - offset - targets).abs() <= 3)
    real_bits = readouts(conf, state)
    result = {"offset_bins": offset, "confidence_histogram": {"real": torch.bincount(conf, minlength=16).tolist()}}
    bg_bits, bg_counts = {}, {}
    for name, (p, n) in backgrounds.items():
        _, c2, s2 = run_full(circuit, p)
        bg_bits[name], bg_counts[name] = readouts(c2, s2), n
        result["confidence_histogram"][name] = torch.bincount(c2, minlength=16).tolist()
    table = {}
    for key, bits in real_bits.items():
        row = {"detect": float(bits.float().mean()), "detect_and_correct": float((bits & correct).float().mean()),
               "correct_given_valid": float(correct[bits].float().mean()) if bits.any() else None}
        for name in bg_bits:
            row[f"fa_{name}"] = float(bg_bits[name][key].float().mean())
        buckets = {}
        for low, high in BUCKETS:
            keep = (counts >= low) & (counts < high)
            b = {"detect": float(bits[keep].float().mean())}
            for name in bg_bits:
                k2 = (bg_counts[name] >= low) & (bg_counts[name] < high)
                b[f"fa_{name}"] = float(bg_bits[name][key][k2].float().mean())
            buckets[f"{low}-{min(high, 256)}"] = b
        row["by_photons"] = buckets
        table[key] = row
    result["readouts"] = table
    result["detection_at_fa_limit"] = {name: dict(zip(("detect", "readout", "fa"),
                                                      detection_at_limit(real_bits, bg_bits[name], limit)))
                                       for name in bg_bits}
    # Limit must hold on both uniform and residual: use the max false-alarm rate of the two.
    best = (0., None, None)
    for k in real_bits:
        fa = max(table[k]["fa_uniform"], table[k]["fa_residual"])
        if fa <= limit and table[k]["detect"] > best[0]:
            best = (table[k]["detect"], k, fa)
    result["detection_at_fa_limit"]["uniform_and_residual"] = dict(zip(("detect", "readout", "fa"), best))
    result["correct_rate_all"] = float(correct.float().mean())
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=ROOT/"runs/2026-11-11_constraints-lab/valid/roc")
    parser.add_argument("--circuits", nargs="*", default=None, help="name=path pairs (default: the three references)")
    parser.add_argument("--no-synth", action="store_true")
    args = parser.parse_args()
    torch.set_num_threads(1)
    args.out.mkdir(parents=True, exist_ok=True)
    circuits = REFERENCES if not args.circuits else dict(x.split("=", 1) for x in args.circuits)
    train, routing, validation = design_data()
    validator = standard_validator(train, validation)
    backgrounds = validation_backgrounds(validation, seed=4321)
    repeat_bg = validation_backgrounds(validation, seed=999)
    g = torch.Generator().manual_seed(999)
    draws = [sample_conditions(validation[0], *CONDITIONS, g) for _ in range(3)]
    repeat_real = (torch.cat([d[0] for d in draws]), torch.cat([d[1] for d in draws]), validation[1].repeat(3))
    report = {"background_rays": {k: len(v[1]) for k, v in backgrounds.items()}, "circuits": {}}
    for name, path in circuits.items():
        circuit = load_circuit(path)
        # Sanity: the extended simulators agree with the shared reference.
        sample = validator.photons[:3000]
        cand, conf, state = run_full(circuit, sample)
        assert torch.equal(cand, simulate_stream(circuit, sample)), "full simulator differs"
        config = StreamConfig(**circuit["config"])
        inputs, codes = pack_circuit(circuit)
        pc, pq, ps = simulate_population_full(config, inputs[None], codes[None], sample)
        assert torch.equal(pc[0].long(), cand) and torch.equal(pq[0].long(), conf) and torch.equal(ps[0].long(), state)
        entry = {"path": str(path), "audit": validator.audit(circuit)}
        entry["valid"] = evaluate(circuit, validator, backgrounds)
        rep = evaluate(circuit, validator, repeat_bg, repeat_real)
        entry["valid_repeat"] = {"detection_at_fa_limit": rep["detection_at_fa_limit"]}
        entry["valid_repeat"]["readouts"] = {k: {x: y for x, y in v.items() if x == "detect" or x.startswith("fa_")}
                                             for k, v in rep["readouts"].items()}
        if not args.no_synth:
            from spad.hardware.synth import synthesize
            from spad.hardware.verilog import stream_verilog
            s = synthesize(stream_verilog(circuit), "photon_core", ROOT/"data")
            entry["synthesized"] = {k: v for k, v in s.items() if k != "report"}
        report["circuits"][name] = entry
        d = entry["valid"]["detection_at_fa_limit"]
        print(name, json.dumps(entry["audit"]["overall"]), json.dumps(d), flush=True)
        (args.out/"roc.json").write_text(json.dumps(report, indent=1)+"\n")


if __name__ == "__main__":
    main()
