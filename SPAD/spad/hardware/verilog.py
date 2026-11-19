"""Export cores and the fixed peak detector to Verilog, and check a Yosys netlist."""
import json

import numpy as np

from spad.core.stream_model import ACTIONS, CONF_LEVELS, StreamConfig


def _gate(name, a, b, table):
    terms = [f"({'' if ia else '~'}{a} & {'' if ib else '~'}{b})"
             for bit, (ia, ib) in zip(table, ((0, 0), (0, 1), (1, 0), (1, 1))) if bit]
    return f"  wire {name} = {' | '.join(terms) if terms else chr(39).join(('1', 'b0'))};"


def stream_verilog(circuit, module="photon_core"):
    c = StreamConfig(**circuit["config"])
    names = circuit["inputs"]
    cb, qb = c.cand_bits, c.conf_bits
    top = 2**qb - 1
    lines = [f"module {module}(input clk, input rst, input valid, input [{cb-1}:0] arrival,",
             f"                   output reg [{cb-1}:0] candidate);",
             f"  reg [{qb-1}:0] confidence;"]
    if c.state_bits:
        lines.append(f"  reg [{c.state_bits-1}:0] state;")
    lines += [f"  wire [{cb}:0] above = arrival - candidate;",
              f"  wire [{cb}:0] below = candidate - arrival;",
              "  wire gt = arrival > candidate;", "  wire lt = arrival < candidate;",
              f"  wire [{cb}:0] size = gt ? above : below;"]
    lines += [f"  wire near{w} = size <= {w};" for w in c.windows]
    lines += ["  wire zero = confidence == 0;"]
    lines += [f"  wire conf{level} = confidence >= {level};" for level in CONF_LEVELS]
    lines += [f"  wire full = confidence == {top};", "  wire const0 = 1'b0;", "  wire const1 = 1'b1;"]
    lines += [f"  wire state{i} = state[{i}];" for i in range(c.state_bits)]
    pool = list(names)
    for depth, layer in enumerate(circuit["layers"]):
        outputs = []
        for gate, (inputs, table) in enumerate(zip(layer["inputs"], layer["truth_tables"])):
            wire = f"g{depth}_{gate}"
            lines.append(_gate(wire, pool[inputs[0]], pool[inputs[1]], table))
            outputs.append(wire)
        pool = list(names) + outputs
    outputs = pool[len(names):]
    for i, action in enumerate(ACTIONS):
        lines.append(f"  wire do_{action} = {outputs[c.state_bits+i]};")
    limit = 2**cb - 1
    lines += [f"  wire [{cb-1}:0] raised = (do_up && !do_down && candidate != {limit}) ? candidate + 1'b1 : candidate;",
              f"  wire [{cb-1}:0] stepped = (do_down && !do_up && candidate != 0) ? candidate - 1'b1 : raised;",
              "  always @(posedge clk) begin",
              "    if (rst) begin", "      candidate <= 0;", "      confidence <= 0;"]
    if c.state_bits:
        lines.append("      state <= 0;")
    lines += ["    end else if (valid) begin", "      candidate <= do_replace ? arrival : stepped;",
              f"      if (do_inc && !do_dec && confidence != {top}) confidence <= confidence + 1'b1;",
              "      if (do_dec && !do_inc && confidence != 0) confidence <= confidence - 1'b1;"]
    lines += [f"      state[{i}] <= {outputs[i]};" for i in range(c.state_bits)]
    lines += ["    end", "  end", "endmodule", ""]
    return "\n".join(lines)


def peak_verilog(count_bits=12, bin_bits=10, module="peak_reader"):
    """Reducer that scans a stored histogram: excludes the histogram memory itself."""
    return f"""module {module}(input clk, input rst, input valid, input [{count_bits-1}:0] count,
                   output reg [{bin_bits-1}:0] best_bin);
  reg [{count_bits-1}:0] best;
  reg [{bin_bits-1}:0] position;
  always @(posedge clk) begin
    if (rst) begin best <= 0; best_bin <= 0; position <= 0; end
    else if (valid) begin
      position <= position + 1'b1;
      if (count > best) begin best <= count; best_bin <= position; end
    end
  end
endmodule
"""


GATES = {"$_AND_": lambda a, b: a & b, "$_OR_": lambda a, b: a | b, "$_XOR_": lambda a, b: a ^ b,
         "$_NAND_": lambda a, b: ~(a & b), "$_NOR_": lambda a, b: ~(a | b), "$_XNOR_": lambda a, b: ~(a ^ b),
         "$_ANDNOT_": lambda a, b: a & ~b, "$_ORNOT_": lambda a, b: a | ~b}


class Netlist:
    """Vectorized simulator for a Yosys JSON gate netlist, for bit-exact checks."""
    def __init__(self, path, module):
        design = json.loads(path.read_text())["modules"][module]
        self.ports = {k: v["bits"] for k, v in design["ports"].items()}
        self.comb, self.flops = [], []
        for cell in design["cells"].values():
            kind, wires = cell["type"], cell["connections"]
            if kind == "$_DFF_P_":
                self.flops.append((wires["D"][0], wires["Q"][0]))
            elif kind in GATES or kind in ("$_NOT_", "$_MUX_", "$_BUF_"):
                self.comb.append((kind, wires))
            else:
                raise ValueError(f"Unexpected cell {kind}")
        self.comb = self._ordered()

    def _ordered(self):
        known = {q for _, q in self.flops} | {b for k, bits in self.ports.items() if k != "candidate" for b in bits}
        known |= {"0", "1", "x"}
        pending, ordered = self.comb, []
        while pending:
            waiting = []
            for kind, wires in pending:
                needs = [wires[p][0] for p in wires if p != "Y"]
                if all(n in known for n in needs):
                    ordered.append((kind, wires))
                    known.add(wires["Y"][0])
                else:
                    waiting.append((kind, wires))
            if len(waiting) == len(pending):
                raise ValueError("Combinational loop in netlist")
            pending = waiting
        return ordered

    def run(self, photons):
        """Reset, clock each photon, and return the final candidate values."""
        rays = len(photons)
        zero, one = np.zeros(rays, bool), np.ones(rays, bool)
        values = {"0": zero, "1": one, "x": zero}
        for _, q in self.flops:
            values[q] = zero

        def tick(rst, valid, arrival):
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
            nxt = [(q, values[d]) for d, q in self.flops]
            for q, v in nxt:
                values[q] = v

        none = np.zeros(rays, dtype=np.int64)
        tick(one, zero, none)
        for step in range(photons.shape[1]):
            arrival = photons[:, step]
            tick(zero, arrival >= 0, np.where(arrival >= 0, arrival, 0))
        return sum(values[b].astype(np.int64) << i for i, b in enumerate(self.ports["candidate"]))
