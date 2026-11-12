"""Free-form photon-stream core: nothing but learned gates and flip-flops.

The other SPAD models give the learner a fixed datapath (a candidate register, a
comparator with distance flags, a confidence counter) and learn only a small
controller. This one assumes none of that. Per photon, the circuit sees:

  the raw arrival time as `arrival_bits` binary wires, const0, const1,
  and its own `state_bits` flip-flops (all zero before the first photon).

Layers of two-input gates follow. A gate may read any input, any flip-flop, or any
gate in an earlier layer; the wiring is learned (DARTS softmax routing) and so is
each gate's 4-entry truth table. The first `state_bits` gates of the last layer
are the flip-flops' next values. After the last photon, flip-flops 0..arrival_bits-1
are read as a binary number: the range bin.

Two things are still decided by hand, because a circuit needs an interface: the
input is a binary arrival time, and the output is a binary number in named
flip-flops. Flip-flops hold their value on clocks without a photon (a clock enable).
"""
from dataclasses import asdict, dataclass

import torch
from torch import nn

FORMAT = "photon-free-core-v1"


@dataclass
class FreeConfig:
    state_bits: int = 32
    width: int = 48
    layers: int = 4
    arrival_bits: int = 10

    def __post_init__(self):
        if self.width < self.state_bits:
            raise ValueError("Last layer must hold every flip-flop's next value")
        if self.state_bits < self.arrival_bits:
            raise ValueError("Need at least arrival_bits flip-flops to hold the answer")
        if self.layers < 1:
            raise ValueError("Need at least one layer")

    @property
    def base_bits(self):
        return self.arrival_bits + 2 + self.state_bits

    def sources(self, layer):
        """How many wires a gate in `layer` may read: inputs, flip-flops, all earlier gates."""
        return self.base_bits + self.width * layer


def input_names(c):
    return ([f"arrival{i}" for i in range(c.arrival_bits)] + ["const0", "const1"]
            + [f"state{i}" for i in range(c.state_bits)])


def photon_bits(photons, bits):
    """[rays, steps] arrival bins -> ([steps, rays, bits] 0/1 floats LSB first, [steps, rays] valid)."""
    valid = photons >= 0
    value = photons.clamp(min=0).long()
    planes = (value[..., None] >> torch.arange(bits, device=photons.device)) & 1
    return planes.transpose(0, 1).float().contiguous(), valid.T.contiguous()


class FreeCore(nn.Module):
    def __init__(self, config=None, init="residual"):
        super().__init__()
        self.config = c = config or FreeConfig()
        self.routes = nn.ParameterList()
        self.table_logits = nn.ParameterList()
        for layer in range(c.layers):
            sources = c.sources(layer)
            routes = torch.randn(c.width, 2, sources) * .01
            picks = torch.randint(sources, (c.width, 2))
            routes.scatter_add_(-1, picks[..., None], torch.full((c.width, 2, 1), 2.))
            if init == "residual":
                # Generic, not task-specific: each gate starts by passing on its first
                # (randomly chosen) input, so signals and gradients cross layers and time.
                tables = torch.tensor([-2., -2., 2., 2.]).repeat(c.width, 1) + torch.randn(c.width, 4) * .5
            else:
                tables = torch.randn(c.width, 4)
            self.routes.append(nn.Parameter(routes))
            self.table_logits.append(nn.Parameter(tables))

    def architecture_parameters(self):
        return list(self.routes)

    def weight_parameters(self):
        return list(self.table_logits)

    def forward(self, photons, temperature=1., ste=False, trajectory=False):
        """Soft (or straight-through binary) pass. Returns the range as a float per ray.

        With trajectory=True, returns (values [steps, rays], output bits [steps, rays, arrival_bits]):
        the answer the circuit would give if read out after each photon.
        """
        c = self.config
        layers = []
        for routes, logits in zip(self.routes, self.table_logits):
            probabilities = (routes / temperature).softmax(-1)
            table = logits.sigmoid()
            if ste:
                chosen = torch.nn.functional.one_hot(probabilities.argmax(-1), probabilities.shape[-1]).to(table.dtype)
                probabilities = probabilities + (chosen - probabilities).detach()
                table = table + ((table > .5).to(table.dtype) - table).detach()
            width, _, sources = probabilities.shape
            weight = probabilities.transpose(0, 1).reshape(2 * width, sources).T   # all a inputs, then all b
            t00, t01, t10, t11 = table.unbind(-1)
            layers.append((weight, t00, t01 - t00, t10 - t00, t11 - t10 - t01 + t00))
        bits, valid = photon_bits(photons, c.arrival_bits)
        rays = len(photons)
        state = bits.new_zeros(rays, c.state_bits)
        consts = torch.tensor([0., 1.], device=bits.device).expand(rays, 2)
        readouts = []
        for k in range(len(bits)):
            sources = torch.cat((bits[k], consts, state), -1)
            for weight, c0, cb, ca, cab in layers:
                a, b = (sources @ weight).chunk(2, -1)
                out = c0 + a * ca + b * cb + a * b * cab
                sources = torch.cat((sources, out), -1)
            state = torch.where(valid[k][:, None], out[:, :c.state_bits], state)
            if trajectory:
                readouts.append(state[:, :c.arrival_bits])
        weights = 2. ** torch.arange(c.arrival_bits, device=bits.device)
        if trajectory:
            output = torch.stack(readouts)
            return output @ weights, output
        return state[:, :c.arrival_bits] @ weights

    @torch.no_grad()
    def circuit(self):
        layers = [{"inputs": routes.argmax(-1).tolist(), "truth_tables": (logits > 0).int().tolist()}
                  for routes, logits in zip(self.routes, self.table_logits)]
        return {"format": FORMAT, "config": asdict(self.config), "inputs": input_names(self.config),
                "output": [f"state{i}" for i in range(self.config.arrival_bits)], "layers": layers}

    @torch.no_grad()
    def load_circuit(self, circuit, sharpness=4.):
        for routes, logits, spec in zip(self.routes, self.table_logits, circuit["layers"]):
            routes.normal_(0, .01)
            routes.scatter_add_(-1, torch.tensor(spec["inputs"], device=routes.device)[..., None],
                                torch.full((*routes.shape[:2], 1), sharpness, device=routes.device))
            logits.copy_((torch.tensor(spec["truth_tables"], device=logits.device).float() * 2 - 1) * sharpness / 2)


@torch.no_grad()
def simulate_free(circuit, photons):
    """Plain integer simulation of an exported circuit, one photon at a time. The reference."""
    c = FreeConfig(**circuit["config"])
    device = photons.device
    rays = len(photons)
    state = torch.zeros(rays, c.state_bits, dtype=torch.long, device=device)
    specs = [(torch.tensor(x["inputs"], device=device), torch.tensor(x["truth_tables"], device=device))
             for x in circuit["layers"]]
    gates = torch.arange(c.width, device=device)[None]
    shifts = torch.arange(c.arrival_bits, device=device)
    consts = torch.tensor([0, 1], device=device).expand(rays, 2)
    for step in range(photons.shape[1]):
        arrival, valid = photons[:, step].long(), photons[:, step] >= 0
        pool = torch.cat(((arrival.clamp(min=0)[:, None] >> shifts) & 1, consts, state), 1)
        for inputs, tables in specs:
            output = tables[gates, 2 * pool[:, inputs[:, 0]] + pool[:, inputs[:, 1]]]
            pool = torch.cat((pool, output), 1)
        state = torch.where(valid[:, None], output[:, :c.state_bits], state)
    return (state[:, :c.arrival_bits] << shifts).sum(-1)


def pack_circuit(circuit, device=None):
    """Wiring [layers, width, 2] and truth tables as 4-bit codes [layers, width] (bit 2a+b)."""
    inputs = torch.tensor([x["inputs"] for x in circuit["layers"]], device=device)
    tables = torch.tensor([x["truth_tables"] for x in circuit["layers"]], device=device)
    return inputs, (tables << torch.arange(4, device=device)).sum(-1).int()


def unpack_circuit(template, inputs, codes):
    circuit = {key: value for key, value in template.items() if key != "layers"}
    circuit["layers"] = [{"inputs": wires.tolist(), "truth_tables": [[(code >> bit) & 1 for bit in range(4)] for code in row]}
                         for wires, row in zip(inputs.cpu(), codes.cpu().tolist())]
    return circuit


def _pack_bits(bits):
    """Booleans [..., rays] -> int64 words [..., ceil(rays/64)], 64 rays per word."""
    rays = bits.shape[-1]
    words = -(-rays // 64)
    bits = torch.nn.functional.pad(bits.long(), (0, words * 64 - rays)).reshape(*bits.shape[:-1], words, 64)
    return (bits << torch.arange(64, device=bits.device)).sum(-1)   # distinct powers: sum is OR


def _unpack_bits(words, rays):
    shifts = torch.arange(64, device=words.device)
    return ((words[..., None] >> shifts) & 1).reshape(*words.shape[:-1], -1)[..., :rays]


def pack_photons(photons, bits):
    """Pack once per photon sample: (arrival planes [steps, bits, words], valid [steps, words])."""
    value = photons.clamp(min=0).long()
    planes = ((value.T[:, None] >> torch.arange(bits, device=photons.device)[None, :, None]) & 1)
    return _pack_bits(planes), _pack_bits((photons >= 0).T)


@torch.no_grad()
def simulate_population_packed(config, inputs, codes, packed, rays, readouts=None):
    """Exact simulation of many circuits at once, 64 rays per machine word.

    inputs [members, layers, width, 2], codes [members, layers, width], packed from
    pack_photons. Returns range bins [members, rays], or with `readouts` (photon counts,
    e.g. (16, 64)) the answers read out after each of those photons [len(readouts) + 1, members,
    rays], the last row being the final answer. Each gate is evaluated in
    algebraic normal form: t00 ^ a&(t00^t10) ^ b&(t00^t01) ^ a&b&(t00^t01^t10^t11).
    """
    c = config
    planes, valid = packed
    members, words = len(inputs), planes.shape[-1]
    mask = lambda bit: -(bit.long())[..., None]                     # 0 or all ones, [members, width, 1]
    layers = []
    for layer in range(c.layers):
        code = codes[:, layer].long()
        t00, t01, t10, t11 = (code & 1, (code >> 1) & 1, (code >> 2) & 1, (code >> 3) & 1)
        index = inputs[:, layer].long()
        layers.append((index[:, :, 0, None].expand(-1, -1, words), index[:, :, 1, None].expand(-1, -1, words),
                       mask(t00), mask(t00 ^ t10), mask(t00 ^ t01), mask(t00 ^ t01 ^ t10 ^ t11)))
    state = torch.zeros(members, c.state_bits, words, dtype=torch.long, device=planes.device)
    consts = torch.stack((torch.zeros(words, dtype=torch.long, device=planes.device),
                          torch.full((words,), -1, dtype=torch.long, device=planes.device)))[None].expand(members, -1, -1)
    shifts = torch.arange(c.arrival_bits, device=planes.device)[None, :, None]
    value = lambda s: (_unpack_bits(s[:, :c.arrival_bits], rays) << shifts).sum(1)
    marks, taken = set(readouts or ()), []
    for k in range(len(planes)):
        pool = torch.cat((planes[k][None].expand(members, -1, -1), consts, state), 1)
        for ia, ib, m0, ma, mb, mab in layers:
            a, b = pool.gather(1, ia), pool.gather(1, ib)
            out = m0 ^ (a & ma) ^ (b & mb) ^ (a & b & mab)
            pool = torch.cat((pool, out), 1)
        keep = valid[k]
        state = (out[:, :c.state_bits] & keep) | (state & ~keep)
        if k + 1 in marks:
            taken.append(value(state))
    if readouts is None:
        return value(state)
    return torch.stack(taken + [value(state)])


def live_gates(circuit):
    """Gates that can influence a flip-flop the answer depends on, and the flip-flops in use."""
    c = FreeConfig(**circuit["config"])
    base = c.base_bits
    first_state = c.arrival_bits + 2
    reads = {}                                                       # wire index -> wires it reads
    for layer, spec in enumerate(circuit["layers"]):
        for gate, (a, b) in enumerate(spec["inputs"]):
            table = spec["truth_tables"][gate]
            uses_a = table[0] != table[2] or table[1] != table[3]
            uses_b = table[0] != table[1] or table[2] != table[3]
            reads[base + layer * c.width + gate] = [w for w, used in ((a, uses_a), (b, uses_b)) if used]
    last = base + (c.layers - 1) * c.width
    live, flops, stack = set(), set(), list(range(c.arrival_bits))  # start from the output flip-flops
    while stack:
        flop = stack.pop()
        if flop in flops:
            continue
        flops.add(flop)
        wires = [last + flop]
        while wires:
            w = wires.pop()
            if w >= base:
                if w not in live:
                    live.add(w)
                    wires += reads[w]
            elif w >= first_state:
                stack.append(w - first_state)
    return {"live_gates": len(live), "total_gates": c.layers * c.width, "flip_flops_used": len(flops)}
