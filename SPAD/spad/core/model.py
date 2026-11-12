"""Recurrent light logic gates with first-order DARTS input routing.

Inference uses Boolean gates, registers, and an integer argmax over bin scores.
Softmax over time is exclusively a training loss, never an inference operation.
"""
from dataclasses import asdict, dataclass

import torch
from torch import nn


@dataclass
class Config:
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
    """Multilinear interpolation; truth-table order is 00, 01, 10, 11."""
    return ((1-a) * (1-b) * table[..., 0] + (1-a) * b * table[..., 1]
            + a * (1-b) * table[..., 2] + a * b * table[..., 3])


class GateLayer(nn.Module):
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
        return [layer.routes for layer in self.layers]

    def weight_parameters(self):
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
