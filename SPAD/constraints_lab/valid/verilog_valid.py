"""Verilog export with an extra `valid_out` port, its synthesis and a bit-exact netlist check.

The core is the shared `stream_verilog` output with one more output; the shared file is not edited.
Readouts (`readout` argument):
  "conf>=K"            valid_out = confidence >= K
  "stateI" / "~stateI" valid_out = state[I] (or its inverse)
  "none"               no extra port (the reference core)
"""
import argparse
import json
import re
import tempfile
from pathlib import Path

import numpy as np
import torch

from spad import ROOT
from spad.hardware.synth import synthesize, yosys
from spad.hardware.verilog import GATES, Netlist, stream_verilog

from constraints_lab.valid.sim import simulate_stream_full


def readout_expression(readout):
    if readout.startswith("conf>="):
        return f"confidence >= {int(readout[6:])}"
    match = re.fullmatch(r"(~?)state(\d+)", readout)
    if match:
        return f"{'~' if match[1] else ''}state[{match[2]}]"
    raise ValueError(readout)


def valid_verilog(circuit, readout, module="photon_core"):
    text = stream_verilog(circuit, module)
    if readout == "none":
        return text
    head, rest = text.split(");", 1)
    text = head + ",\n                   output valid_out);" + rest
    return text.replace("endmodule", f"  assign valid_out = {readout_expression(readout)};\nendmodule")


def readout_bits(readout, confidence, state):
    if readout.startswith("conf>="):
        return confidence >= int(readout[6:])
    inverse = readout.startswith("~")
    bit = state[:, int(readout.lstrip("~")[5:])] == 1
    return ~bit if inverse else bit


class ValidNetlist(Netlist):
    def _ordered(self):
        outputs = {b for k in ("candidate", "valid_out") for b in self.ports.get(k, [])}
        known = {q for _, q in self.flops} | {b for k, bits in self.ports.items() for b in bits if b not in outputs
                                               and k not in ("candidate", "valid_out")}
        known |= {"0", "1", "x"}
        pending, ordered = self.comb, []
        while pending:
            waiting = []
            for kind, wires in pending:
                if all(wires[p][0] in known for p in wires if p != "Y"):
                    ordered.append((kind, wires))
                    known.add(wires["Y"][0])
                else:
                    waiting.append((kind, wires))
            if len(waiting) == len(pending):
                raise ValueError("Combinational loop in netlist")
            pending = waiting
        return ordered

    def run_valid(self, photons):
        """Reset, clock each photon; return final candidate and valid_out."""
        rays = len(photons)
        zero, one = np.zeros(rays, bool), np.ones(rays, bool)
        values = {"0": zero, "1": one, "x": zero}
        for _, q in self.flops:
            values[q] = zero

        def settle(rst, valid, arrival):
            values[self.ports["rst"][0]] = rst
            values[self.ports["clk"][0]] = zero
            values[self.ports["valid"][0]] = valid
            for i, b in enumerate(self.ports["arrival"]):
                values[b] = ((arrival >> i) & 1).astype(bool)
            for kind, w in self.comb:
                get = lambda p: values[w[p][0]]
                if kind == "$_NOT_":
                    out = ~get("A")
                elif kind == "$_BUF_":
                    out = get("A")
                elif kind == "$_MUX_":
                    out = np.where(get("S"), get("B"), get("A"))
                else:
                    out = GATES[kind](get("A"), get("B"))
                values[w["Y"][0]] = out

        def tick(rst, valid, arrival):
            settle(rst, valid, arrival)
            for q, v in [(q, values[d]) for d, q in self.flops]:
                values[q] = v

        none = np.zeros(rays, dtype=np.int64)
        tick(one, zero, none)
        for step in range(photons.shape[1]):
            arrival = photons[:, step]
            tick(zero, arrival >= 0, np.where(arrival >= 0, arrival, 0))
        settle(zero, zero, none)       # combinational outputs after the last clock
        bit = lambda b: values[b] if b in values else (one if b == "1" else zero)
        candidate = sum(bit(b).astype(np.int64) << i for i, b in enumerate(self.ports["candidate"]))
        valid = bit(self.ports["valid_out"][0]) if "valid_out" in self.ports else None
        return candidate, valid


def verify_valid(circuit, readout, rays=4000, seed=3):
    """Mismatches (candidate, valid_out) between the Yosys gate netlist and the Python simulator."""
    verilog = valid_verilog(circuit, readout)
    with tempfile.TemporaryDirectory() as name:
        folder = Path(name)
        (folder/"core.v").write_text(verilog)
        yosys("read_verilog core.v\nhierarchy -top photon_core\nsynth -flatten -top photon_core\n"
              "dfflegalize -cell $_DFF_P_ x\nabc -g AND,OR,XOR,MUX\nopt_clean\nwrite_json core.json\n", folder)
        netlist = ValidNetlist(folder/"core.json", "photon_core")
    torch.manual_seed(seed)
    centre = torch.randint(0, 672, (rays, 1))
    photons = (centre + torch.randint(-12, 13, (rays, 96))).clamp(0, 671)
    noise = torch.rand(rays, 96) < .3
    photons = torch.where(noise, torch.randint(0, 672, (rays, 96)), photons)
    # Half the rays are pure background, so the valid bit takes both values.
    photons[: rays//2] = torch.randint(0, 672, (rays//2, 96))
    photons = torch.where(torch.rand(rays, 96) < .05, torch.full_like(photons, -1), photons)
    cand, conf, state = simulate_stream_full(circuit, photons)
    got_cand, got_valid = netlist.run_valid(photons.numpy())
    expected_valid = readout_bits(readout, conf, state).numpy() if readout != "none" else None
    return {"candidate_mismatches": int((cand.numpy() != got_cand).sum()),
            "valid_mismatches": int((expected_valid != got_valid).sum()) if expected_valid is not None else 0,
            "valid_ones": int(expected_valid.sum()) if expected_valid is not None else None}


def synth_valid(circuit, readout):
    s = synthesize(valid_verilog(circuit, readout), "photon_core", ROOT/"data")
    return {k: v for k, v in s.items() if k != "report"}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("circuit", type=Path)
    parser.add_argument("readouts", nargs="+")
    parser.add_argument("--verify", action="store_true")
    parser.add_argument("--out", type=Path)
    args = parser.parse_args()
    torch.set_num_threads(1)
    circuit = json.loads(args.circuit.read_text())
    results = {}
    for readout in ["none"] + args.readouts:
        results[readout] = synth_valid(circuit, readout)
        if args.verify:
            results[readout]["parity"] = verify_valid(circuit, readout)
        print(readout, results[readout], flush=True)
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(json.dumps(results, indent=1)+"\n")


if __name__ == "__main__":
    main()
