"""Shared helpers for the flops track: data, standard audit, synthesis with register cuts.

Nothing here edits shared code. allow_small_counter() relaxes StreamConfig's conf_bits >= 4
check and pads the packed simulator's confidence flags *inside this process only*, so a
3- or 2-bit confidence counter can be simulated, synthesized and verified unchanged.
"""
import json
from pathlib import Path

import torch

from spad import ROOT
from spad.core import stream_model as sm
from spad.core.stream_model import ACTIONS, CONF_LEVELS, StreamConfig
from spad.dataset.photons import load_rays
from spad.training.police import Police, measure_pulse

DATA = ROOT/"data"
CONDITIONS = (16, 256, .6)
FLOP_CELL = "DFFHQx4_ASAP7_75t_R"


def allow_small_counter():
    """Let StreamConfig take conf_bits < 4 in this process (flags conf8 etc. are then constant 0)."""
    if getattr(sm, "_flops_patched", False):
        return

    def relaxed(self):
        self.windows = tuple(self.windows)
        if self.width < self.state_bits + len(ACTIONS):
            raise ValueError("Last layer must hold next state and all actions")
        if self.layers < 1 or self.conf_bits < 1 or self.state_bits < 0:
            raise ValueError("Need a layer, a confidence bit and nonnegative state")
    StreamConfig.__post_init__ = relaxed
    original = sm._suffix_or
    # conf_above[m] for m = log2(level) must exist even when the counter is narrower than 4 bits.
    sm._suffix_or = lambda planes, none: original(planes, none) + [none] * 4
    sm._flops_patched = True


def load_data(device="cpu"):
    train = [x.to(device) for x in load_rays(DATA, "train", clean_only=True)[:2]]
    routing = [x.to(device) for x in load_rays(DATA, "architecture", clean_only=True)[:2]]
    validation = [x.to(device) for x in load_rays(DATA, "validation")[:2]]
    pulse, zero = measure_pulse(train[0].cpu())
    return train, routing, validation, Police(pulse, zero).to(device), pulse


def standard_audit(circuit, data, seed=1234):
    from spad.training.train_stream import Validator
    train, _, validation, police, _ = data
    return Validator(train, validation, CONDITIONS, 3, police, seed=seed).audit(circuit)


def short_audit(audit):
    row = {"mae_m": audit["overall"]["mae_m"], "median_m": audit["overall"]["median_m"],
           "within3": audit["overall"].get("recall_3_bins")}
    row["offset_steps"] = [round(audit[k]["median_signed_bins"], 2)
                           for k in ("photons_16-32", "photons_32-64", "photons_64-128", "photons_128-256")]
    row["time_shift"] = audit["time_shift_test"]["moves_with_photons_within_1_bin"]
    return row


# ----------------------------------------------------------------------------- Verilog with cuts

def _gate(name, a, b, table):
    terms = [f"({'' if ia else '~'}{a} & {'' if ib else '~'}{b})"
             for bit, (ia, ib) in zip(table, ((0, 0), (0, 1), (1, 0), (1, 1))) if bit]
    return f"  wire {name} = {' | '.join(terms) if terms else chr(39).join(('1', 'b0'))};"


def cut_verilog(circuit, drop_state=(), drop_conf=False, open_all=False, no_step=False, module="photon_core"):
    """Same core as spad.hardware.verilog.stream_verilog, with registers optionally cut out.

    drop_state: state bits whose flop and next-value logic are removed; their value becomes a free
        input, so logic that reads them stays (area difference = flop + logic that only serves it).
    drop_conf: the same for the whole confidence counter (flags that read it stay).
    open_all: every register becomes a free input and its next value an output, with no valid/reset
        gating (area difference = flops + their per-flop load/reset muxing only).
    no_step: the candidate never steps up/down (only replace or hold): removes the +-1 stepper.
    With every option off the text matches stream_verilog's logic exactly.
    """
    c = StreamConfig(**circuit["config"])
    names = circuit["inputs"]
    cb, qb, sb = c.cand_bits, c.conf_bits, c.state_bits
    top = 2**qb - 1
    drop_state = set(drop_state)
    ports = ["input clk", "input rst", "input valid", f"input [{cb-1}:0] arrival"]
    body = []
    if open_all:
        ports += [f"input [{cb-1}:0] candidate", f"output [{cb-1}:0] candidate_next",
                  f"input [{qb-1}:0] confidence", f"output [{qb-1}:0] confidence_next"]
        if sb:
            ports += [f"input [{sb-1}:0] state", f"output [{sb-1}:0] state_next"]
    else:
        ports.append(f"output reg [{cb-1}:0] candidate")
        if drop_conf:
            ports.append(f"input [{qb-1}:0] confidence")
        else:
            body.append(f"  reg [{qb-1}:0] confidence;")
        if sb:
            body.append(f"  reg [{sb-1}:0] state;")
            if drop_state:
                ports.append(f"input [{sb-1}:0] state_free")
    body += [f"  wire [{cb}:0] above = arrival - candidate;", f"  wire [{cb}:0] below = candidate - arrival;",
             "  wire gt = arrival > candidate;", "  wire lt = arrival < candidate;",
             f"  wire [{cb}:0] size = gt ? above : below;"]
    body += [f"  wire near{w} = size <= {w};" for w in c.windows]
    body += ["  wire zero = confidence == 0;"]
    body += [f"  wire conf{level} = confidence >= {level};" for level in CONF_LEVELS]
    body += [f"  wire full = confidence == {top};", "  wire const0 = 1'b0;", "  wire const1 = 1'b1;"]
    body += [f"  wire state{i} = {'state_free' if i in drop_state and not open_all else 'state'}[{i}];"
             for i in range(sb)]
    pool = list(names)
    for depth, layer in enumerate(circuit["layers"]):
        outputs = []
        for gate, (inputs, table) in enumerate(zip(layer["inputs"], layer["truth_tables"])):
            wire = f"g{depth}_{gate}"
            body.append(_gate(wire, pool[inputs[0]], pool[inputs[1]], table))
            outputs.append(wire)
        pool = list(names) + outputs
    outputs = pool[len(names):]
    for i, action in enumerate(ACTIONS):
        body.append(f"  wire do_{action} = {outputs[sb+i]};")
    limit = 2**cb - 1
    if no_step:
        body.append(f"  wire [{cb-1}:0] stepped = candidate;")
    else:
        body += [f"  wire [{cb-1}:0] raised = (do_up && !do_down && candidate != {limit}) ? candidate + 1'b1 : candidate;",
                 f"  wire [{cb-1}:0] stepped = (do_down && !do_up && candidate != 0) ? candidate - 1'b1 : raised;"]
    if open_all:
        body += ["  assign candidate_next = do_replace ? arrival : stepped;",
                 f"  assign confidence_next = (do_inc && !do_dec && confidence != {top}) ? confidence + 1'b1 :"
                 f" (do_dec && !do_inc && confidence != 0) ? confidence - 1'b1 : confidence;"]
        if sb:
            body.append(f"  assign state_next = {{{', '.join(outputs[i] for i in reversed(range(sb)))}}};")
        body.append("endmodule\n")
        return f"module {module}({', '.join(ports)});\n" + "\n".join(body)
    body += ["  always @(posedge clk) begin", "    if (rst) begin", "      candidate <= 0;"]
    if not drop_conf:
        body.append("      confidence <= 0;")
    if sb:
        body.append("      state <= 0;")
    body += ["    end else if (valid) begin", "      candidate <= do_replace ? arrival : stepped;"]
    if not drop_conf:
        body += [f"      if (do_inc && !do_dec && confidence != {top}) confidence <= confidence + 1'b1;",
                 "      if (do_dec && !do_inc && confidence != 0) confidence <= confidence - 1'b1;"]
    body += [f"      state[{i}] <= {outputs[i]};" for i in range(sb) if i not in drop_state]
    body += ["    end", "  end", "endmodule", ""]
    return f"module {module}({', '.join(ports)});\n" + "\n".join(body)


def synth(verilog):
    from spad.hardware.synth import synthesize
    result = synthesize(verilog, "photon_core", DATA)
    flop_area = 0.
    for line in result["report"].splitlines():
        parts = line.split()
        if len(parts) == 3 and parts[2].startswith(("DFF", "DLL", "DHL")):
            flop_area += float(parts[1])
    return {"area": result["area"], "cells": result["cells"], "flops": result["flops"],
            "flop_area": round(flop_area, 4)}


def synth_circuit(circuit):
    from spad.hardware.verilog import stream_verilog
    return synth(stream_verilog(circuit))


def parity(circuit):
    from spad.hardware.synth import verify
    from spad.hardware.verilog import stream_verilog
    return verify(stream_verilog(circuit), "photon_core", circuit)


def load_circuit(path):
    return json.loads(Path(path).read_text())


@torch.no_grad()
def register_activity(circuit, photons):
    """Simulate (integer reference semantics) and record what each register does.

    Returns per state bit: fraction of (ray, photon) steps where it is 1 and whether it ever
    changes; for the counter: highest value reached, share of steps at each flag level.
    """
    c = StreamConfig(**circuit["config"])
    rays = len(photons)
    photons = photons.long()
    candidate = torch.zeros(rays, dtype=torch.long)
    confidence = torch.zeros_like(candidate)
    state = torch.zeros(rays, c.state_bits, dtype=torch.long)
    top_c, top_q = 2**c.cand_bits - 1, 2**c.conf_bits - 1
    specs = [(torch.tensor(x["inputs"]), torch.tensor(x["truth_tables"])) for x in circuit["layers"]]
    gates = torch.arange(c.width)[None]
    steps = 0
    state_on = torch.zeros(c.state_bits)
    state_toggles = torch.zeros(c.state_bits)
    conf_hist = torch.zeros(top_q + 1)
    for step in range(photons.shape[1]):
        arrival, valid = photons[:, step], photons[:, step] >= 0
        if not valid.any():
            break
        distance = arrival - candidate
        flags = [(distance.abs() <= w) for w in c.windows]
        flags += [distance > 0, distance < 0, confidence == 0]
        flags += [confidence >= level for level in CONF_LEVELS]
        flags += [confidence == top_q, torch.zeros_like(valid), torch.ones_like(valid)]
        base = torch.cat((torch.stack(flags, 1).long(), state), 1)
        output = None
        for inputs, tables in specs:
            pool = base if output is None else torch.cat((base, output), 1)
            output = tables[gates, 2*pool[:, inputs[:, 0]] + pool[:, inputs[:, 1]]]
        new_state = output[:, :c.state_bits]
        replace, up, down, inc, dec = output[:, c.state_bits:c.state_bits+len(ACTIONS)].T
        stepped = (candidate + up - down).clamp(0, top_c)
        candidate = torch.where(valid, torch.where(replace == 1, arrival, stepped), candidate)
        new_conf = torch.where(valid, (confidence + inc - dec).clamp(0, top_q), confidence)
        new_state = torch.where(valid[:, None], new_state, state)
        state_toggles += (new_state != state)[valid].float().sum(0)
        state = new_state
        confidence = new_conf
        steps += int(valid.sum())
        state_on += state[valid].float().sum(0)
        conf_hist += torch.bincount(confidence[valid], minlength=top_q + 1).float()
    return {"state_on_share": (state_on/steps).tolist(), "state_toggles_per_photon": (state_toggles/steps).tolist(),
            "confidence_max": int((conf_hist > 0).nonzero().max()),
            "confidence_share_by_value": [round(x, 4) for x in (conf_hist/steps).tolist()]}
