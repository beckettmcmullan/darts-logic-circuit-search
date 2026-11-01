"""
Gate-level DARTS search for a 1011 sequence detector.
The circuit sees one input bit x per clock and must raise z on the clock where the
last four inputs were 1, 0, 1, 1 (overlaps count: 1011011 fires twice).
It is never given a state transition table, only input/output sequences.
Each gate node learns alpha (what gate it is) and beta_a / beta_b (what it reads).
Each D flip-flop learns delta (what it stores for the next clock), and gamma picks
the signal that drives z. Two hardware costs join the loss: the expected area of
the gates and flip-flops the output depends on, and the expected critical path.
"""

import torch
import torch.nn as nn
import torch.nn.functional as F
import argparse
import json
import os
from collections import deque

import matplotlib
matplotlib.use("Agg")  # write image files; no window needed
import matplotlib.pyplot as plt


# Differentiable expressions for boolean gates
# On 0/1 inputs these give exact Boolean results. Between 0 and 1 they
# provide smooth outputs so gradients can flow through the circuit choices.
def gate_not(a): return 1 - a
def gate_and(a, b): return a * b
def gate_or(a, b): return a + b - a * b
def gate_nand(a, b): return 1 - a * b
def gate_nor(a, b): return (1 - a) * (1 - b)
def gate_xor(a, b): return a + b - 2 * a * b
def gate_xnor(a, b): return 1 - gate_xor(a, b)


# Each gate's formula and how many inputs it reads
GATES = {
    "NOT": (gate_not, 1),
    "AND": (gate_and, 2),
    "OR": (gate_or, 2),
    "XOR": (gate_xor, 2),
    "NAND": (gate_nand, 2),
    "NOR": (gate_nor, 2),
    "XNOR": (gate_xnor, 2),
}

GATE_NAMES = list(GATES)


# The sources a gate actually reads: both wires, or only the first one for NOT
def gate_sources(gate, a, b):
    return (a, b)[:GATES[gate][1]]

# Illustrative hardware costs in standard-cell units. Area is in gate equivalents
# (GE: one 2-input NAND = 1), delay in NAND delays. NAND/NOR are the cheapest and
# fastest cells in CMOS; AND/OR are a NAND/NOR plus an inverter. Swap these for
# numbers from Vivado reports when the operators become synthesized modules.
GATE_AREA = {
    "NOT": 0.67, "AND": 1.33, "OR": 1.33, "XOR": 2.33,
    "NAND": 1.0, "NOR": 1.0, "XNOR": 2.33,
}

GATE_DELAY = {
    "NOT": 1.0, "AND": 2.0, "OR": 2.0, "XOR": 3.0,
    "NAND": 1.0, "NOR": 1.0, "XNOR": 3.0,
}

FF_AREA = 4.67  # D flip-flop with reset

PATTERN = (1, 0, 1, 1)


# z[t] = 1 when x[t-3..t] is 1,0,1,1. This is the only place the pattern appears:
# the circuit sees these targets, never the states that produce them.
def detector_targets(x):

    z = torch.zeros_like(x)
    n = len(PATTERN)

    hit = torch.ones_like(x[:, n - 1:])

    for j, bit in enumerate(PATTERN):
        hit = hit * (x[:, j:x.shape[1] - n + 1 + j] == bit).float()

    z[:, n - 1:] = hit

    return z


def make_sequences(count, length, generator):
    x = torch.randint(0, 2, (count, length), generator=generator).float()
    return x, detector_targets(x)


# Gumbel noise to occasionally give less favored operations a greater influence during training
def gumbel(t):
    u = torch.rand_like(t).clamp(1e-6, 1 - 1e-6)
    return -torch.log(-torch.log(u))


# Train independent candidate circuits together as one batch; this samples
# several searches, rather than enumerating every possible circuit.
class SequenceCircuits(nn.Module):

    def __init__(self, num_circuits, num_nodes=8, num_ffs=3, init_std=1.0):
        super().__init__()

        self.num_nodes = num_nodes
        self.num_ffs = num_ffs

        # Signal order: x, then each flip-flop output Q0..QK-1, then each gate node.
        self.base = 1 + num_ffs
        sources = self.base + num_nodes

        # These parameters are choice scores (logits), not fixed gate weights:
        # alpha chooses the gate, beta_a/b choose its wires, delta chooses what
        # each flip-flop stores, and gamma chooses the signal that drives z.
        self.alpha = nn.Parameter(init_std * torch.randn(num_circuits, num_nodes, len(GATE_NAMES)))
        self.beta_a = nn.Parameter(init_std * torch.randn(num_circuits, num_nodes, sources))
        self.beta_b = nn.Parameter(init_std * torch.randn(num_circuits, num_nodes, sources))

        # Flip-flops and z may read any signal, including x or a Q directly.
        # A flip-flop reading another Q is a plain wire, which is how shift
        # registers are built.
        self.delta = nn.Parameter(init_std * torch.randn(num_circuits, num_ffs, sources))
        self.gamma = nn.Parameter(init_std * torch.randn(num_circuits, sources))

        # Keep the combinational logic acyclic: node i reads x, the Qs and
        # earlier nodes only. Loops are allowed only through a flip-flop.
        mask = torch.full((num_nodes, sources), float("-inf"))
        for i in range(num_nodes):
            mask[i, :self.base + i] = 0
        self.register_buffer("mask", mask)

        self.register_buffer("area", torch.tensor([GATE_AREA[g] for g in GATE_NAMES]))
        self.register_buffer("delay", torch.tensor([GATE_DELAY[g] for g in GATE_NAMES]))

        # Coefficients of (1, a, b, a*b) for each gate, read off by evaluating
        # the gate at the four corners (a, b) in {0, 1}^2.
        corners = [(0, 0), (1, 0), (0, 1), (1, 1)]
        poly = []

        for fn, arity in GATES.values():
            f00, f10, f01, f11 = [float(fn(*(a, b)[:arity])) for a, b in corners]
            poly.append([f00, f10 - f00, f01 - f00, f11 - f10 - f01 + f00])

        self.register_buffer("gate_poly", torch.tensor(poly))

        self.register_buffer("binary", torch.tensor([float(GATES[g][1] == 2) for g in GATE_NAMES]))

    # Soft choices for one forward pass. hard=True gives the argmax circuit as
    # one-hot weights, which makes the same forward pass exact Boolean logic.
    def choices(self, tau=1.0, noise=0.0, hard=False):

        def weights(scores, extra=0):

            scores = scores + extra

            if hard:
                return F.one_hot(scores.argmax(-1), scores.shape[-1]).float()

            if noise:
                scores = scores + noise * gumbel(scores)

            # Lower temperature makes choices sharper; higher temperature mixes
            # candidates more evenly. They remain soft during the forward pass.
            return F.softmax(scores / tau, dim=-1)

        return {
            "gate": weights(self.alpha),
            "a": weights(self.beta_a, self.mask),
            "b": weights(self.beta_b, self.mask),
            "d": weights(self.delta),
            "z": weights(self.gamma),
        }

    def forward(self, x, w):

        circuits = self.alpha.shape[0]
        batch, steps = x.shape

        # Every flip-flop resets to 0 at the start of a sequence.
        q = x.new_zeros(circuits, batch, self.num_ffs)

        # (circuits, nodes, 4): the blended gate as c0 + c1*a + c2*b + c3*a*b
        coef = w["gate"] @ self.gate_poly

        zs, qs = [], []

        for t in range(steps):

            # (circuits, batch, sources): x and the stored state at this clock
            signals = torch.cat([x[:, t].expand(circuits, batch).unsqueeze(-1), q], dim=-1)

            for i in range(self.num_nodes):

                width = signals.shape[-1]

                # Each input is a weighted sum of available signals, not yet one wire.
                # In einsum: c = circuit, b = sequence in the batch, s = source.
                a = torch.einsum("cbs,cs->cb", signals, w["a"][:, i, :width])
                b = torch.einsum("cbs,cs->cb", signals, w["b"][:, i, :width])

                # Weighted combination of candidate gate outputs. Every gate
                # formula above is c0 + c1*a + c2*b + c3*a*b, so blending the 7
                # gate outputs equals blending their coefficients (much faster).
                c = coef[:, i, None, :]
                node_output = c[..., 0] + c[..., 1] * a + c[..., 2] * b + c[..., 3] * a * b

                signals = torch.cat([signals, node_output.unsqueeze(-1)], dim=-1)

            zs.append(torch.einsum("cbs,cs->cb", signals, w["z"]))
            qs.append(q)

            # Clock edge: each flip-flop stores its (soft) D input for the next step.
            # Training sends gradients back through earlier clocks along this path.
            q = torch.einsum("cbs,cks->cbk", signals, w["d"])

        # (circuits, batch, steps) and (circuits, batch, steps, flip-flops)
        return torch.stack(zs, dim=-1), torch.stack(qs, dim=2)

    # Expected area and critical path of each soft circuit, differentiable in
    # every choice. Only hardware that z actually depends on is charged.
    def hardware_cost(self, w):

        circuits = self.alpha.shape[0]
        n, k, base = self.num_nodes, self.num_ffs, self.base

        p_binary = (w["gate"] * self.binary).sum(-1)    # gate reads input b too
        node_area = (w["gate"] * self.area).sum(-1)     # (circuits, nodes)
        node_delay = (w["gate"] * self.delay).sum(-1)

        # read[c, j, s]: probability that gate j reads signal s on either input
        read = 1 - (1 - w["a"]) * (1 - w["b"] * p_binary[..., None])

        # Liveness: the probability that a signal matters for z. A signal is live
        # if z reads it, a live flip-flop stores it, or a live gate reads it. A
        # flip-flop is live if its Q is. Loops through flip-flops make this
        # circular, so start from "nothing live" and repeat the sweep.
        live_q = w["z"].new_zeros(circuits, k)

        for _ in range(k + 1):

            # probability that neither z nor a live flip-flop reads each signal
            unread = (1 - w["z"]) * torch.prod(
                1 - live_q[..., None] * w["d"], dim=1
            )

            # Walk gates from last to first so later readers are known.
            live = [None] * n

            for i in reversed(range(n)):

                u = unread[:, base + i]

                for j in range(i + 1, n):
                    u = u * (1 - live[j] * read[:, j, base + i])

                live[i] = 1 - u

            live_nodes = torch.stack(live, dim=1)

            unread_base = unread[:, :base] * torch.prod(
                1 - live_nodes[..., None] * read[:, :, :base], dim=1
            )

            live_q = 1 - unread_base[:, 1:]

        area = (live_nodes * node_area).sum(-1) + FF_AREA * live_q.sum(-1)

        # Arrival times: x and every Q are ready at the clock edge (time 0).
        # A gate starts when its later input arrives, then adds its own delay.
        arrival = w["z"].new_zeros(circuits, base)

        for i in range(n):

            width = base + i
            in_a = (w["a"][:, i, :width] * arrival).sum(-1)
            in_b = (w["b"][:, i, :width] * arrival).sum(-1)

            # max(in_a, in_b) for 2-input gates, in_a for NOT, mixed by p_binary
            start = in_a + p_binary[:, i] * torch.relu(in_b - in_a)

            arrival = torch.cat(
                [arrival, (start + node_delay[:, i]).unsqueeze(-1)],
                dim=-1
            )

        # The clock period is set by the slowest path into z or into a live
        # flip-flop's D input. max() sends the gradient to that critical endpoint.
        t_z = (w["z"] * arrival).sum(-1, keepdim=True)
        t_d = live_q * (w["d"] * arrival[:, None, :]).sum(-1)

        critical = torch.cat([t_z, t_d], dim=1).max(dim=1).values

        return area, critical

    # argmax of every choice for circuit c
    def extract(self, c):

        gates = self.alpha[c].argmax(-1).tolist()
        src_a = (self.beta_a[c] + self.mask).argmax(-1).tolist()
        src_b = (self.beta_b[c] + self.mask).argmax(-1).tolist()

        return {
            "nodes": [
                (GATE_NAMES[g], a, b)
                for g, a, b in zip(gates, src_a, src_b)
            ],
            "d": self.delta[c].argmax(-1).tolist(),
            "z": self.gamma[c].argmax().item(),
        }


# ---------------------------------------------------------------------------
# Discrete circuit tools: everything below works on the extracted circuit.
# ---------------------------------------------------------------------------

def signal_name(s, num_ffs):

    if s == 0:
        return "x"

    if s <= num_ffs:
        return f"Q{s - 1}"

    return f"n{s - 1 - num_ffs}"


# one clock of the discrete circuit: returns z, the next state and all signals
def circuit_step(circuit, bit, q):

    signals = [bit, *q]

    for gate, a, b in circuit["nodes"]:

        fn = GATES[gate][0]
        signals.append(int(fn(*(signals[src] for src in gate_sources(gate, a, b)))))

    return (
        signals[circuit["z"]],
        tuple(signals[s] for s in circuit["d"]),
        signals,
    )


# signals z depends on, now or through any flip-flop
def live_signals(circuit):

    num_ffs = len(circuit["d"])
    base = 1 + num_ffs

    used, stack = set(), [circuit["z"]]

    while stack:

        s = stack.pop()

        if s in used:
            continue

        used.add(s)

        if 1 <= s < base:
            stack.append(circuit["d"][s - 1])  # a used flip-flop needs its D input

        elif s >= base:
            stack.extend(gate_sources(*circuit["nodes"][s - base]))

    return used


# indices k of the flip-flops z depends on (flip-flop k is signal 1 + k)
def live_ffs(circuit, used):
    return [k for k in range(len(circuit["d"])) if 1 + k in used]


# longest register-to-register (or input-to-z) path through the live gates
def critical_path(circuit, used):

    num_ffs = len(circuit["d"])
    base = 1 + num_ffs

    arrival = {s: 0.0 for s in range(base)}
    previous = {}

    for i, (gate, a, b) in enumerate(circuit["nodes"]):

        s = base + i
        latest = max(gate_sources(gate, a, b), key=arrival.get)

        arrival[s] = arrival[latest] + GATE_DELAY[gate]
        previous[s] = latest

    endpoints = [("z", circuit["z"])] + [(f"D{k}", circuit["d"][k]) for k in live_ffs(circuit, used)]

    end, s = max(endpoints, key=lambda e: arrival[e[1]])
    path = [s]

    while path[-1] in previous:
        path.append(previous[path[-1]])

    return arrival[s], path[::-1], end


# Exact check against the reference detector for EVERY input sequence of ANY
# length: walk all reachable (last three inputs, circuit state) pairs from reset.
# There are at most 8 * 2^K of them, so this finishes instantly. On failure,
# return the shortest input sequence that makes the circuit disagree.
def verify(circuit):

    start = ((0, 0, 0), (0,) * len(circuit["d"]))
    parent = {start: None}
    queue = deque([start])

    while queue:

        history, q = queue.popleft()

        for bit in (0, 1):

            want = int(history + (bit,) == PATTERN)
            got, q_next, _ = circuit_step(circuit, bit, q)

            if got != want:

                sequence, state = [bit], (history, q)

                while parent[state] is not None:
                    state, b = parent[state]
                    sequence.append(b)

                return False, sequence[::-1]

            nxt = (history[1:] + (bit,), q_next)

            if nxt not in parent:
                parent[nxt] = ((history, q), bit)
                queue.append(nxt)

    return True, None


# The state machine the circuit implements, read off by simulation from reset:
# this is the transition table the search was never given.
def state_table(circuit):

    live = live_ffs(circuit, live_signals(circuit))

    def key(q):
        return "".join(str(q[k]) for k in live) or "-"

    start = (0,) * len(circuit["d"])
    seen, queue, rows = {start}, deque([start]), []

    while queue:

        q = queue.popleft()
        row = {"state": key(q)}

        for bit in (0, 1):

            z, q_next, _ = circuit_step(circuit, bit, q)
            row[f"next{bit}"] = key(q_next)
            row[f"z{bit}"] = z

            if q_next not in seen:
                seen.add(q_next)
                queue.append(q_next)

        rows.append(row)

    # different full states can look the same on the live flip-flops
    unique = list({r["state"]: r for r in rows}.values())

    return [f"Q{k}" for k in live], unique


def describe(circuit):

    k = len(circuit["d"])
    used = live_signals(circuit)
    name = lambda s: signal_name(s, k)
    lines = []

    for i, (gate, a, b) in enumerate(circuit["nodes"]):

        if 1 + k + i not in used:
            continue

        args = ", ".join(name(src) for src in gate_sources(gate, a, b))
        lines.append(f"n{i} = {gate}({args})")

    for q in live_ffs(circuit, used):
        lines.append(f"Q{q} <= {name(circuit['d'][q])}   (next clock)")

    lines.append(f"z = {name(circuit['z'])}")

    return lines


# hardware numbers for one extracted circuit
def circuit_stats(circuit):

    k = len(circuit["d"])
    used = live_signals(circuit)

    gates = [circuit["nodes"][s - 1 - k][0] for s in used if s > k]
    ffs = len(live_ffs(circuit, used))
    delay, path, end = critical_path(circuit, used)

    return {
        "gates": len(gates),
        "ffs": ffs,
        "area": sum(GATE_AREA[g] for g in gates) + FF_AREA * ffs,
        "delay": delay,
        "path": path,
        "end": end,
    }


# Run every argmax circuit at once on a set of sequences (hard one-hot weights).
@torch.no_grad()
def discrete_accuracy(model, x, y):

    z, q = model(x, model.choices(hard=True))
    right = (z.round() == y).float()

    return {
        "bit": right.mean(dim=(1, 2)),                     # every output bit
        "sequence": right.min(dim=2).values.mean(dim=1),   # whole sequences right
        "recall": (right * y).sum(dim=(1, 2)) / y.sum(),   # detections caught
    }, z, q


def search(
    seed=0,
    circuits=64,
    num_nodes=8,
    num_ffs=3,
    epochs=500,
    train_seqs=256,
    seq_len=16,
    batch=64,
    lr=0.05,
    tau_start=1.0,
    tau_end=0.3,
    noise=1.0,
    gate_weight=0.01,
    delay_weight=0.01,
    cost_start=0.3,
    cost_full=0.6,
    pos_weight=4.0,
    eval_every=5
):

    torch.manual_seed(seed)

    # Training data: random bit sequences and the detector's output bits.
    # Unseen test data: a different generator and 4x longer sequences, so the
    # circuit must keep working beyond the horizon it was trained on.
    data_gen = torch.Generator().manual_seed(seed)
    x_train, y_train = make_sequences(train_seqs, seq_len, data_gen)

    test_gen = torch.Generator().manual_seed(seed + 10_000)
    x_test, y_test = make_sequences(500, 4 * seq_len, test_gen)

    model = SequenceCircuits(circuits, num_nodes, num_ffs)
    opt = torch.optim.Adam(model.parameters(), lr=lr)

    history = {
        "epoch": [], "tau": [], "ramp": [],
        "total": [], "task": [], "gate_cost": [], "delay_cost": [],
        "soft_area": [], "soft_delay": [], "train_acc": [],
        "eval_epoch": [], "eval": [],
    }

    for epoch in range(epochs):

        progress = epoch / max(epochs - 1, 1)

        # Geometric temperature annealing, as in the full adder search
        tau = tau_start * (tau_end / tau_start) ** progress

        # Hardware costs stay off until the search has found working logic, then
        # ramp in. Turning them on from the start collapses circuits to nothing.
        ramp = min(max((progress - cost_start) / (cost_full - cost_start), 0.0), 1.0)

        order = torch.randperm(train_seqs, generator=data_gen)
        # Per-circuit totals over this epoch's batches, named as in history
        sums = {key: torch.zeros(circuits) for key in
                ["total", "task", "gate_cost", "delay_cost", "soft_area", "soft_delay", "train_acc"]}
        batches = 0

        for start in range(0, train_seqs, batch):

            idx = order[start:start + batch]
            x, y = x_train[idx], y_train[idx]

            # One noisy sample of every choice per batch, shared across all clocks,
            # so each batch trains one consistent (soft) circuit per search.
            w = model.choices(tau, noise)
            z, _ = model(x, w)

            # Detections are rare (1 in 16 positions), so a missed 1 costs
            # pos_weight times more than a false alarm; otherwise "always 0"
            # already scores ~94% and the search stalls there.
            task = F.binary_cross_entropy(
                z.clamp(1e-6, 1 - 1e-6),
                y.expand_as(z),
                weight=(1 + (pos_weight - 1) * y).expand_as(z),
                reduction="none"
            ).mean(dim=(1, 2))

            area, delay = model.hardware_cost(w)

            gate_cost = ramp * gate_weight * area
            delay_cost = ramp * delay_weight * delay
            per_circuit = task + gate_cost + delay_cost

            # Sum over circuits so each circuit gets the same gradient it would get alone.
            opt.zero_grad()
            per_circuit.sum().backward()
            opt.step()

            with torch.no_grad():
                sums["total"] += per_circuit
                sums["task"] += task
                sums["gate_cost"] += gate_cost
                sums["delay_cost"] += delay_cost
                sums["soft_area"] += area
                sums["soft_delay"] += delay
                sums["train_acc"] += ((z > 0.5).float() == y).float().mean(dim=(1, 2))

            batches += 1

        mean = {key: (value / batches) for key, value in sums.items()}

        history["epoch"].append(epoch + 1)
        history["tau"].append(tau)
        history["ramp"].append(ramp)
        for key, value in mean.items():
            history[key].append(value.tolist())

        # Snap every circuit to its argmax and test it on unseen sequences,
        # plus the exact all-sequences check.
        if epoch % eval_every == 0 or epoch == epochs - 1:

            acc, _, _ = discrete_accuracy(model, x_test, y_test)
            train_acc, _, _ = discrete_accuracy(model, x_train, y_train)
            rows = []

            with torch.no_grad():

                for c in range(circuits):

                    circuit = model.extract(c)
                    stats = circuit_stats(circuit)

                    rows.append({
                        "verified": verify(circuit)[0],
                        "test_bit": acc["bit"][c].item(),
                        "test_seq": acc["sequence"][c].item(),
                        "recall": acc["recall"][c].item(),
                        "train_bit": train_acc["bit"][c].item(),
                        "gates": stats["gates"],
                        "ffs": stats["ffs"],
                        "area": stats["area"],
                        "delay": stats["delay"],
                    })

            history["eval_epoch"].append(epoch + 1)
            history["eval"].append(rows)

            ok = sum(r["verified"] for r in rows)
            print(
                f"epoch {epoch + 1:4d}  tau {tau:.2f}  cost ramp {ramp:.2f}  "
                f"median task loss {mean['task'].median():.4f}  "
                f"verified {ok}/{circuits}"
            )

    return model, history, (x_test, y_test)


# matplotlib: loss vs epoch, median over the batch of searches
def plot_loss(history, path):

    epochs = history["epoch"]

    fig, ax = plt.subplots(figsize=(8, 4.5))

    for key, label, color in [
        ("total", "total loss", "#2b2b2a"),
        ("task", "task loss (weighted BCE)", "#2a78d6"),
        ("gate_cost", "gate area penalty", "#eb6834"),
        ("delay_cost", "propagation delay penalty", "#1baf7a"),
    ]:
        median = torch.tensor(history[key]).median(dim=1).values
        ax.plot(epochs, median, color=color, linewidth=2, label=label)

    # shade where the hardware penalties ramp in
    ramp = history["ramp"]
    on = [e for e, r in zip(epochs, ramp) if 0 < r < 1]

    if on:
        ax.axvspan(on[0], on[-1], color="#e6e5e0", alpha=0.6, linewidth=0)
        ax.text(on[0], 0.03, " hardware costs ramp in", transform=ax.get_xaxis_transform(),
                fontsize=8, color="#55544f")

    ax.set_yscale("log")
    ax.set_title("1011 detector search: loss vs epoch (median over searches)",
                 loc="left", fontsize=12)
    ax.set_xlabel("epoch")
    ax.set_ylabel("loss")
    ax.grid(True, color="#e6e5e0", linewidth=0.8)
    ax.set_axisbelow(True)

    for side in ["top", "right"]:
        ax.spines[side].set_visible(False)

    ax.legend(frameon=False)
    fig.tight_layout()
    fig.savefig(path, dpi=150)
    plt.close(fig)


# The same loss curves as a self-contained HTML page (no internet needed): hover
# or use the arrow keys to read every series at any epoch. Takes the saved
# report data, so it can be rebuilt from history.json without retraining.
LOSS_SERIES = [
    ("total", "total loss", "--ink"),
    ("task", "task loss (weighted BCE)", "--series-1"),
    ("gate_cost", "gate area penalty", "--series-2"),
    ("delay_cost", "propagation delay penalty", "--series-3"),
]

LOSS_PAGE = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>1011 detector search: loss vs epoch</title>
<style>
  :root {
    color-scheme: light;
    --surface: #fcfcfb; --page: #f9f9f7;
    --ink: #0b0b0b; --ink-2: #52514e; --muted: #898781;
    --grid: #e1e0d9; --axis: #c3c2b7; --band: #f0efec; --border: rgba(11,11,11,0.10);
    --series-1: #2a78d6; --series-2: #eb6834; --series-3: #1baf7a;
  }
  @media (prefers-color-scheme: dark) {
    :root {
      color-scheme: dark;
      --surface: #1a1a19; --page: #0d0d0d;
      --ink: #f0efec; --ink-2: #c3c2b7; --muted: #898781;
      --grid: #2c2c2a; --axis: #383835; --band: #262624; --border: rgba(255,255,255,0.10);
      --series-1: #3987e5; --series-2: #d95926; --series-3: #199e70;
    }
  }
  body { margin: 0; padding: 24px; background: var(--page); color: var(--ink);
         font: 14px/1.4 system-ui, -apple-system, "Segoe UI", sans-serif; }
  .card { max-width: 960px; margin: 0 auto; background: var(--surface);
          border: 1px solid var(--border); border-radius: 12px; padding: 20px 20px 12px; }
  h1 { font-size: 16px; font-weight: 600; margin: 0 0 2px; }
  .sub { color: var(--ink-2); margin: 0 0 12px; }
  .legend { display: flex; flex-wrap: wrap; gap: 4px 18px; margin: 0 0 8px; color: var(--ink-2); }
  .legend span { display: inline-flex; align-items: center; gap: 6px; }
  .legend i { display: inline-block; width: 16px; height: 2px; border-radius: 1px; }
  #chart { position: relative; }
  svg { display: block; width: 100%; overflow: visible; }
  svg text { fill: var(--muted); font-size: 11px; font-variant-numeric: tabular-nums; }
  svg .label { font-size: 12px; fill: var(--ink-2); }
  .hit { fill: transparent; cursor: crosshair; outline: none; }
  .hit:focus-visible { stroke: var(--series-1); stroke-width: 2; }
  .tip { position: absolute; pointer-events: none; background: var(--surface); color: var(--ink);
         border: 1px solid var(--border); border-radius: 8px; padding: 8px 10px; min-width: 190px;
         box-shadow: 0 4px 16px rgba(0,0,0,0.12); font-size: 12px; display: none; }
  .tip .head { font-weight: 600; }
  .tip .meta { color: var(--muted); margin-bottom: 6px; }
  .tip .row { display: flex; align-items: center; gap: 8px; }
  .tip .row i { width: 12px; height: 2px; border-radius: 1px; flex: none; }
  .tip .row b { font-variant-numeric: tabular-nums; min-width: 62px; }
  .tip .row span { color: var(--ink-2); }
  .note { color: var(--muted); font-size: 12px; margin: 8px 0 0; }
  details { margin-top: 12px; color: var(--ink-2); }
  summary { cursor: pointer; }
  .table-wrap { max-height: 360px; overflow: auto; margin-top: 8px; border: 1px solid var(--border); border-radius: 8px; }
  table { border-collapse: collapse; width: 100%; font-variant-numeric: tabular-nums; font-size: 12px; }
  th, td { padding: 4px 10px; text-align: right; border-bottom: 1px solid var(--grid); }
  th { position: sticky; top: 0; background: var(--surface); color: var(--ink); font-weight: 600; }
</style>
</head>
<body>
<div class="card">
  <h1>1011 detector search: loss vs epoch</h1>
  <p class="sub" id="sub"></p>
  <div class="legend" id="legend"></div>
  <div id="chart"><svg id="svg" role="img" aria-label="Loss vs epoch, log scale"></svg><div class="tip" id="tip"></div></div>
  <p class="note">Each curve is the median over all searches of that quantity on its own, so the
    medians of the parts need not add up to the median total. Penalties are zero (not drawn
    on the log axis) until the hardware costs ramp in. Hover, or focus the chart and use the arrow keys.</p>
  <details id="details"><summary>Data table</summary><div class="table-wrap"><table id="table"></table></div></details>
</div>
<script>
const DATA = __LOSS_DATA__;
const NS = "http://www.w3.org/2000/svg";
const svg = document.getElementById("svg"), tip = document.getElementById("tip");
const css = name => getComputedStyle(document.documentElement).getPropertyValue(name).trim();
const fmt = v => v === 0 ? "0" : (v >= 0.01 ? v.toFixed(4) : v.toExponential(2));
const n = DATA.epoch.length;
let focusIndex = n - 1;

document.getElementById("sub").textContent =
  `Median over ${DATA.circuits} parallel searches, ${n} epochs, log scale`;

const legend = document.getElementById("legend");
for (const s of DATA.series) {
  const item = document.createElement("span"), key = document.createElement("i");
  key.style.background = `var(${s.color})`;
  item.append(key, document.createTextNode(s.label));
  legend.append(item);
}

function el(tag, attrs, parent) {
  const node = document.createElementNS(NS, tag);
  for (const k in attrs) node.setAttribute(k, attrs[k]);
  if (parent) parent.append(node);
  return node;
}

function render() {
  svg.replaceChildren();
  const W = svg.parentElement.clientWidth, H = 380;
  const m = { top: 12, right: W < 560 ? 12 : 170, bottom: 36, left: 52 };
  svg.setAttribute("viewBox", `0 0 ${W} ${H}`);
  svg.setAttribute("height", H);
  const iw = W - m.left - m.right, ih = H - m.top - m.bottom;

  const positive = DATA.series.flatMap(s => s.values.filter(v => v > 0));
  const lo = Math.floor(Math.log10(Math.min(...positive)));
  const hi = Math.ceil(Math.log10(Math.max(...positive)));
  const x = e => m.left + (e - DATA.epoch[0]) / (DATA.epoch[n - 1] - DATA.epoch[0]) * iw;
  const y = v => m.top + (hi - Math.log10(v)) / (hi - lo) * ih;

  // where the hardware costs ramp in
  const ramping = DATA.epoch.filter((e, i) => DATA.ramp[i] > 0 && DATA.ramp[i] < 1);
  if (ramping.length) {
    const x0 = x(ramping[0]), x1 = x(ramping[ramping.length - 1]);
    el("rect", { x: x0, y: m.top, width: x1 - x0, height: ih, fill: css("--band") }, svg);
    el("text", { x: x0 + 6, y: m.top + ih - 8 }, svg).textContent = "hardware costs ramp in";
  }

  // gridlines and y ticks at every decade
  for (let p = lo; p <= hi; p++) {
    const yy = y(10 ** p);
    el("line", { x1: m.left, x2: m.left + iw, y1: yy, y2: yy, stroke: css("--grid"), "stroke-width": 1 }, svg);
    el("text", { x: m.left - 8, y: yy + 4, "text-anchor": "end" }, svg).textContent =
      p >= 0 ? String(10 ** p) : (p >= -3 ? (10 ** p).toFixed(-p) : `1e${p}`);
  }

  // x axis
  el("line", { x1: m.left, x2: m.left + iw, y1: m.top + ih, y2: m.top + ih, stroke: css("--axis") }, svg);
  const step = W < 560 ? 100 : 50;
  for (let e = 0; e <= DATA.epoch[n - 1]; e += step) {
    if (e < DATA.epoch[0]) continue;
    el("text", { x: x(e), y: m.top + ih + 18, "text-anchor": "middle" }, svg).textContent = e;
  }
  el("text", { x: m.left + iw / 2, y: H - 2, "text-anchor": "middle" }, svg).textContent = "epoch";
  el("text", { x: 12, y: m.top + ih / 2, "text-anchor": "middle",
               transform: `rotate(-90 12 ${m.top + ih / 2})` }, svg).textContent = "loss";

  // lines; zeros break the path because log(0) is undefined
  for (const s of DATA.series) {
    let d = "", pen = false;
    s.values.forEach((v, i) => {
      if (v > 0) { d += `${pen ? "L" : "M"}${x(DATA.epoch[i]).toFixed(1)},${y(v).toFixed(1)}`; pen = true; }
      else pen = false;
    });
    el("path", { d, fill: "none", stroke: css(s.color), "stroke-width": 2,
                 "stroke-linejoin": "round", "stroke-linecap": "round" }, svg);
  }

  // direct labels at the right end, nudged apart so they never overlap
  if (m.right > 100) {
    const ends = DATA.series.map(s => ({ s, yy: y(s.values[n - 1]) })).sort((a, b) => a.yy - b.yy);
    for (let i = 1; i < ends.length; i++) ends[i].yy = Math.max(ends[i].yy, ends[i - 1].yy + 15);
    for (const { s, yy } of ends)
      el("text", { class: "label", x: m.left + iw + 8, y: yy + 4 }, svg).textContent = s.label;
  }

  // crosshair, one dot per series and the hit area for pointer and keyboard
  const cross = el("line", { y1: m.top, y2: m.top + ih, stroke: css("--muted"), "stroke-width": 1, visibility: "hidden" }, svg);
  const dots = DATA.series.map(s => el("circle", { r: 4, fill: css(s.color), stroke: css("--surface"),
                                                    "stroke-width": 2, visibility: "hidden" }, svg));
  const hit = el("rect", { class: "hit", x: m.left, y: m.top, width: iw, height: ih, tabindex: 0,
                           "aria-label": "Loss chart: use left and right arrow keys to step through epochs" }, svg);

  function show(i) {
    focusIndex = i;
    const cx = x(DATA.epoch[i]);
    cross.setAttribute("x1", cx); cross.setAttribute("x2", cx); cross.setAttribute("visibility", "visible");
    DATA.series.forEach((s, k) => {
      const v = s.values[i];
      dots[k].setAttribute("visibility", v > 0 ? "visible" : "hidden");
      if (v > 0) { dots[k].setAttribute("cx", cx); dots[k].setAttribute("cy", y(v)); }
    });

    tip.replaceChildren();
    const head = document.createElement("div"); head.className = "head";
    head.textContent = `Epoch ${DATA.epoch[i]}`;
    const meta = document.createElement("div"); meta.className = "meta";
    meta.textContent = `temperature ${DATA.tau[i].toFixed(3)} · cost ramp ${DATA.ramp[i].toFixed(2)}`;
    tip.append(head, meta);
    for (const s of DATA.series) {
      const row = document.createElement("div"); row.className = "row";
      const key = document.createElement("i"); key.style.background = `var(${s.color})`;
      const val = document.createElement("b"); val.textContent = fmt(s.values[i]);
      const name = document.createElement("span"); name.textContent = s.label;
      row.append(key, val, name); tip.append(row);
    }
    tip.style.display = "block";
    const tw = tip.offsetWidth, left = cx + 14 + tw > W ? cx - 14 - tw : cx + 14;
    tip.style.left = `${Math.max(0, left)}px`;
    tip.style.top = `${m.top + 8}px`;
  }
  function hide() {
    cross.setAttribute("visibility", "hidden");
    dots.forEach(d => d.setAttribute("visibility", "hidden"));
    tip.style.display = "none";
  }

  hit.addEventListener("pointermove", ev => {
    const box = svg.getBoundingClientRect();
    const px = (ev.clientX - box.left) * (W / box.width);
    const e = DATA.epoch[0] + (px - m.left) / iw * (DATA.epoch[n - 1] - DATA.epoch[0]);
    show(Math.min(n - 1, Math.max(0, Math.round(e - DATA.epoch[0]))));
  });
  hit.addEventListener("pointerleave", hide);
  hit.addEventListener("focus", () => show(focusIndex));
  hit.addEventListener("blur", hide);
  hit.addEventListener("keydown", ev => {
    const jump = ev.shiftKey ? 10 : 1;
    if (ev.key === "ArrowRight") show(Math.min(n - 1, focusIndex + jump));
    else if (ev.key === "ArrowLeft") show(Math.max(0, focusIndex - jump));
    else if (ev.key === "Home") show(0);
    else if (ev.key === "End") show(n - 1);
    else return;
    ev.preventDefault();
  });
}

// the table is built the first time it is opened
document.getElementById("details").addEventListener("toggle", function () {
  const table = document.getElementById("table");
  if (!this.open || table.rows.length) return;
  const head = table.createTHead().insertRow();
  for (const name of ["epoch", "temperature", "cost ramp", ...DATA.series.map(s => s.label)]) {
    const th = document.createElement("th"); th.textContent = name; head.append(th);
  }
  const body = table.createTBody();
  DATA.epoch.forEach((e, i) => {
    const row = body.insertRow();
    for (const v of [e, DATA.tau[i].toFixed(3), DATA.ramp[i].toFixed(2), ...DATA.series.map(s => fmt(s.values[i]))])
      row.insertCell().textContent = v;
  });
});

render();
addEventListener("resize", render);
matchMedia("(prefers-color-scheme: dark)").addEventListener("change", render);
</script>
</body>
</html>
"""


def plot_loss_html(data, path):

    payload = {
        "circuits": data["settings"]["circuits"],
        "epoch": data["epoch"],
        "tau": data["tau"],
        "ramp": data["ramp"],
        "series": [
            {"key": key, "label": label, "color": color, "values": data["median"][key]}
            for key, label, color in LOSS_SERIES
        ],
    }

    # "</" would end the <script> block early if it ever appeared in the data
    page = LOSS_PAGE.replace("__LOSS_DATA__", json.dumps(payload).replace("</", "<\\/"))

    with open(path, "w") as f:
        f.write(page)


# ---------------------------------------------------------------------------
# Schematic of an extracted circuit (live part only), drawn with matplotlib.
# Layout: x and the flip-flops in column 0, each gate in the column of its
# logic depth and on its own row, so a horizontal wire never runs through a
# gate. Wires turn in a vertical channel just before the column they feed;
# flip-flop D inputs loop back along lanes under the circuit.
# ---------------------------------------------------------------------------

GATE_W, GATE_H, BUBBLE = 1.0, 0.8, 0.16
COL_W, ROW_H = 3.0, 1.3


def _bezier(p0, p1, p2, n=20):
    t = torch.linspace(0, 1, n)[:, None]
    p0, p1, p2 = (torch.tensor(p, dtype=torch.float) for p in (p0, p1, p2))
    return ((1 - t) ** 2 * p0 + 2 * (1 - t) * t * p1 + t ** 2 * p2).tolist()


# outline of a gate body with its back edge at x0, centered on y0
def _gate_outline(gate, x0, y0):

    w, h = GATE_W, GATE_H

    if gate in ("AND", "NAND"):
        r = h / 2
        arc = [(w - r + r * torch.cos(a).item(), r * torch.sin(a).item())
               for a in torch.linspace(-torch.pi / 2, torch.pi / 2, 30)]
        pts = [(0, -r), *arc, (0, r)]

    elif gate == "NOT":
        pts = [(0, -h / 2.5), (w - BUBBLE, 0), (0, h / 2.5)]

    else:  # OR, NOR, XOR, XNOR share the OR body
        pts = (_bezier((0, h / 2), (0.6 * w, h / 2), (w, 0))
               + _bezier((w, 0), (0.6 * w, -h / 2), (0, -h / 2))
               + _bezier((0, -h / 2), (0.25 * w, 0), (0, h / 2)))

    return [(x0 + px, y0 + py) for px, py in pts]


def _draw_gate(ax, gate, x0, y0, label):

    ax.add_patch(plt.Polygon(_gate_outline(gate, x0, y0), closed=True,
                             facecolor="white", edgecolor="black", linewidth=1.4, zorder=3))

    if gate in ("XOR", "XNOR"):
        back = _bezier((-0.14, GATE_H / 2), (0.11, 0), (-0.14, -GATE_H / 2))
        ax.plot([x0 + px for px, _ in back], [y0 + py for _, py in back],
                color="black", linewidth=1.4, zorder=3)

    out = x0 + GATE_W
    if gate in ("NOT", "NAND", "NOR", "XNOR"):
        cx = x0 + GATE_W + BUBBLE / 2 - (BUBBLE if gate == "NOT" else 0)
        ax.add_patch(plt.Circle((cx, y0), BUBBLE / 2, facecolor="white",
                                edgecolor="black", linewidth=1.4, zorder=4))
        out = cx + BUBBLE / 2

    ax.text(x0 + 0.3, y0 + GATE_H / 2 + 0.08, label, fontsize=7, color="#55544f", zorder=5)
    ax.text(x0 + 0.38, y0, gate, fontsize=6.5, ha="center", va="center", zorder=5)

    return out


def draw_circuit(circuit, path, title="Discovered circuit"):

    k = len(circuit["d"])
    base = 1 + k
    used = live_signals(circuit)
    ffs = live_ffs(circuit, used)
    gates = [i for i in range(len(circuit["nodes"])) if base + i in used]
    name = lambda s: signal_name(s, k)

    # column = logic depth (inputs and flip-flops are depth 0)
    depth = {s: 0 for s in range(base)}
    for i, (gate, a, b) in enumerate(circuit["nodes"]):
        depth[base + i] = 1 + max(depth[s] for s in gate_sources(gate, a, b))

    rows = [0] + [1 + q for q in ffs] + sorted((base + i for i in gates), key=lambda s: (depth[s], s))
    y = {s: -r * ROW_H for r, s in enumerate(rows)}
    last_col = max([depth[s] for s in rows] + [0])
    right = last_col * COL_W + GATE_W + 0.8   # where right-side channels start

    fig_w = max(6.0, (right + 1.5 + 0.35 * len(ffs)) * 0.9)
    fig_h = max(3.0, (len(rows) + 1.5 + 0.35 * len(ffs)) * ROW_H * 0.6)
    fig, ax = plt.subplots(figsize=(fig_w, fig_h))

    # sources: x terminal and flip-flop boxes in column 0
    out = {}
    ax.text(0.35, y[0], "x", fontsize=11, ha="right", va="center")
    out[0] = GATE_W

    for q in ffs:
        s, cy = 1 + q, y[1 + q]
        ax.add_patch(plt.Rectangle((0.1, cy - 0.45), 0.9, 0.9, facecolor="white",
                                   edgecolor="black", linewidth=1.4, zorder=3))
        ax.text(0.2, cy + 0.2, "D", fontsize=7, va="center", zorder=5)
        ax.text(0.9, cy + 0.2, "Q", fontsize=7, ha="right", va="center", zorder=5)
        ax.plot([0.1, 0.22, 0.1], [cy - 0.33, -0.25 + cy, cy - 0.17], color="black",
                linewidth=1, zorder=5)  # clock triangle
        ax.text(0.55, cy - 0.62, f"Q{q}", fontsize=7, ha="center", color="#55544f")
        out[s] = GATE_W

    pins = {}  # gate signal -> list of (source, pin y)
    for i in gates:
        s = base + i
        gate, a, b = circuit["nodes"][i]
        x0 = depth[s] * COL_W
        out[s] = _draw_gate(ax, gate, x0, y[s], name(s))
        srcs = gate_sources(gate, a, b)
        offsets = [0.0] if len(srcs) == 1 else [GATE_H / 4, -GATE_H / 4]
        pins[s] = [(src, y[s] + off) for src, off in zip(srcs, offsets)]

    # every net is drawn as segments; points where 3+ segment ends meet get a dot
    nets = {s: [] for s in rows}

    # gate inputs: one channel per (source, target column)
    for col in range(1, last_col + 1):
        feeding = sorted({src for s in pins if depth[s] == col for src, _ in pins[s]},
                         key=lambda src: y[src])
        lo, hi = (col - 1) * COL_W + GATE_W + 0.4, col * COL_W - 0.25
        for j, src in enumerate(feeding):
            cx = lo + (hi - lo) * (j + 1) / (len(feeding) + 1)
            ys = [py for s in pins if depth[s] == col for p, py in pins[s] if p == src]
            nets[src].append((cx, ys, col * COL_W + 0.15))

    # flip-flop D inputs: right channel, down to a lane, back left, up to D
    bottom = min(y.values()) - 0.9
    feedback = []
    for n, q in enumerate(ffs):
        src = circuit["d"][q]
        rx = right + 0.35 * n
        lane = bottom - 0.35 * n
        lx = -0.25 - 0.3 * n
        feedback.append((src, rx, lane, lx, y[1 + q]))

    z_x = right + 0.35 * len(ffs) + 0.4
    for s, segs_in in nets.items():
        segs = []
        stops = [cx for cx, _, _ in segs_in] + [rx for src, rx, *_ in feedback if src == s]
        if s == circuit["z"]:
            stops.append(z_x)
        if not stops:
            continue

        xs = sorted({out[s], *stops})
        segs += [((a, y[s]), (b, y[s])) for a, b in zip(xs, xs[1:])]

        for cx, ys, end in segs_in:
            vs = sorted({y[s], *ys})
            segs += [((cx, a), (cx, b)) for a, b in zip(vs, vs[1:])]
            segs += [((cx, py), (end, py)) for py in ys]

        for src, rx, lane, lx, dy in feedback:
            if src == s:
                segs += [((rx, y[s]), (rx, lane)), ((rx, lane), (lx, lane)),
                         ((lx, lane), (lx, dy)), ((lx, dy), (0.15, dy))]

        ends = {}
        for seg in segs:
            ax.plot(*zip(*seg), color="black", linewidth=1.1, zorder=1)
            for p in seg:
                key = (round(p[0], 3), round(p[1], 3))
                ends[key] = ends.get(key, 0) + 1

        for (px, py), count in ends.items():
            if count >= 3:
                ax.add_patch(plt.Circle((px, py), 0.06, color="black", zorder=2))

    ax.text(z_x + 0.1, y[circuit["z"]], "z", fontsize=11, va="center")
    ax.text(-0.25 - 0.3 * max(len(ffs) - 1, 0) - 0.1, bottom - 0.35 * len(ffs),
            "all flip-flops share clk and reset", fontsize=7, color="#55544f", va="top")

    ax.set_title(title, loc="left", fontsize=11)
    ax.set_aspect("equal")
    ax.axis("off")
    ax.autoscale_view()
    fig.tight_layout()
    fig.savefig(path, dpi=200)
    plt.close(fig)


# Everything the interactive page needs, as plain JSON.
def report_data(model, history, test_data, args):

    x_test, y_test = test_data
    acc, z_all, q_all = discrete_accuracy(model, x_test, y_test)
    circuits = model.alpha.shape[0]
    k = model.num_ffs

    final = []

    for c in range(circuits):

        circuit = model.extract(c)
        ok, counterexample = verify(circuit)
        stats = circuit_stats(circuit)

        final.append({
            "id": c,
            "verified": ok,
            "counterexample": counterexample,
            "test_bit": acc["bit"][c].item(),
            "test_seq": acc["sequence"][c].item(),
            **{key: stats[key] for key in ["gates", "ffs", "area", "delay", "end", "path"]},
            "lines": describe(circuit),
            "circuit": circuit,
        })

    # Best = verified, then cheapest by the same weighted cost the search used.
    def cost(r):
        return args.gate_weight * r["area"] + args.delay_weight * r["delay"]

    verified = [r for r in final if r["verified"]]
    best = min(
        verified or final,
        key=lambda r: (not r["verified"], cost(r), r["area"], r["delay"])
    )

    # A waveform of the best circuit on one unseen sequence
    c = best["id"]
    length = 40
    row = int(y_test[:, :length].sum(dim=1).argmax())  # the busiest unseen sequence

    names, table = state_table(best["circuit"])

    def r4(values):
        return [round(v, 5) for v in values]

    median = lambda key: r4(torch.tensor(history[key]).median(dim=1).values.tolist())

    return {
        "settings": vars(args),
        "gate_area": GATE_AREA, "gate_delay": GATE_DELAY, "ff_area": FF_AREA,
        "num_ffs": k,
        "epoch": history["epoch"],
        "tau": r4(history["tau"]),
        "ramp": r4(history["ramp"]),
        "median": {
            key: median(key) for key in
            ["total", "task", "gate_cost", "delay_cost", "soft_area", "soft_delay", "train_acc"]
        },
        "task_per_circuit": [
            r4(list(col)) for col in zip(*history["task"])
        ],
        "eval_epoch": history["eval_epoch"],
        "eval": [
            {
                "verified": sum(r["verified"] for r in rows),
                "test_bit_median": sorted(r["test_bit"] for r in rows)[len(rows) // 2],
                "train_bit_median": sorted(r["train_bit"] for r in rows)[len(rows) // 2],
                "test_bit_best": max(r["test_bit"] for r in rows),
                "gates_verified": sorted(r["gates"] for r in rows if r["verified"]),
                "delay_verified": sorted(r["delay"] for r in rows if r["verified"]),
                "area_verified": sorted(r["area"] for r in rows if r["verified"]),
            }
            for rows in history["eval"]
        ],
        "final": [
            {key: r[key] for key in r if key != "circuit"} | {
                "nodes": r["circuit"]["nodes"],
                "d": r["circuit"]["d"],
                "z": r["circuit"]["z"],
            }
            for r in final
        ],
        "best": best["id"],
        "state_names": names,
        "state_table": table,
        "wave": {
            "x": x_test[row, :length].int().tolist(),
            "target": y_test[row, :length].int().tolist(),
            "z": z_all[c, row, :length].round().int().tolist(),
            "q": q_all[c, row, :length].round().int().T.tolist(),
        },
    }


def main():

    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])

    parser.add_argument("--circuits", type=int, default=64,
                        help="independent searches run as one batch")
    parser.add_argument("--nodes", type=int, default=8, help="gate nodes per circuit")
    parser.add_argument("--ffs", type=int, default=3, help="D flip-flops per circuit")
    parser.add_argument("--epochs", type=int, default=500)
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--noise", type=float, default=1.0,
                        help="Gumbel noise scale (0 = plain softmax)")
    parser.add_argument("--gate-weight", type=float, default=0.01,
                        help="penalty per gate equivalent of live area")
    parser.add_argument("--delay-weight", type=float, default=0.01,
                        help="penalty per NAND delay on the critical path")
    parser.add_argument("--out", default="seq_detector_out",
                        help="folder for the plot, JSON and interactive report")
    parser.add_argument("--compare", default=None,
                        help="history.json of another run to compare against in the report")

    parser.add_argument("--draw", default=None,
                        help="history.json of a finished run: redraw its circuit and loss plot, then exit")

    args = parser.parse_args()

    if args.draw:

        with open(args.draw) as f:
            saved = json.load(f)

        best = saved["final"][saved["best"]]
        folder = os.path.dirname(args.draw)
        draw_circuit(best, os.path.join(folder, "circuit.png"),
                     f"Best 1011 detector (search {best['id']}): {best['gates']} gates, "
                     f"{best['ffs']} flip-flops")
        plot_loss_html(saved, os.path.join(folder, "loss_vs_epoch.html"))
        print(f"saved {folder}/circuit.png and loss_vs_epoch.html")
        return

    model, history, test_data = search(
        seed=args.seed,
        circuits=args.circuits,
        num_nodes=args.nodes,
        num_ffs=args.ffs,
        epochs=args.epochs,
        noise=args.noise,
        gate_weight=args.gate_weight,
        delay_weight=args.delay_weight,
    )

    os.makedirs(args.out, exist_ok=True)

    data = report_data(model, history, test_data, args)

    # Optional second run (e.g. the same search without hardware costs), shown
    # next to this one in the report's area vs delay view.
    if args.compare:

        with open(args.compare) as f:
            other = json.load(f)

        data["compare"] = {
            "settings": other["settings"],
            "final": [
                {key: r[key] for key in ["id", "verified", "gates", "ffs", "area", "delay"]}
                for r in other["final"]
            ],
        }

    verified = [r for r in data["final"] if r["verified"]]

    print(
        f"\n{len(verified)}/{args.circuits} searches give a circuit that is correct "
        f"for every input sequence (checked exhaustively from reset)\n"
    )

    best = data["final"][data["best"]]

    print(
        f"Best circuit (search {best['id']}): {best['gates']} gates, "
        f"{best['ffs']} flip-flops, area {best['area']:.2f} GE, "
        f"critical path {best['delay']:.0f} NAND delays, "
        f"unseen-sequence bit accuracy {best['test_bit']:.4f}"
    )

    for line in best["lines"]:
        print("    " + line)

    print("\nState table it learned (" + ", ".join(data["state_names"]) + "):")
    print("    state | x=0: next, z | x=1: next, z")

    for row in data["state_table"]:
        print(f"    {row['state']:>5} | {row['next0']:>5}, {row['z0']}    "
              f"| {row['next1']:>5}, {row['z1']}")

    plot_loss(history, os.path.join(args.out, "loss_vs_epoch.png"))
    plot_loss_html(data, os.path.join(args.out, "loss_vs_epoch.html"))
    draw_circuit(best, os.path.join(args.out, "circuit.png"),
                 f"Best 1011 detector (search {best['id']}): {best['gates']} gates, "
                 f"{best['ffs']} flip-flops")

    with open(os.path.join(args.out, "history.json"), "w") as f:
        json.dump(data, f)

    # The interactive report is a template with the data dropped in.
    template = os.path.join(os.path.dirname(os.path.abspath(__file__)), "report_template.html")

    if os.path.exists(template):

        with open(template) as f:
            page = f.read().replace("__REPORT_DATA__", json.dumps(data))

        with open(os.path.join(args.out, "report.html"), "w") as f:
            f.write(page)

    print(f"\nsaved {args.out}/loss_vs_epoch.png, loss_vs_epoch.html, circuit.png, "
          f"history.json and report.html")


if __name__ == "__main__":
    main()