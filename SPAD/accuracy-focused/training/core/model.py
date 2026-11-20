"""Learned logic-gate layers: the shared building block, plus an older histogram model.

Two things live here.

1. GateLayer and light_gate. A layer is `width` two-input gates. Each gate has
   two routing vectors (which source signal feeds input a and input b) and a
   4-entry truth table. In training the routing is a softmax over sources and the
   truth table is four sigmoid probabilities, so the gate is a differentiable
   multilinear function (a DARTS-style relaxation). After hardening, each input
   is one source (argmax) and each table entry is 0 or 1. training.core.stream_model
   builds the photon-stream core from this class.

2. RecurrentLogic, Config and simulate_circuit. An earlier design that scans a
   stored 672-bin histogram one bin at a time and outputs a per-bin score, with
   the range being the earliest bin of maximum score. Nothing in the current
   stream pipeline imports it; it is kept as a reference for the histogram-based
   approach that the stream core replaces.

Time bins are 750 ps wide (about 0.1124 m of range each).
"""
from dataclasses import asdict, dataclass

import torch
from torch import nn


@dataclass
class Config:
    """Sizes for RecurrentLogic (histogram scanner).

    count_bits: bits of the per-bin photon count fed in (counts clamp at 2**count_bits - 1).
    position_bits: bits of the bin index fed in; must cover `bins`.
    state_bits: recurrent registers carried from one bin to the next.
    score_bits: width of the unsigned per-bin score the last layer emits.
    width: gates per layer; must be at least state_bits + score_bits.
    layers: number of gate layers.
    bins: histogram length (672 time bins of 750 ps).
    truncation: detach the state every `truncation` bins (0 = full backprop through time).
    """
    count_bits: int = 12
    position_bits: int = 10
    state_bits: int = 16
    score_bits: int = 8
    width: int = 24
    layers: int = 2
    bins: int = 672
    truncation: int = 32

    def __post_init__(self):
        if min(self.count_bits, self.state_bits, self.score_bits, self.layers) < 1:
            raise ValueError("Counts, state, score and layers must be positive")
        if self.width < self.state_bits + self.score_bits:
            raise ValueError("Last layer must hold both next-state and score bits")
        if self.position_bits < (self.bins - 1).bit_length():
            raise ValueError("Position counter cannot represent all histogram bins")
        if self.truncation < 0:
            raise ValueError("Truncation must be nonnegative (0 = full BPTT)")


def light_gate(a, b, table):
    """Evaluate a two-input gate as a multilinear function of a and b.

    a, b: tensors of values in [0, 1] (exactly 0 or 1 once hardened), any shape.
    table: [..., 4] output values for (a, b) = 00, 01, 10, 11, in that order.
    Returns a tensor broadcast over a, b and table's leading dimensions. For
    binary a, b and table it equals the plain Boolean gate.
    """
    return ((1-a) * (1-b) * table[..., 0] + (1-a) * b * table[..., 1]
            + a * (1-b) * table[..., 2] + a * b * table[..., 3])


class GateLayer(nn.Module):
    """One layer of `width` learnable two-input gates.

    Parameters:
      routes [width, 2, sources]: logits choosing which source signal drives
        input a (index 0) and input b (index 1) of each gate. These are the
        DARTS "architecture" parameters.
      table_logits [width, 4]: logits for the truth-table entries 00, 01, 10, 11.
        These are the "weight" parameters.
    `sources` is the number of signals the layer can read.
    """
    def __init__(self, sources, width):
        super().__init__()
        # Residual A initialization breaks gate/negation symmetry.
        self.table_logits = nn.Parameter(
            torch.tensor([-2., -2., 2., 2.]).repeat(width, 1)
            + torch.randn(width, 4) * 0.2)
        routes = torch.randn(width, 2, sources) * 0.01
        for i in range(width):
            routes[i, 0, i % sources] += 1.5
            routes[i, 1, (i * 7 + 1) % sources] += 1.5
        self.routes = nn.Parameter(routes)

    def prepared(self, temperature=1., hard=False, ste=False):
        """Return (routing [width, 2, sources], table [width, 4]) for the chosen mode.

        Soft (default): routing is softmax(routes / temperature), table is the
        sigmoid of its logits. A lower temperature makes routing closer to one-hot.
        hard: routing is one-hot at the argmax and table is thresholded at 0.5,
        so the layer is the exact discrete circuit (no gradient).
        ste (straight-through estimator): the forward value is the hard one, but
        the gradient is taken as if the soft value had been used. This is the
        `x + (hard - x).detach()` pattern below: it equals `hard` in value and
        `x` in gradient.
        """
        probabilities = (self.routes / temperature).softmax(-1)
        table = self.table_logits.sigmoid()
        if hard or ste:
            chosen = torch.nn.functional.one_hot(
                probabilities.argmax(-1), probabilities.shape[-1]).to(table.dtype)
            binary = (table > 0.5).to(table.dtype)
            if ste and not hard:
                probabilities = probabilities + (chosen - probabilities).detach()
                table = table + (binary - table).detach()
            else:
                probabilities, table = chosen, binary
        return probabilities, table


class RecurrentLogic(nn.Module):
    """Histogram scanner: gate layers run once per bin with recurrent state.

    Input is a [rays, bins] integer histogram. For each bin the base inputs are
    the count bits (LSB first), the bin index bits, constants 0 and 1, and the
    previous state. The last layer's first `state_bits` outputs are the next
    state and the next `score_bits` outputs are an unsigned score for that bin.
    forward() returns scores [rays, bins]; the range is the earliest argmax.
    """
    def __init__(self, config=None):
        super().__init__()
        self.config = config or Config()
        c = self.config
        self.external_bits = c.count_bits + c.position_bits + 2
        self.base_bits = self.external_bits + c.state_bits
        self.layers = nn.ModuleList([
            GateLayer(self.base_bits if i == 0 else self.base_bits + c.width, c.width)
            for i in range(c.layers)])
        # Start near a coarse peak detector instead of a random range prior.
        # Later layers initially forward the corresponding preceding gate.
        # Every connection remains searchable, including recurrent feedback.
        with torch.no_grad():
            for depth, layer in enumerate(self.layers):
                for i in range(c.width):
                    source = i % self.base_bits if depth == 0 else self.base_bits+i
                    if depth == 0 and c.state_bits <= i < c.state_bits+c.score_bits:
                        bit = i-c.state_bits + max(c.count_bits-c.score_bits, 0)
                        source = min(bit, c.count_bits-1)
                    layer.routes[i, 0].normal_(0, 0.01)
                    layer.routes[i, 0, source] += 3.
        positions = torch.arange(c.bins)[:, None]
        self.register_buffer("position", ((positions >> torch.arange(c.position_bits)) & 1).float())
        self.register_buffer("score_weights", 2. ** torch.arange(c.score_bits))

    def architecture_parameters(self):
        """Routing logits, optimized on the architecture split."""
        return [layer.routes for layer in self.layers]

    def weight_parameters(self):
        """Truth-table logits, optimized on the training split."""
        return [layer.table_logits for layer in self.layers]

    def forward(self, histograms, temperature=1., hard=False, ste=False):
        c = self.config
        if histograms.ndim != 2 or histograms.shape[1] != c.bins:
            raise ValueError(f"Expected [rays, {c.bins}] histograms")
        # ADC/count encoding is deterministic and identical in soft/hard models.
        counts = histograms.to(torch.int64).clamp(0, 2**c.count_bits - 1)
        encoded = ((counts[..., None] >> torch.arange(c.count_bits, device=counts.device)) & 1).float()
        prepared = [layer.prepared(temperature, hard, ste) for layer in self.layers]
        state = encoded.new_zeros((len(counts), c.state_bits))
        constants = encoded.new_tensor([0., 1.]).expand(len(counts), 2)
        scores = []
        for t in range(c.bins):
            if c.truncation and t and t % c.truncation == 0:
                state = state.detach()
            base = torch.cat((encoded[:, t], self.position[t].expand(len(counts), -1),
                              constants, state), -1)
            outputs = None
            for routing, table in prepared:
                sources = base if outputs is None else torch.cat((base, outputs), -1)
                if hard:
                    indices = routing.argmax(-1)
                    a, b = sources[:, indices[:, 0]], sources[:, indices[:, 1]]
                else:
                    a = sources @ routing[:, 0].T
                    b = sources @ routing[:, 1].T
                outputs = light_gate(a, b, table)
            state = outputs[:, :c.state_bits]
            scores.append(outputs[:, c.state_bits:c.state_bits+c.score_bits] @ self.score_weights)
        return torch.stack(scores, 1)

    @torch.no_grad()
    def circuit(self):
        """Export the hardened network as a JSON-serializable dictionary."""
        layers = []
        for layer in self.layers:
            routes, table = layer.prepared(hard=True)
            layers.append({"inputs": routes.argmax(-1).cpu().tolist(),
                           "truth_tables": table.int().cpu().tolist()})
        return {
            "format": "recurrent-light-logic-v1", "config": asdict(self.config),
            "truth_table_order": ["00", "01", "10", "11"],
            "input_order": "count bits LSB-first, bin index bits LSB-first, 0, 1, previous state",
            "layer_sources": "base inputs; append preceding layer outputs for layers > 0",
            "outputs": "first state_bits -> next state; next score_bits -> unsigned bin score",
            "reset": "state zeroed before each pixel histogram",
            "range_reducer": "earliest index of maximum unsigned bin score",
            "layers": layers,
        }


@torch.no_grad()
def simulate_circuit(circuit, histograms):
    """Independent integer implementation for exported-circuit equivalence checks."""
    c = Config(**circuit["config"])
    histograms = histograms.cpu().long().clamp(0, 2**c.count_bits-1)
    state = torch.zeros(len(histograms), c.state_bits, dtype=torch.long)
    result = []
    for t in range(c.bins):
        counts = (histograms[:, t, None] >> torch.arange(c.count_bits)) & 1
        position = ((torch.tensor(t) >> torch.arange(c.position_bits)) & 1).expand(len(counts), -1)
        base = torch.cat([counts, position, torch.zeros(len(counts), 1, dtype=torch.long),
                          torch.ones(len(counts), 1, dtype=torch.long), state], 1)
        output = None
        for layer in circuit["layers"]:
            pool = base if output is None else torch.cat([base, output], 1)
            inputs = torch.tensor(layer["inputs"])
            index = 2 * pool[:, inputs[:, 0]] + pool[:, inputs[:, 1]]
            table = torch.tensor(layer["truth_tables"])
            output = table[torch.arange(c.width)[None, :], index]
        state = output[:, :c.state_bits]
        result.append(output[:, c.state_bits:c.state_bits+c.score_bits] @ (2**torch.arange(c.score_bits)))
    return torch.stack(result, 1)
