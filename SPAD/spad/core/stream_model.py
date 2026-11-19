"""Per-pixel photon-stream core: fixed datapath, learned logic-gate controller.

Each pixel holds a candidate bin, a saturating confidence counter and a few
learned state bits, and no histogram. Per photon, the datapath compares the
arrival with the candidate. The controller maps those comparison flags and its
own state to actions. After the photon budget, the candidate is the range bin.
Distances enter as thermometer flags, because Boolean gates use them directly.
"""
from dataclasses import asdict, dataclass

import torch
from torch import nn

from spad.core.model import GateLayer, light_gate

ACTIONS = ("replace", "up", "down", "inc", "dec")
CONF_LEVELS = (2, 4, 8)


@dataclass
class StreamConfig:
    state_bits: int = 4
    width: int = 16
    layers: int = 3
    conf_bits: int = 4
    cand_bits: int = 10
    windows: tuple = (1, 2, 4, 8, 16)

    def __post_init__(self):
        self.windows = tuple(self.windows)
        if self.width < self.state_bits + len(ACTIONS):
            raise ValueError("Last layer must hold next state and all actions")
        if self.layers < 1 or self.conf_bits < 4 or self.state_bits < 0:
            raise ValueError("Need a layer, four confidence bits and nonnegative state")


def input_names(c):
    return ([f"near{w}" for w in c.windows] + ["gt", "lt", "zero"]
            + [f"conf{level}" for level in CONF_LEVELS] + ["full", "const0", "const1"]
            + [f"state{i}" for i in range(c.state_bits)])


def _flag(hard, soft, mode):
    """Boolean forward value; the surrogate supplies gradients unless fully soft."""
    return soft if mode == "soft" else soft + (hard.float() - soft).detach()


class StreamCore(nn.Module):
    def __init__(self, config=None):
        super().__init__()
        self.config = c = config or StreamConfig()
        self.base_bits = len(input_names(c))
        self.layers = nn.ModuleList([
            GateLayer(self.base_bits if i == 0 else self.base_bits + c.width, c.width)
            for i in range(c.layers)])
        with torch.no_grad():
            state = self.base_bits - c.state_bits
            for layer in self.layers:
                layer.routes.normal_(0, 0.01)
                sources = layer.routes.shape[-1]
                picks = torch.randint(sources, (c.width, 2))
                layer.routes.scatter_add_(-1, picks[..., None], torch.full((c.width, 2, 1), 2.))
                layer.table_logits.copy_(torch.randn(c.width, 4))
            # Every state bit starts as a feedback loop through the last layer.
            last = self.layers[-1]
            for i in range(c.state_bits):
                last.routes[i, 0].normal_(0, 0.01)
                last.routes[i, 0, state + i] += 3.
                last.table_logits[i] = torch.tensor([-2., -2., 2., 2.])

    def architecture_parameters(self):
        return [layer.routes for layer in self.layers]

    def weight_parameters(self):
        return [layer.table_logits for layer in self.layers]

    def features(self, candidate, confidence, arrival, state, mode):
        c = self.config
        distance = arrival - candidate
        size = distance.abs()
        flags = [_flag(size <= w, ((w + .5 - size) / (.25*w + 1)).sigmoid(), mode) for w in c.windows]
        flags += [_flag(distance > 0, (distance - .5).sigmoid(), mode),
                  _flag(distance < 0, (-distance - .5).sigmoid(), mode),
                  _flag(confidence < 1, (.5 - confidence).sigmoid(), mode)]
        flags += [_flag(confidence >= level, (confidence - level + .5).sigmoid(), mode) for level in CONF_LEVELS]
        top = 2**c.conf_bits - 1
        flags += [_flag(confidence >= top, (confidence - top + .5).sigmoid(), mode),
                  torch.zeros_like(size), torch.ones_like(size)]
        return torch.cat((torch.stack(flags, -1), state), -1)

    def forward_reference(self, photons, temperature=1., hard=False, ste=False):
        """Original, unfused forward. Kept to check forward() against."""
        c = self.config
        mode = "soft" if not (hard or ste) else "binary"
        prepared = [layer.prepared(temperature, hard, ste) for layer in self.layers]
        rays = len(photons)
        candidate = photons.new_zeros(rays, dtype=torch.float32)
        confidence = torch.zeros_like(candidate)
        state = candidate.new_zeros(rays, c.state_bits)
        top_c, top_q = 2**c.cand_bits - 1, 2**c.conf_bits - 1
        for step in range(photons.shape[1]):
            arrival = photons[:, step].float()
            valid = photons[:, step] >= 0
            base = self.features(candidate, confidence, arrival, state, mode)
            outputs = None
            for routing, table in prepared:
                sources = base if outputs is None else torch.cat((base, outputs), -1)
                if hard:
                    index = routing.argmax(-1)
                    a, b = sources[:, index[:, 0]], sources[:, index[:, 1]]
                else:
                    a, b = sources @ routing[:, 0].T, sources @ routing[:, 1].T
                outputs = light_gate(a, b, table)
            new_state = outputs[:, :c.state_bits]
            replace, up, down, inc, dec = outputs[:, c.state_bits:c.state_bits+len(ACTIONS)].unbind(-1)
            stepped = (candidate + up - down).clamp(0, top_c)
            new_candidate = stepped + replace * (arrival - stepped)
            new_confidence = (confidence + inc - dec).clamp(0, top_q)
            candidate = torch.where(valid, new_candidate, candidate)
            confidence = torch.where(valid, new_confidence, confidence)
            state = torch.where(valid[:, None], new_state, state)
        return candidate

    # ------------------------------------------------------------------ fused forward
    # Same mathematics as forward_reference with far fewer operations per photon, so a
    # GPU spends less time launching tiny kernels: all window and confidence flags in
    # one comparison each, one matmul per layer for both gate inputs, and the gate's
    # bilinear coefficients computed once per pass instead of once per photon.
    # set_compile() can additionally fuse the per-photon step with torch.compile.

    _compiled = None

    def set_compile(self, mode=None):
        """mode: None (eager), "default", or "reduce-overhead" (CUDA graphs)."""
        self._compiled = None if not mode else torch.compile(_fused_step, mode=mode, dynamic=False)
        return self

    def forward(self, photons, temperature=1., hard=False, ste=False):
        if hard:
            return self.forward_reference(photons, temperature, hard=True)   # exact discrete path
        c = self.config
        binary = ste
        layers = []
        for layer in self.layers:
            routing, table = layer.prepared(temperature, False, ste)
            width, _, sources = routing.shape
            weight = routing.transpose(0, 1).reshape(2 * width, sources).T     # [sources, 2*width]: all a, then all b
            c0, c1, c2, c3 = table.unbind(-1)
            layers.append((weight, c0, c1 - c0, c2 - c0, c3 - c2 - c1 + c0))
        device = photons.device
        windows = torch.tensor(c.windows, dtype=torch.float32, device=device)
        top_q = 2**c.conf_bits - 1
        levels = torch.tensor(list(CONF_LEVELS) + [top_q], dtype=torch.float32, device=device)
        rays = len(photons)
        candidate = torch.zeros(rays, dtype=torch.float32, device=device)
        confidence = torch.zeros_like(candidate)
        state = candidate.new_zeros(rays, c.state_bits)
        consts = torch.tensor([0., 1.], device=device).expand(rays, 2)
        arrivals = photons.float().T.contiguous()
        valids = (photons >= 0).T.contiguous()
        start = (candidate, confidence, state)
        if self._compiled is not None:
            try:
                return self._run(self._compiled, start, arrivals, valids, windows, levels, consts, layers, binary)
            except Exception as error:    # a compile mode the device cannot run: keep training, uncompiled
                print(f"torch.compile failed ({type(error).__name__}); continuing without it", flush=True)
                self._compiled = None
        return self._run(_fused_step, start, arrivals, valids, windows, levels, consts, layers, binary)

    def _run(self, step, start, arrivals, valids, windows, levels, consts, layers, binary):
        c = self.config
        candidate, confidence, state = start
        for k in range(len(arrivals)):
            candidate, confidence, state = step(candidate, confidence, state, arrivals[k], valids[k], windows,
                                                levels, consts, layers, binary, c.state_bits,
                                                float(2**c.cand_bits - 1), float(2**c.conf_bits - 1))
        return candidate

    @torch.no_grad()
    def circuit(self):
        layers = []
        for layer in self.layers:
            routes, table = layer.prepared(hard=True)
            layers.append({"inputs": routes.argmax(-1).tolist(), "truth_tables": table.int().tolist()})
        return {"format": "photon-stream-core-v1", "config": asdict(self.config),
                "inputs": input_names(self.config), "actions": list(ACTIONS), "layers": layers}

    @torch.no_grad()
    def load_circuit(self, circuit, sharpness=4.):
        """Set logits so the hard model equals a circuit, with room to keep learning."""
        for layer, spec in zip(self.layers, circuit["layers"]):
            layer.routes.normal_(0, 0.01)
            device = layer.routes.device
            layer.routes.scatter_add_(-1, torch.tensor(spec["inputs"], device=device)[..., None],
                                      torch.full((*layer.routes.shape[:2], 1), sharpness, device=device))
            layer.table_logits.copy_((torch.tensor(spec["truth_tables"], device=device).float()*2-1)*sharpness/2)


def _fused_step(candidate, confidence, state, arrival, valid, windows, levels, consts, layers, binary,
                state_bits: int, top_c: float, top_q: float):
    """One photon through the comparator, the gate layers and the update (soft or STE)."""
    distance = arrival - candidate
    size = distance.abs()
    near = ((windows + .5 - size[:, None]) / (.25 * windows + 1)).sigmoid()
    sign = torch.stack(((distance - .5).sigmoid(), (-distance - .5).sigmoid(), (.5 - confidence).sigmoid()), -1)
    conf = (confidence[:, None] - levels + .5).sigmoid()
    soft = torch.cat((near, sign, conf), -1)
    if binary:
        hard = torch.cat((size[:, None] <= windows, torch.stack((distance > 0, distance < 0, confidence < 1), -1),
                          confidence[:, None] >= levels), -1).to(soft.dtype)
        soft = soft + (hard - soft).detach()
    base = torch.cat((soft, consts, state), -1)
    sources = base
    out = base
    for weight, c0, ca, cb, cab in layers:
        ab = sources @ weight
        a, b = ab.chunk(2, -1)
        out = c0 + a * cb + b * ca + a * b * cab
        sources = torch.cat((base, out), -1)
    new_state = out[:, :state_bits]
    replace, up, down, inc, dec = out[:, state_bits:state_bits + 5].unbind(-1)
    stepped = (candidate + up - down).clamp(0, top_c)
    new_candidate = stepped + replace * (arrival - stepped)
    new_confidence = (confidence + inc - dec).clamp(0, top_q)
    candidate = torch.where(valid, new_candidate, candidate)
    confidence = torch.where(valid, new_confidence, confidence)
    state = torch.where(valid[:, None], new_state, state)
    return candidate, confidence, state


def rule_circuit(config=None, window=8):
    """Hand-written rule: majority vote within a window, plus a one-bin median step."""
    c = config or StreamConfig()
    names = input_names(c)
    near, zero, gt, lt = (names.index(n) for n in (f"near{window}", "zero", "gt", "lt"))
    const = names.index("const0")
    state = len(names) - c.state_bits
    base = len(names)
    layers = []
    for depth in range(c.layers):
        last = depth == c.layers - 1
        inputs, tables = [[const, const] for _ in range(c.width)], [[0, 0, 0, 0] for _ in range(c.width)]
        if last:
            for i in range(c.state_bits):
                inputs[i], tables[i] = [state+i, const], [0, 0, 1, 1]
            for name, gate in {"replace": ([near, zero], [0, 1, 0, 0]), "up": ([near, gt], [0, 0, 0, 1]),
                               "down": ([near, lt], [0, 0, 0, 1]), "inc": ([near, zero], [0, 1, 1, 1]),
                               "dec": ([near, zero], [1, 0, 0, 0])}.items():
                inputs[c.state_bits + ACTIONS.index(name)], tables[c.state_bits + ACTIONS.index(name)] = gate
        layers.append({"inputs": inputs, "truth_tables": tables})
    return {"format": "photon-stream-core-v1", "config": asdict(c), "inputs": names,
            "actions": list(ACTIONS), "layers": layers}


@torch.no_grad()
def simulate_stream(circuit, photons):
    """Independent integer implementation of the core. Returns final candidates."""
    c = StreamConfig(**circuit["config"])
    rays = len(photons)
    photons = photons.long()
    device = photons.device
    candidate = torch.zeros(rays, dtype=torch.long, device=device)
    confidence = torch.zeros_like(candidate)
    state = torch.zeros(rays, c.state_bits, dtype=torch.long, device=device)
    top_c, top_q = 2**c.cand_bits - 1, 2**c.conf_bits - 1
    specs = [(torch.tensor(x["inputs"], device=device), torch.tensor(x["truth_tables"], device=device))
             for x in circuit["layers"]]
    gates = torch.arange(c.width, device=device)[None]
    for step in range(photons.shape[1]):
        arrival, valid = photons[:, step], photons[:, step] >= 0
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
        confidence = torch.where(valid, (confidence + inc - dec).clamp(0, top_q), confidence)
        state = torch.where(valid[:, None], new_state, state)
    return candidate


def pack_circuit(circuit, device=None):
    """Return wiring [layers, width, 2] and truth tables as 4-bit codes [layers, width]."""
    inputs = torch.tensor([x["inputs"] for x in circuit["layers"]], device=device)
    tables = torch.tensor([x["truth_tables"] for x in circuit["layers"]], device=device)
    codes = (tables << torch.arange(4, device=device)).sum(-1).int()
    return inputs, codes


def unpack_circuit(template, inputs, codes):
    """Return a copy of a circuit dictionary holding the packed wiring and tables."""
    circuit = {key: value for key, value in template.items() if key != "layers"}
    circuit["layers"] = [{"inputs": wires.tolist(), "truth_tables": [[(code >> bit) & 1 for bit in range(4)] for code in row]}
                         for wires, row in zip(inputs.cpu(), codes.cpu().tolist())]
    return circuit


def _pack_bits(bits):
    """Pack booleans [..., rays] into int64 words [..., ceil(rays/64)], 64 rays per word."""
    rays = bits.shape[-1]
    words = -(-rays // 64)
    bits = torch.nn.functional.pad(bits.long(), (0, words*64 - rays)).reshape(*bits.shape[:-1], words, 64)
    # Distinct powers of two never carry, so the sum is a bitwise OR (bit 63 wraps to the sign bit).
    return (bits << torch.arange(64, device=bits.device)).sum(-1)


def _unpack_bits(words, rays):
    shifts = torch.arange(64, device=words.device)
    return ((words[..., None] >> shifts) & 1).reshape(*words.shape[:-1], -1)[..., :rays]


def packable(config):
    """The packed simulator needs power-of-two windows and confidence levels."""
    powers = lambda xs: all(x > 0 and x & (x - 1) == 0 for x in xs)
    return powers(config.windows) and powers(CONF_LEVELS) and max(config.windows) < 2**config.cand_bits


def _subtract(x, y, none):
    """x - y on bit-planes: (difference planes, borrow-out plane meaning x < y)."""
    borrow, out = none, []
    for xi, yi in zip(x, y):
        out.append(xi ^ yi ^ borrow)
        borrow = (~xi & yi) | (~(xi ^ yi) & borrow)
    return out, borrow


def _suffix_or(planes, none):
    """above[k] = OR of planes[k:], so (value < 2**k) == ~above[k]."""
    above, acc = [none] * (len(planes) + 1), none
    for k in range(len(planes) - 1, -1, -1):
        acc = acc | planes[k]
        above[k] = acc
    return above


def _step_counter(planes, up, down):
    """Saturating +1/-1 (both or neither: hold), on bit-planes."""
    top, bottom = planes[0], ~planes[0]
    for p in planes[1:]:
        top, bottom = top & p, bottom & ~p
    carry, borrow = up & ~down & ~top, down & ~up & ~bottom
    result = []
    for p in planes:
        result.append(p ^ carry)
        carry = p & carry
    out = []
    for p in result:
        out.append(p ^ borrow)
        borrow = ~p & borrow
    return out


def _packed_step(cand, conf, state, a_planes, valid, wires, masks, window_bits, conf_bits, state_bits: int):
    """One photon for every circuit and 64 rays per word. Registers are [circuits, bits, words]."""
    circuits, _, words = cand.shape
    none = torch.zeros((circuits, words), dtype=cand.dtype, device=cand.device)
    ones = ~none
    cand_l, conf_l = list(cand.unbind(1)), list(conf.unbind(1))
    state_l = list(state.unbind(1)) if state_bits else []
    a = [plane[None].expand(circuits, words) for plane in a_planes.unbind(0)]
    valid = valid[None]
    above_d, lt = _subtract(a, cand_l, none)        # arrival - candidate; borrow: arrival < candidate
    below_d, gt = _subtract(cand_l, a, none)        # candidate - arrival; borrow: arrival > candidate
    size = [(gt & x) | (~gt & y) for x, y in zip(above_d, below_d)]
    above = _suffix_or(size, none)
    lower, acc = [none], none                         # lower[k] = OR of size[:k]
    for plane in size:
        acc = acc | plane
        lower.append(acc)
    flags = []
    for k in window_bits:
        exact = size[k] & ~above[k + 1] & ~lower[k]     # size == 2**k
        flags.append(~above[k] | exact)                 # size <= 2**k
    conf_above = _suffix_or(conf_l, none)
    full = conf_l[0]
    for p in conf_l[1:]:
        full = full & p
    flags += [gt, lt, ~conf_above[0]]
    flags += [conf_above[m] for m in conf_bits]
    flags += [full, none, ones]
    base = torch.stack(flags + state_l, 1)            # [circuits, inputs, words]
    pool, out = base, base
    for wire, (t0, t1, t2, t3) in zip(wires, masks):
        index = wire[..., None].expand(-1, -1, -1, words)
        x = pool.gather(1, index[:, :, 0])
        y = pool.gather(1, index[:, :, 1])
        out = (t0 & ~x & ~y) | (t1 & ~x & y) | (t2 & x & ~y) | (t3 & x & y)
        pool = torch.cat((base, out), 1)
    replace, up, down, inc, dec = (out[:, state_bits + i] for i in range(len(ACTIONS)))
    stepped = _step_counter(cand_l, up, down)
    moved = [(replace & ai) | (~replace & si) for ai, si in zip(a, stepped)]
    cand = torch.stack([(valid & m) | (~valid & p) for m, p in zip(moved, cand_l)], 1)
    counted = _step_counter(conf_l, inc, dec)
    conf = torch.stack([(valid & m) | (~valid & p) for m, p in zip(counted, conf_l)], 1)
    if state_bits:
        state = torch.stack([(valid & out[:, i]) | (~valid & p) for i, p in enumerate(state_l)], 1)
    return cand, conf, state


_PACKED = {"mode": None, "step": None}


def set_search_compile(mode=None):
    """torch.compile the packed simulator's per-photon step: None, "default" or "reduce-overhead"."""
    _PACKED["mode"] = mode
    _PACKED["step"] = None if not mode else torch.compile(_packed_step, mode=mode, dynamic=False)


@torch.no_grad()
def simulate_population_packed(config, inputs, codes, photons):
    """Bit-sliced simulate_population: same results, 64 rays per machine word.

    Every register is held as bit-planes [circuits, bits, words]. Comparisons,
    gates and counters are bitwise logic on those planes (the circuit itself,
    ripple subtractors and incrementers included), so one operation advances
    64 rays at once. Takes and returns the same shapes as simulate_population.
    The per-photon step can be fused with set_search_compile().
    """
    c = config
    if not packable(c):
        return simulate_population(config, inputs, codes, photons)
    circuits, rays = len(inputs), len(photons)
    device = photons.device
    cb, qb, sb = c.cand_bits, c.conf_bits, c.state_bits
    photons = photons.long()
    valid_all = _pack_bits((photons >= 0).T)                                    # [steps, words]
    arrival = photons.clamp_min(0).T                                            # [steps, rays]
    arrival_all = _pack_bits(((arrival[:, None, :] >> torch.arange(cb, device=device)[None, :, None]) & 1).bool())
    words = valid_all.shape[-1]
    cand = torch.zeros((circuits, cb, words), dtype=torch.long, device=device)
    conf = torch.zeros((circuits, qb, words), dtype=torch.long, device=device)
    state = torch.zeros((circuits, sb, words), dtype=torch.long, device=device)
    masks = tuple(tuple(-((codes[:, layer, :, None].long() >> i) & 1) for i in range(4)) for layer in range(c.layers))
    wires = tuple(inputs[:, layer].long() for layer in range(c.layers))         # [circuits, width, 2]
    window_bits = tuple(w.bit_length() - 1 for w in c.windows)
    conf_bits = tuple(level.bit_length() - 1 for level in CONF_LEVELS)
    run = lambda step: _run_packed(step, cand, conf, state, arrival_all, valid_all, wires, masks, window_bits, conf_bits, sb)
    if _PACKED["step"] is not None:
        try:
            return _unpack_candidates(run(_PACKED["step"]), rays)
        except Exception as error:
            print(f"torch.compile of the search failed ({type(error).__name__}); continuing without it", flush=True)
            _PACKED["step"] = None
    return _unpack_candidates(run(_packed_step), rays)


def _run_packed(step, cand, conf, state, arrival_all, valid_all, wires, masks, window_bits, conf_bits, sb):
    for k in range(len(valid_all)):
        cand, conf, state = step(cand, conf, state, arrival_all[k], valid_all[k], wires, masks, window_bits, conf_bits, sb)
    return cand


def _unpack_candidates(cand, rays):
    return sum(_unpack_bits(cand[:, i], rays) << i for i in range(cand.shape[1])).int()


@torch.no_grad()
def simulate_population(config, inputs, codes, photons):
    """Run many circuits on shared rays at once. Returns candidates [circuits, rays].

    Takes wiring [circuits, layers, width, 2] and codes [circuits, layers, width].
    Matches simulate_stream for every member, so it is safe for discrete search.
    """
    c = config
    circuits, rays = len(inputs), len(photons)
    device = photons.device
    candidate = torch.zeros(circuits, rays, dtype=torch.int32, device=device)
    confidence = torch.zeros_like(candidate)
    state = torch.zeros(circuits, rays, c.state_bits, dtype=torch.int32, device=device)
    top_c, top_q = 2**c.cand_bits - 1, 2**c.conf_bits - 1
    wires = [inputs[:, i, None, :, :].expand(circuits, rays, c.width, 2) for i in range(c.layers)]
    tables = [codes[:, i, None, :] for i in range(c.layers)]
    never, always = torch.zeros_like(candidate, dtype=torch.bool), torch.ones_like(candidate, dtype=torch.bool)
    for step in range(photons.shape[1]):
        arrival = photons[:, step].int()[None]
        valid = arrival >= 0
        distance = arrival - candidate
        size = distance.abs()
        flags = [size <= w for w in c.windows]
        flags += [distance > 0, distance < 0, confidence == 0]
        flags += [confidence >= level for level in CONF_LEVELS]
        flags += [confidence == top_q, never, always]
        base = torch.cat((torch.stack(flags, -1).int(), state), -1)
        output = None
        for wire, table in zip(wires, tables):
            pool = base if output is None else torch.cat((base, output), -1)
            index = 2*pool.gather(2, wire[..., 0]) + pool.gather(2, wire[..., 1])
            output = (table >> index) & 1
        new_state = output[..., :c.state_bits]
        replace, up, down, inc, dec = output[..., c.state_bits:c.state_bits+len(ACTIONS)].unbind(-1)
        stepped = (candidate + up - down).clamp(0, top_c)
        candidate = torch.where(valid, torch.where(replace == 1, arrival.expand_as(stepped), stepped), candidate)
        confidence = torch.where(valid, (confidence + inc - dec).clamp(0, top_q), confidence)
        state = torch.where(valid[..., None], new_state, state)
    return candidate
