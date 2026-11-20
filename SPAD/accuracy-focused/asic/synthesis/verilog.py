"""Export cores and the fixed peak detector to Verilog, and check a Yosys netlist.

stream_verilog turns a photon-stream-core-v1 circuit dictionary into one synchronous
module: the fixed datapath (candidate register, subtractors, window flags, confidence
counter) plus one combinational wire per learned gate. peak_verilog is the baseline
that scans a stored histogram for its maximum (it excludes the histogram memory).
Netlist reads a Yosys JSON gate netlist and simulates it with numpy so the generated
hardware can be compared against training.core.stream_model.simulate_stream.
Used by asic.synthesis.synth, timing, area_model and the ASAP7 flow scripts.
"""
import json

import numpy as np

from training.core.stream_model import ACTIONS, GATE_NEAR, RIVAL_FAR, StreamConfig, swap_slot, window_name, window_units


def _gate(name, a, b, table):
    """Verilog `wire` for one gate: an OR of the (a, b) minterms whose table entry is 1.

    table order is 00, 01, 10, 11. An all-zero table becomes the constant 1'b0.
    """
    terms = [f"({'' if ia else '~'}{a} & {'' if ib else '~'}{b})"
             for bit, (ia, ib) in zip(table, ((0, 0), (0, 1), (1, 0), (1, 1))) if bit]
    return f"  wire {name} = {' | '.join(terms) if terms else chr(39).join(('1', 'b0'))};"


def stream_verilog(circuit, module="photon_core"):
    """Return Verilog text for a photon-stream-core-v1 circuit.

    Ports: clk, rst, valid (a photon arrives this cycle), arrival [cand_bits-1:0]
    (time bin, 750 ps each) and output candidate [cand_bits-1:0], the current range
    estimate. One photon is consumed per clock when `valid` is high; rst clears
    candidate, confidence and state. Matches simulate_stream: the up/down and inc/dec
    updates saturate and cancel if both are set; replace wins over up/down.
    """
    c = StreamConfig(**circuit["config"])
    names = circuit["inputs"]
    subbin = c.frac_bits > 0 or c.step_bits > 0
    ab, cb, qb = c.cand_bits, c.cand_bits + c.frac_bits, c.conf_bits
    top = 2**qb - 1
    # A sub-bin core's candidate is fixed point: cand_bits whole bins, frac_bits fractional.
    time = "arrival_fx" if subbin else "arrival"
    lines = [f"module {module}(input clk, input rst, input valid, input [{ab-1}:0] arrival,",
             f"                   output reg [{cb-1}:0] candidate);",
             f"  reg [{qb-1}:0] confidence;"]
    if c.state_bits:
        lines.append(f"  reg [{c.state_bits-1}:0] state;")
    if subbin:
        lines.append(f"  wire [{cb-1}:0] arrival_fx = " + (f"{{arrival, {c.frac_bits}'b0}};" if c.frac_bits else "arrival;"))
    lines += [f"  wire [{cb}:0] above = {time} - candidate;",
              f"  wire [{cb}:0] below = candidate - {time};",
              f"  wire gt = {time} > candidate;", f"  wire lt = {time} < candidate;",
              f"  wire [{cb}:0] size = gt ? above : below;"]
    lines += [f"  wire {window_name(w)} = size <= {units};" for w, units in zip(c.windows, window_units(c))]
    lines += ["  wire zero = confidence == 0;"]
    lines += [f"  wire conf{level} = confidence >= {level};" for level in c.conf_levels]
    lines += [f"  wire full = confidence == {top};", "  wire const0 = 1'b0;", "  wire const1 = 1'b1;"]
    if c.rivals:
        lines += _rival_logic(c, ab, cb)
    if c.coincidence_depth:
        lines += _coincidence_logic(c, ab)
    if c.challenge_cap:
        lines += _challenge_logic(c, qb)
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
    if c.challenge_cap:
        # A far replace needs the challenger to outnumber the incumbent; blocked, replace, up and down drop.
        lines.append(f"  wire blocked = {outputs[c.state_bits]} & ~{window_name(GATE_NEAR)} & ~outnumber;")
    elif c.coincidence_depth:
        # A far replace after the first acquisition needs a coincidence; blocked, replace, up and down drop.
        lines.append(f"  wire blocked = {outputs[c.state_bits]} & acquired & ~{window_name(GATE_NEAR)} & ~coinc;")
    for i, action in enumerate(ACTIONS):
        gated = c.coincidence_depth and action in ("replace", "up", "down")
        lines.append(f"  wire do_{action} = {outputs[c.state_bits+i]}" + (" & ~blocked;" if gated else ";"))
    limit = 2**cb - 1
    if subbin:
        # Step of 2**-select bins, saturating at both ends of the register.
        first = c.state_bits + len(ACTIONS)
        select = "{" + ", ".join(reversed(outputs[first:first + c.step_bits])) + "}"
        if c.track == "prop":
            # Proportional: |distance| >> (select + 1), a running-mean update (never overshoots the photon).
            lines.append(f"  wire [{cb}:0] shifted = size >> ({{1'b0, {select}}} + 1'b1);")
            lines += [f"  wire [{cb-1}:0] step = shifted[{cb-1}:0];"]
        lines += ([] if c.track == "prop" else
                  [f"  wire [{cb-1}:0] step = " + (f"{cb}'d{c.scale} >> {select};" if c.step_bits else f"{cb}'d{c.scale};")]) + [
                  f"  wire [{cb}:0] sum = {{1'b0, candidate}} + {{1'b0, step}};",
                  f"  wire [{cb-1}:0] raised = (do_up && !do_down) ? (sum[{cb}] ? {cb}'d{limit} : sum[{cb-1}:0]) : candidate;",
                  f"  wire [{cb-1}:0] stepped = (do_down && !do_up) ? (candidate < step ? {cb}'d0 : candidate - step) : raised;"]
    else:
        lines += [f"  wire [{cb-1}:0] raised = (do_up && !do_down && candidate != {limit}) ? candidate + 1'b1 : candidate;",
                  f"  wire [{cb-1}:0] stepped = (do_down && !do_up && candidate != 0) ? candidate - 1'b1 : raised;"]
    lines += ["  always @(posedge clk) begin",
              "    if (rst) begin", "      candidate <= 0;", "      confidence <= 0;"]
    if c.state_bits:
        lines.append("      state <= 0;")
    if c.rivals:
        lines += [f"      rpos{k} <= 0;" for k in range(c.rivals)] + [f"      rvotes{k} <= 0;" for k in range(c.rivals)]
    if c.coincidence_depth:
        lines += [f"      cfifo{k} <= 0;" for k in range(c.coincidence_depth)]
        lines += [f"      cvalid{k} <= 0;" for k in range(c.coincidence_depth)] + ["      acquired <= 0;"]
    if c.rivals:
        whole = f"{{best_pos, {c.frac_bits}'b0}}" if c.frac_bits else "best_pos"
        update = f"{outputs[swap_slot(c)]} ? {whole} : do_replace ? {time} : stepped"
    else:
        update = f"do_replace ? {time} : stepped"
    lines += ["    end else if (valid) begin", f"      candidate <= {update};",
              f"      if (do_inc && !do_dec && confidence != {top}) confidence <= confidence + 1'b1;",
              "      if (do_dec && !do_inc && confidence != 0) confidence <= confidence - 1'b1;"]
    if c.challenge_cap:
        lines.append("      if (do_replace) confidence <= loaded;")
    lines += [f"      state[{i}] <= {outputs[i]};" for i in range(c.state_bits)]
    for k in range(c.rivals):
        lines += [f"      if (rhit{k} && rvotes{k} != {2**c.rival_bits - 1}) rvotes{k} <= rvotes{k} + 1'b1;",
                  f"      if (rtake{k}) begin rpos{k} <= arrival; rvotes{k} <= 1; end",
                  *_rival_track_line(c, k),
                  f"      if (rdecay) rvotes{k} <= rvotes{k} - 1'b1;"]
    if c.coincidence_depth:
        # The FIFO shifts on every valid photon; acquired sets on the first replace.
        lines += ["      cfifo0 <= arrival;", "      cvalid0 <= 1'b1;"]
        lines += [f"      cfifo{k} <= cfifo{k-1};" for k in range(1, c.coincidence_depth)]
        lines += [f"      cvalid{k} <= cvalid{k-1};" for k in range(1, c.coincidence_depth)]
        lines += ["      if (do_replace) acquired <= 1'b1;"]
    lines += ["    end", "  end", "endmodule", ""]
    return "\n".join(lines)


def _rival_track_line(c, k):
    """With rival_track, a voted register moves toward the photon: one bin, or half the gap."""
    if c.rival_track == "off":
        return []
    move = "1'b1" if c.rival_track == "step" else f"rdist{k}[{c.cand_bits}:1]"
    return [f"      if (rhit{k} && rdist{k} != 0) rpos{k} <= arrival > rpos{k} ? rpos{k} + {move} : rpos{k} - {move};"]


def _rival_logic(c, ab, cb):
    """Rival registers: positions, vote counters, their update signals and the flags they give."""
    n, rb = c.rivals, c.rival_bits
    lines = [f"  reg [{ab-1}:0] rpos{k};" for k in range(n)] + [f"  reg [{rb-1}:0] rvotes{k};" for k in range(n)]
    for k in range(n):
        lines += [f"  wire [{ab}:0] rdist{k} = arrival > rpos{k} ? arrival - rpos{k} : rpos{k} - arrival;",
                  f"  wire rmatch{k} = (rvotes{k} != 0) && (rdist{k} <= {c.rival_window});",
                  f"  wire rempty{k} = rvotes{k} == 0;"]
    any_of = lambda name, count: " | ".join(f"{name}{j}" for j in range(count)) or "1'b0"
    lines += [f"  wire rany = {any_of('rmatch', n)};", f"  wire rdecay = !rany && !({any_of('rempty', n)});"]
    for k in range(n):
        # A photon votes for the first register it matches, else takes the first empty one.
        lines += [f"  wire rhit{k} = rmatch{k} && !({any_of('rmatch', k)});",
                  f"  wire rtake{k} = !rany && rempty{k} && !({any_of('rempty', k)});"]
    # Best-supported register; the lowest-numbered one wins ties.
    lines += [f"  wire [{rb-1}:0] bvotes0 = rvotes0;", f"  wire [{ab-1}:0] bpos0 = rpos0;"]
    for k in range(1, n):
        lines += [f"  wire better{k} = rvotes{k} > bvotes{k-1};",
                  f"  wire [{rb-1}:0] bvotes{k} = better{k} ? rvotes{k} : bvotes{k-1};",
                  f"  wire [{ab-1}:0] bpos{k} = better{k} ? rpos{k} : bpos{k-1};"]
    whole = f"candidate[{cb-1}:{c.frac_bits}]" if c.frac_bits else "candidate"
    lines += [f"  wire [{rb-1}:0] best_votes = bvotes{n-1};", f"  wire [{ab-1}:0] best_pos = bpos{n-1};",
              f"  wire [{ab-1}:0] whole = {whole};",
              f"  wire [{ab}:0] rgap = best_pos > whole ? best_pos - whole : whole - best_pos;",
              f"  wire rival_far = (best_votes != 0) && (rgap > {RIVAL_FAR});"]
    lines += [f"  wire rival{level} = best_votes >= {level};" for level in c.rival_levels]
    return lines


def _coincidence_logic(c, ab):
    """FIFO of raw arrivals, the acquired bit, and coinc: the photon within the window of a valid entry.

    Each window test is one subtract, arrival - entry + W <= 2W, which equals |arrival - entry| <= W:
    with ab + 1 bits a negative difference wraps above 2W because W < 2**ab.
    """
    w, n = c.coincidence_window, c.coincidence_depth
    lines = [f"  reg [{ab-1}:0] cfifo{k};" for k in range(n)] + [f"  reg cvalid{k};" for k in range(n)]
    lines += ["  reg acquired;"]
    lines += [f"  wire [{ab}:0] cdiff{k} = {{1'b0, arrival}} - {{1'b0, cfifo{k}}} + {ab+1}'d{w};" for k in range(n)]
    lines += ["  wire coinc = " + " | ".join(f"(cvalid{k} && cdiff{k} <= {2*w})" for k in range(n)) + ";"]
    return lines


def _challenge_logic(c, qb):
    """Evidence = 1 + FIFO entries in the window (a small adder tree); outnumber = evidence > min(confidence, cap)."""
    n, top = c.coincidence_depth, 2**qb - 1
    eb = max(n + 1, 1).bit_length()
    hits = " + ".join(f"{{{eb-1}'b0, cvalid{k} && cdiff{k} <= {2*c.coincidence_window}}}" for k in range(n))
    return [f"  wire [{eb-1}:0] evidence = {eb}'d1 + {hits};",
            f"  wire [{qb-1}:0] incumbent = confidence > {c.challenge_cap} ? {qb}'d{c.challenge_cap} : confidence;",
            f"  wire outnumber = {{{max(qb, eb) - eb}'b0, evidence}} > {{{max(qb, eb) - qb}'b0, incumbent}};".replace("{0'b0, ", "{"),
            f"  wire [{qb-1}:0] loaded = " + (f"evidence > {top} ? {qb}'d{top} : evidence;" if 2**eb - 1 > top else f"evidence;")]


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
    """Vectorized simulator for a Yosys JSON gate netlist, for bit-exact checks.

    path: Yosys `write_json` output; module: top module name. Only the simple gate
    cells in GATES plus $_NOT_, $_MUX_, $_BUF_ and $_DFF_P_ flip-flops are accepted.
    Every ray is a numpy boolean lane, so a whole batch is simulated at once.
    """
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
        """Topologically sort combinational cells so each runs after its inputs."""
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
