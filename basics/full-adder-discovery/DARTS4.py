"""
Gate-level DARTS search for a full adder circuit.
Each gate node learns alpha (what gate it is) and beta_a / beta_b (what inputs it takes).
Every input is constructed by an acyclic graph of nodes, where each node is guaranteed
to use a previous signal that existed before it.
Gamma picks which nodes drive Sum and Cout.
"""

import torch
import torch.nn as nn
import torch.nn.functional as F
import argparse
from pathlib import Path
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
def gate_xnor(a, b): return 1 - (a + b - 2 * a * b)


# Names of each gate
GATES = {
    "NOT": (gate_not, 1),
    "AND": (gate_and, 2),
    "OR": (gate_or, 2),
    "XOR": (gate_xor, 2),
    "NAND": (gate_nand, 2),
    "NOR": (gate_nor, 2),
    "XNOR": (gate_xnor, 2),
}


# Every 0/1 input combination as a float tensor
def truth_table(num_inputs):
    rows = [
        [(i >> bit) & 1 for bit in reversed(range(num_inputs))]
        for i in range(2 ** num_inputs)
    ]  # generate all combinations of 0s and 1s for the given number of inputs

    return torch.tensor(rows, dtype=torch.float32)


GATE_NAMES = list(GATES)
INPUT_NAMES = ["A", "B", "Cin"]
OUTPUT_NAMES = ["Sum", "Cout"]
NUM_INPUTS = len(INPUT_NAMES)


def full_adder_table():
    x = truth_table(NUM_INPUTS)  # all combinations of A, B, Cin
    total = x.sum(dim=1)

    y = torch.stack(
        [total % 2, (total >= 2).float()],
        dim=1
    )  # Sum, Cout

    return x, y


# Gumbel noise to occasionally give less favored operations a greater influence during training
def gumbel(t):
    u = torch.rand_like(t).clamp(1e-6, 1 - 1e-6)
    return -torch.log(-torch.log(u))


# Train independent candidate circuits together as one batch; this samples
# several searches, rather than enumerating every possible circuit.
class GateCircuits(nn.Module):

    def __init__(self, num_circuits, num_nodes=8, num_outputs=2, init_std=1.0):
        super().__init__()

        self.num_nodes = num_nodes
        sources = NUM_INPUTS + num_nodes

        # These parameters are choice scores (logits), not fixed gate weights:
        # alpha chooses the gate, beta_a/b choose its wires, and gamma chooses
        # the output nodes. Softmax turns each set of scores into a soft choice.
        self.alpha = nn.Parameter(
            init_std * torch.randn(num_circuits, num_nodes, len(GATE_NAMES))
        )

        self.beta_a = nn.Parameter(
            init_std * torch.randn(num_circuits, num_nodes, sources)
        )

        self.beta_b = nn.Parameter(
            init_std * torch.randn(num_circuits, num_nodes, sources)
        )

        self.gamma = nn.Parameter(
            init_std * torch.randn(num_circuits, num_outputs, num_nodes)
        )

        # Keep the circuits acyclic
        mask = torch.full((num_nodes, sources), float("-inf"))

        for i in range(num_nodes):
            mask[i, :NUM_INPUTS + i] = 0

        # Adding -inf makes forbidden sources have exactly zero softmax weight.
        # Node i can read A/B/Cin and earlier nodes, never itself or later nodes.
        # A buffer follows the model's device but is not trained by the optimizer.
        self.register_buffer("mask", mask)

    def forward(self, x, tau=1.0, noise=0.0):

        def weights(scores, extra=0):
            if noise:
                scores = scores + noise * gumbel(scores)

            # Lower temperature makes choices sharper; higher temperature mixes
            # candidates more evenly. They remain soft during the forward pass.
            return F.softmax((scores + extra) / tau, dim=-1)

        w_gate = weights(self.alpha)
        w_a = weights(self.beta_a, self.mask)
        w_b = weights(self.beta_b, self.mask)
        w_out = weights(self.gamma)

        circuits = self.alpha.shape[0]

        # (circuits, rows, sources)
        signals = x.unsqueeze(0).expand(circuits, -1, -1)

        for i in range(self.num_nodes):

            # Select the two inputs for the current gate
            # Each input is a weighted sum of available signals, not yet one wire.
            # In einsum: c = circuit, r = truth-table row, s = source.
            # Summing over s preserves one value per circuit and truth-table row.
            a = torch.einsum(
                "crs,cs->cr",
                signals,
                w_a[:, i, :signals.shape[-1]]
            )

            b = torch.einsum(
                "crs,cs->cr",
                signals,
                w_b[:, i, :signals.shape[-1]]
            )

            # Evaluate every possible gate operation
            outs = torch.stack(
                [
                    fn(a) if arity == 1 else fn(a, b)
                    for fn, arity in GATES.values()
                ],
                dim=-1
            )

            # Weighted combination of candidate gate outputs
            # Like DARTS2's prediction, this blends operations so the loss can
            # differentiate with respect to which gate the node should become.
            node_output = (
                outs * w_gate[:, i, None, :]
            ).sum(dim=-1)

            # Add the new node to the available signals
            signals = torch.cat(
                [signals, node_output.unsqueeze(-1)],
                dim=-1
            )

        # Select which gate nodes drive Sum and Cout
        # n = gate node and o = output; sum over n to blend nodes for each output.
        return torch.einsum(
            "crn,con->cro",
            signals[:, :, NUM_INPUTS:],
            w_out
        )  # (circuits, rows, outputs)

    # argmax of every choice for circuit c: a list of (gate, src_a, src_b) and the output nodes
    def extract(self, c):

        # Argmax replaces each soft mixture with one gate/wire/output choice.
        # A good soft circuit may become wrong after this discrete conversion,
        # so the extracted circuit must be checked separately below.
        gates = self.alpha[c].argmax(-1).tolist()

        src_a = (
            self.beta_a[c] + self.mask
        ).argmax(-1).tolist()

        src_b = (
            self.beta_b[c] + self.mask
        ).argmax(-1).tolist()

        nodes = [
            (GATE_NAMES[g], a, b)
            for g, a, b in zip(gates, src_a, src_b)
        ]

        outputs = self.gamma[c].argmax(-1).tolist()

        return nodes, outputs


# evaluate an extracted circuit with discrete boolean gates
def run_discrete(nodes, outputs, x):

    signals = [x[:, i] for i in range(NUM_INPUTS)]

    for gate, a, b in nodes:

        fn, arity = GATES[gate]

        signals.append(
            fn(signals[a])
            if arity == 1
            else fn(signals[a], signals[b])
        )

    return torch.stack(
        [signals[NUM_INPUTS + o] for o in outputs],
        dim=1
    )


# indices of the gate nodes the outputs depend on
def prune(nodes, outputs):

    # Walk backward from Sum/Cout: nodes that neither output depends on can
    # be omitted from the description without changing the circuit's behavior.
    used, stack = set(), list(outputs)

    while stack:

        i = stack.pop()

        if i in used:
            continue

        used.add(i)

        gate, a, b = nodes[i]

        for src in [a] if GATES[gate][1] == 1 else [a, b]:

            if src >= NUM_INPUTS:
                stack.append(src - NUM_INPUTS)

    return sorted(used)


def describe(nodes, outputs):

    def name(src):
        return (
            INPUT_NAMES[src]
            if src < NUM_INPUTS
            else f"n{src - NUM_INPUTS}"
        )

    lines = []

    for i in prune(nodes, outputs):

        gate, a, b = nodes[i]

        args = (
            name(a)
            if GATES[gate][1] == 1
            else f"{name(a)}, {name(b)}"
        )

        lines.append(f"n{i} = {gate}({args})")

    for out_name, o in zip(OUTPUT_NAMES, outputs):
        lines.append(f"{out_name} = n{o}")

    return lines


def search(
    seed=0,
    circuits=64,
    num_nodes=8,
    steps=3000,
    lr=0.05,
    tau_start=1.0,
    tau_end=0.3,
    noise=1.0,
    history=None
):

    # If a list is passed as history, each step appends one loss per circuit,
    # so main() can plot training progress without changing results.
    torch.manual_seed(seed)

    x, y = full_adder_table()

    model = GateCircuits(circuits, num_nodes)

    opt = torch.optim.Adam(model.parameters(), lr=lr)

    for step in range(steps):

        # Geometric temperature annealing
        # Start with broader mixtures, then encourage more decisive choices as
        # training progresses. This does not guarantee an exact discrete circuit.
        tau = tau_start * (
            tau_end / tau_start
        ) ** (step / max(steps - 1, 1))

        # BCE uses logarithms; avoid log(0) at exact 0/1 predictions.
        pred = model(x, tau, noise).clamp(1e-6, 1 - 1e-6)

        # Sum over circuits so each circuit gets the same gradient it would get alone.
        # BCE penalizes disagreement with each target bit. Average over the eight
        # input rows and two output bits separately for each independent circuit.
        loss = F.binary_cross_entropy(
            pred,
            y.expand_as(pred),
            reduction="none"
        ).mean(dim=(1, 2))

        if history is not None:
            history.append(loss.detach().tolist())

        loss = loss.sum()

        opt.zero_grad()
        # Gradients flow through gate formulas and all soft choices, letting Adam
        # learn the circuit structure itself (gate types, wiring, and outputs).
        loss.backward()
        opt.step()

    results = []

    with torch.no_grad():

        for c in range(circuits):

            nodes, outputs = model.extract(c)

            # Testing every input combination proves correctness for this Boolean
            # task; a low training loss alone does not prove the hard circuit works.
            exact = torch.equal(
                run_discrete(nodes, outputs, x),
                y
            )

            results.append((nodes, outputs, exact))

    return results


def main():

    parser = argparse.ArgumentParser(
        description=__doc__.splitlines()[0]
    )

    parser.add_argument(
        "--circuits",
        type=int,
        default=64,
        help="independent searches run as one batch"
    )

    parser.add_argument(
        "--nodes",
        type=int,
        default=8,
        help="gate nodes per circuit"
    )

    parser.add_argument(
        "--steps",
        type=int,
        default=3000
    )

    parser.add_argument(
        "--seed",
        type=int,
        default=0
    )

    parser.add_argument(
        "--noise",
        type=float,
        default=1.0,
        help="Gumbel noise scale (0 = plain softmax)"
    )

    args = parser.parse_args()

    history = []

    results = search(
        args.seed,
        args.circuits,
        args.nodes,
        args.steps,
        noise=args.noise,
        history=history
    )

    exact = [
        (nodes, outputs)
        for nodes, outputs, ok in results
        if ok
    ]

    print(
        f"{len(exact)}/{len(results)} searches extracted an exact full adder\n"
    )

    # Show each distinct exact circuit once, smallest first.
    seen = {}

    for nodes, outputs in exact:

        lines = tuple(describe(nodes, outputs))

        seen.setdefault(lines, 0)
        seen[lines] += 1

    for lines, count in sorted(
        seen.items(),
        key=lambda kv: len(kv[0])
    ):

        print(
            f"{len(lines) - len(OUTPUT_NAMES)} gates (found {count}x):"
        )

        for line in lines:
            print("    " + line)

        print()

    plot_loss(history, [ok for _, _, ok in results])


# Average of the last `window` steps at every step (fewer at the start), for each circuit
def moving_average(losses, window):

    totals = torch.cat([torch.zeros(1, losses.shape[1]), losses.cumsum(dim=0)])
    steps = torch.arange(1, losses.shape[0] + 1)
    starts = (steps - window).clamp(min=0)

    return (totals[steps] - totals[starts]) / (steps - starts).unsqueeze(1)


# Smoothed loss of every exact circuit against iterations, with their median on top
def plot_loss(history, exact, window=50, path=Path(__file__).parent / "figures" / "darts4_loss.png"):

    if not any(exact):
        print("no exact circuits, so no loss graph")
        return

    # (steps, circuits), keeping only circuits whose extracted circuit is an exact full adder
    losses = torch.tensor(history)[:, torch.tensor(exact)]

    # The Gumbel noise makes the raw loss jump around, so smooth each circuit first.
    losses = moving_average(losses, window)

    fig, ax = plt.subplots(figsize=(8, 4.5))

    # Each circuit is an independent search, so draw them all faintly.
    ax.plot(losses, color="#9a9a94", linewidth=0.6, alpha=0.25)
    ax.plot([], [], color="#9a9a94", linewidth=1, label="each exact circuit")

    # The median is not dragged around by a few unusual circuits.
    ax.plot(
        losses.median(dim=1).values,
        color="#2a78d6",
        linewidth=2,
        label="median of exact circuits"
    )

    # BCE drops by orders of magnitude, so a log axis keeps late progress visible.
    ax.set_yscale("log")
    ax.set_xlabel("Iteration")
    ax.set_ylabel(f"BCE loss per circuit ({window}-step moving average)")
    ax.set_title(
        f"Full adder search: loss of the {sum(exact)}/{len(exact)} exact circuits",
        loc="left"
    )

    ax.grid(True, color="#e1e0d9", linewidth=0.8)
    ax.spines[["top", "right"]].set_visible(False)
    ax.legend(frameon=False)

    fig.tight_layout()
    path.parent.mkdir(parents=True, exist_ok=True)  # create figures/ if it is missing
    fig.savefig(path, dpi=150)
    print(f"saved {path}")

    plt.show()


if __name__ == "__main__":
    main()
