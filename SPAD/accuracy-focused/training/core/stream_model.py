"""Per-pixel photon-stream core: fixed datapath, learned logic-gate controller.

Each pixel holds a candidate bin, a saturating confidence counter and a few
learned state bits, and no histogram. Per photon, the datapath compares the
arrival with the candidate. The controller maps those comparison flags and its
own state to actions. After the photon budget, the candidate is the range bin.
Distances enter as thermometer flags, because Boolean gates use them directly.

Per-photon datapath (fixed, not learned). For arrival `a` and candidate `c`
(both in time bins of 750 ps, 0..1023 with the default cand_bits=10):
  distance = a - c, size = |distance|
  near{w}  : size <= w for each window w (default 1, 2, 4, 8, 16)
  gt, lt   : a > c, a < c
  zero     : confidence == 0
  conf2/4/8: confidence >= 2, 4, 8
  full     : confidence == 2**conf_bits - 1
  const0, const1 : constants
  state{i} : the learned memory bits from the previous photon
These (see input_names) are the base signals. Three layers of two-input gates
read them (layer k>0 can also read layer k-1's outputs). The last layer's
outputs are, in order: next state bits, then the five actions in ACTIONS:
  replace: candidate <- arrival
  up/down: candidate +1 / -1, saturating at 0 and 2**cand_bits - 1
  inc/dec: confidence +1 / -1, saturating at 0 and 2**conf_bits - 1
(up with down, or inc with dec, cancel). A photon with arrival < 0 is padding
and changes nothing.

Four implementations of the same circuit live here; they must agree:
  StreamCore.forward / forward_reference : float, differentiable (training)
  simulate_stream                        : integer, one circuit (the reference)
  simulate_population                    : integer, many circuits at once
  simulate_population_packed             : same, bit-sliced 64 rays per word
The exported circuit dictionary ("photon-stream-core-v1") holds, per layer, the
source index of both gate inputs and the 4-entry truth table (order 00, 01, 10, 11).

Sub-bin resolution (frac_bits > 0): the candidate register gains frac_bits fractional
bits, so it holds range in units of 1/2**frac_bits of a time bin. Arrivals stay whole
bins. With step_bits > 0 the controller also drives a step-size select: a step moves
the candidate by 2**-s of a bin, s being the binary number on the select outputs, so
the circuit can take whole-bin steps while it is far off and fine steps once locked.
With frac_bits = step_bits = 0 everything is identical to the original core.

Rival registers (rivals > 0): extra memory that remembers where else photons cluster.
Each register holds a whole-bin position and a small vote counter. A photon within
rival_window bins of an occupied register votes for the first such register; otherwise
it takes the first empty register; if none is empty every counter drops by one. The
registers never look at the candidate or the controller. The controller sees whether the
best-supported register is far from the candidate (more than RIVAL_FAR bins) and how many
votes it has, and gains one action, swap, which moves the candidate onto that register.
With rival_track set, a register that receives a vote also moves toward the photon, so it
follows the centre of its cluster instead of holding the first photon's position: "step"
moves it one bin (sign of the gap), "half" by half the gap rounded toward the register.
No extra memory bits, one small adder per register.

Coincidence gate (coincidence_depth D > 0): a D-entry FIFO of raw arrival bins with valid bits,
shifting on every valid photon, and one `acquired` flip-flop set by the first replace. `coinc`
says the photon lies within coincidence_window bins of at least one valid entry (entries from
before this photon). After the first acquisition the candidate may jump to a far photon (not
within 16 bins, ~near16) only on a coincidence: a blocked replace also clears up and down, so
the candidate holds; inc, dec, the step select and next state pass through. `coinc` is also a
controller input. Like the rival registers, the FIFO depends only on the photons.

Challenge rule (challenge_cap C > 0, needs the coincidence FIFO): the FIFO's comparators are
counted instead of OR-ed. A photon's evidence is 1 + the number of FIFO entries within
coincidence_window bins of it (a 4-bit adder tree); `outnumber` says that evidence exceeds the
incumbent's confidence, capped at C. It is a controller input, and the datapath enforces it: a
replace outside near16 without `outnumber` is blocked (replacing the gate's coinc test), and an
accepted replace loads the confidence counter with the challenger's evidence, so a pair arrives
with confidence 2, a triple with 3. The FIFO and its count depend only on the photons.

Proportional tracking (track = "prop"): up/down move the candidate by |arrival - candidate| >>
(select + 1) instead of a fixed 2**-select bins, so with a gain schedule the candidate is a running
mean of the photons it accepts, not a median-like sign step. Reuses the window subtractor's |d|;
adds a small barrel shifter in front of the existing adder.

Windows (near flags) are |arrival - candidate| <= w in fixed point: any w whose product with
2**frac_bits is a positive integer, e.g. 0.25 or 12. Sub-bin flags are named near0p5, near0p25...
"""
from dataclasses import asdict, dataclass

import torch
from torch import nn

from training.core.model import GateLayer, light_gate

ACTIONS = ("replace", "up", "down", "inc", "dec")
RIVAL_TRACKS = ("off", "step", "half")
TRACKS = ("step", "prop")
RIVAL_FAR = 16          # bins; a power of two so the bit-sliced simulator can test it
GATE_NEAR = 16          # bins; the coincidence gate blocks only replaces outside near16
CONF_LEVELS = (2, 4, 8)


@dataclass
class StreamConfig:
    """Datapath and controller sizes.

    state_bits: learned memory bits carried from photon to photon.
    width: gates per layer; the last layer needs state_bits + 5 outputs.
    layers: gate layers (the controller depth).
    conf_bits: width of the saturating confidence counter (flags use levels 2, 4, 8, max).
    cand_bits: width of the candidate register, in time bins (default 10, so 0..1023;
        the 672-bin histogram range fits).
    windows: distances (in bins) tested by the near flags; must be powers of two for
        the packed simulator (see packable).
    """
    state_bits: int = 4
    width: int = 16
    layers: int = 3
    conf_bits: int = 4
    cand_bits: int = 10
    windows: tuple = (1, 2, 4, 8, 16)
    frac_bits: int = 0                 # fractional candidate bits (sub-bin resolution)
    step_bits: int = 0                 # step-size select outputs: step = 2**-select bins
    conf_levels: tuple = CONF_LEVELS   # confidence thresholds shown to the controller
    rivals: int = 0                    # extra position registers, each with a vote counter
    rival_window: int = 8              # a photon within this many bins votes for a register
    rival_bits: int = 4                # vote counter width
    rival_levels: tuple = (2, 4, 8)    # vote thresholds shown to the controller
    rival_track: str = "off"           # a voted register moves toward the photon: "off", "step" (1 bin), "half"
    coincidence_depth: int = 0         # FIFO entries of the coincidence gate on far jumps (0 = off)
    coincidence_window: int = 8        # a photon within this many bins of an entry is a coincidence
    challenge_cap: int = 0             # challenge rule: evidence (1 + FIFO matches) must beat min(confidence, cap)
    track: str = "step"                # "step": fixed 2**-select steps; "prop": |distance| >> (select + 1)

    def __post_init__(self):
        self.windows = tuple(sorted(window_value(w) for w in self.windows))
        if len(set(self.windows)) != len(self.windows):
            raise ValueError("Windows must be distinct")
        for w in self.windows:
            units = w * 2**self.frac_bits
            if not (units > 0 and float(units).is_integer()):
                raise ValueError(f"Window {w} is not a positive whole number of 1/{2**self.frac_bits} bins")
        if self.coincidence_depth < 0 or not 0 <= self.coincidence_window < 2**self.cand_bits:
            raise ValueError("The coincidence FIFO needs a nonnegative depth and a window below the range")
        if self.coincidence_depth and GATE_NEAR not in self.windows:
            raise ValueError(f"The coincidence gate needs the near{GATE_NEAR} window")
        self.conf_levels = tuple(self.conf_levels)
        self.rival_levels = tuple(self.rival_levels)
        if self.width < self.state_bits + len(ACTIONS) + self.step_bits + (self.rivals > 0):
            raise ValueError("Last layer must hold next state, all actions, the step select and swap")
        if self.rivals < 0 or (self.rivals and max(self.rival_levels) >= 2**self.rival_bits):
            raise ValueError("Rival vote levels must fit the vote counter")
        if self.rival_track not in RIVAL_TRACKS:
            raise ValueError(f"rival_track must be one of {RIVAL_TRACKS}")
        if self.layers < 1 or self.conf_bits < 4 or self.state_bits < 0:
            raise ValueError("Need a layer, four confidence bits and nonnegative state")
        if self.challenge_cap < 0 or (self.challenge_cap and not self.coincidence_depth):
            raise ValueError("The challenge rule counts the coincidence FIFO: set coincidence_depth")
        if self.challenge_cap and self.challenge_cap >= 2**self.conf_bits:
            raise ValueError("The challenge cap must fit the confidence counter")
        if self.track not in TRACKS:
            raise ValueError(f"track must be one of {TRACKS}")
        if self.frac_bits < 0 or self.step_bits < 0 or (self.track == "step" and 2**self.step_bits - 1 > self.frac_bits):
            raise ValueError("The finest step, 2**-(2**step_bits - 1) bins, needs that many fractional bits")
        if max(self.conf_levels) >= 2**self.conf_bits:
            raise ValueError("Confidence levels must fit the confidence counter")

    @property
    def scale(self):
        """Candidate register units per time bin."""
        return 2**self.frac_bits


def window_value(w):
    """A window as stored: int for whole bins (so names and JSON keep their old form), else float."""
    w = float(w)
    return int(w) if w.is_integer() else w


def window_name(w):
    """Verilog-safe input name: near1, near12 for whole bins, near0p5, near0p125 for sub-bin windows."""
    w = window_value(w)
    return f"near{w}" if isinstance(w, int) else "near" + repr(w).replace(".", "p")


def window_units(c):
    """Windows in candidate register units (1/2**frac_bits bins), as exact integers."""
    return tuple(int(round(w * c.scale)) for w in c.windows)


def input_names(c):
    """Names of the base signals the first gate layer can read, in index order.

    Circuit "inputs" entries index into this list (layer 0) or into this list
    followed by the previous layer's outputs (later layers).
    """
    return ([window_name(w) for w in c.windows] + ["gt", "lt", "zero"]
            + [f"conf{level}" for level in c.conf_levels] + ["full", "const0", "const1"]
            + (["rival_far"] + [f"rival{level}" for level in c.rival_levels] if c.rivals else [])
            + (["coinc"] if c.coincidence_depth else [])
            + (["outnumber"] if c.challenge_cap else [])
            + [f"state{i}" for i in range(c.state_bits)])


@torch.no_grad()
def coincidence_trace(config, photons):
    """coinc seen by each photon, bool [rays, steps]: within coincidence_window bins of a valid FIFO entry.

    The FIFO holds the last coincidence_depth valid arrivals before this photon (raw bins) and
    shifts on every valid photon. It depends only on the photons, so one trace serves every circuit.
    """
    c = config
    photons = photons.long()
    rays, steps = photons.shape
    fifo = torch.zeros(rays, c.coincidence_depth, dtype=torch.long, device=photons.device)
    filled = torch.zeros_like(fifo, dtype=torch.bool)
    coinc = torch.zeros(rays, steps, dtype=torch.bool, device=photons.device)
    for step in range(steps):
        photon = photons[:, step]
        valid = photon >= 0
        coinc[:, step] = (filled & ((photon[:, None] - fifo).abs() <= c.coincidence_window)).any(1)
        fifo = torch.where(valid[:, None], torch.cat((photon[:, None], fifo[:, :-1]), 1), fifo)
        filled = torch.where(valid[:, None], torch.cat((valid[:, None], filled[:, :-1]), 1), filled)
    return coinc


@torch.no_grad()
def coincidence_count_trace(config, photons):
    """Number of valid FIFO entries within coincidence_window bins of each photon, long [rays, steps]."""
    c = config
    photons = photons.long()
    rays, steps = photons.shape
    fifo = torch.zeros(rays, c.coincidence_depth, dtype=torch.long, device=photons.device)
    filled = torch.zeros_like(fifo, dtype=torch.bool)
    count = torch.zeros(rays, steps, dtype=torch.long, device=photons.device)
    for step in range(steps):
        photon = photons[:, step]
        valid = photon >= 0
        count[:, step] = (filled & ((photon[:, None] - fifo).abs() <= c.coincidence_window)).sum(1)
        fifo = torch.where(valid[:, None], torch.cat((photon[:, None], fifo[:, :-1]), 1), fifo)
        filled = torch.where(valid[:, None], torch.cat((valid[:, None], filled[:, :-1]), 1), filled)
    return count


@torch.no_grad()
def rival_trace(config, photons):
    """Best-supported rival register seen by each photon: (position, votes), each [rays, steps].

    Values are the registers' contents before that photon updates them, as flip-flops show them.
    The registers depend only on the photons, so one trace serves every circuit of a population.
    """
    c = config
    photons = photons.long()
    rays, steps = photons.shape
    device = photons.device
    pos = torch.zeros(rays, c.rivals, dtype=torch.long, device=device)
    votes = torch.zeros_like(pos)
    top = 2**c.rival_bits - 1
    best_pos = torch.zeros(rays, steps, dtype=torch.long, device=device)
    best_votes = torch.zeros_like(best_pos)
    first = lambda mask: mask & (mask.long().cumsum(1) == 1)      # lowest-numbered register wins
    for step in range(steps):
        leader = first(votes == votes.max(1, keepdim=True).values)
        best_pos[:, step] = (pos * leader).sum(1)
        best_votes[:, step] = (votes * leader).sum(1)
        photon = photons[:, step, None]
        valid = photon >= 0
        match = (votes > 0) & ((pos - photon).abs() <= c.rival_window)
        voted = first(match) & valid
        empty = votes == 0
        taken = first(empty) & valid & ~match.any(1, keepdim=True)
        decay = valid & ~match.any(1, keepdim=True) & ~empty.any(1, keepdim=True)
        votes = torch.where(voted, (votes + 1).clamp(max=top), votes)
        if c.rival_track != "off":
            # The voted register moves toward the photon: one bin, or half the gap (|gap| >> 1).
            gap = photon - pos
            move = gap.sign() if c.rival_track == "step" else gap.sign() * (gap.abs() >> 1)
            pos = torch.where(voted, pos + move, pos)
        pos = torch.where(taken, photon.expand_as(pos), pos)
        votes = torch.where(taken, torch.ones_like(votes), votes)
        votes = torch.where(decay, votes - 1, votes)
    return best_pos, best_votes


def _flag(hard, soft, mode):
    """Boolean forward value; the surrogate supplies gradients unless fully soft.

    mode "soft": return the smooth sigmoid surrogate. Otherwise (straight-through):
    the value is the exact Boolean `hard`, the gradient is that of `soft`.
    """
    return soft if mode == "soft" else soft + (hard.float() - soft).detach()


class StreamCore(nn.Module):
    """Differentiable model of the per-pixel photon-stream circuit.

    Input photons are [rays, steps] integer arrival bins (750 ps each), -1 where a
    ray has no photon. forward() returns the final candidate bin per ray, [rays],
    as a float. Modes: soft (default), ste=True (Boolean forward, soft gradient)
    and hard=True (the exact discrete circuit, via forward_reference).
    """
    def __init__(self, config=None):
        super().__init__()
        self.config = c = config or StreamConfig()
        self.base_bits = len(input_names(c))
        self.layers = nn.ModuleList([
            GateLayer(self.base_bits if i == 0 else self.base_bits + c.width, c.width)
            for i in range(c.layers)])
        with torch.no_grad():
            # Index of the first state signal among the base inputs.
            state = self.base_bits - c.state_bits
            for layer in self.layers:
                # Random start: near-zero routing logits, plus a strong bump on two random
                # sources per gate so each input begins close to one-hot.
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
        """Routing logits (optimized on the architecture split)."""
        return [layer.routes for layer in self.layers]

    def weight_parameters(self):
        """Truth-table logits (optimized on the training split)."""
        return [layer.table_logits for layer in self.layers]

    def features(self, candidate, confidence, arrival, state, mode):
        """Comparator flags [rays, base_bits] for one photon (order as input_names).

        candidate, confidence, arrival: float tensors [rays] (bins / counter value).
        state: [rays, state_bits]. The sigmoid surrogates are centred on the Boolean
        threshold (e.g. size <= w becomes sigmoid((w + .5 - size) / (.25 w + 1))), so
        they are near 0.5 only at the boundary.
        """
        c = self.config
        distance = arrival - candidate
        size = distance.abs()
        flags = [_flag(size <= w, ((w + .5 - size) / (.25*w + 1)).sigmoid(), mode) for w in c.windows]
        flags += [_flag(distance > 0, (distance - .5).sigmoid(), mode),
                  _flag(distance < 0, (-distance - .5).sigmoid(), mode),
                  _flag(confidence < 1, (.5 - confidence).sigmoid(), mode)]
        flags += [_flag(confidence >= level, (confidence - level + .5).sigmoid(), mode) for level in c.conf_levels]
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
        top_c, top_q = (2**(c.cand_bits + c.frac_bits) - 1) / c.scale, 2**c.conf_bits - 1
        first = c.state_bits + len(ACTIONS)
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
            replace, up, down, inc, dec = outputs[:, c.state_bits:first].unbind(-1)
            size = _step_size(outputs[:, first:first + c.step_bits])
            stepped = (candidate + (up - down) * size).clamp(0, top_c)
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
        """Choose how the per-photon step runs: None (eager), "default", or "reduce-overhead" (CUDA graphs).

        Returns self. If compilation fails on this device, forward() falls back to eager.
        """
        self._compiled = None if not mode else torch.compile(_fused_step, mode=mode, dynamic=False)
        return self

    def forward(self, photons, temperature=1., hard=False, ste=False):
        """Run the photon streams through the circuit; returns final candidates [rays] (float).

        photons: [rays, steps] int arrival bins, -1 for no photon.
        temperature: softmax temperature of the routing (lower = closer to one-hot).
        hard: exact discrete circuit (slow path). ste: Boolean forward, soft gradient.
        With neither, everything is soft. Gradients flow through the candidate via the
        replace/up/down actions.
        """
        c = self.config
        if c.rivals or c.coincidence_depth or c.track != "step":
            if not hard:
                raise NotImplementedError("Rival registers and the coincidence gate have no gradient model: "
                                          "train them with --steps 0")
            return simulate_stream(self.circuit(), photons).float() / c.scale
        if hard:
            return self.forward_reference(photons, temperature, hard=True)   # exact discrete path
        binary = ste
        layers = []
        for layer in self.layers:
            routing, table = layer.prepared(temperature, False, ste)
            width, _, sources = routing.shape
            # The multilinear gate expands to c0 + a*(c2-c0) + b*(c1-c0) + a*b*(c3-c2-c1+c0)
            # for table entries c0..c3 = outputs for (a,b) = 00, 01, 10, 11. The four
            # coefficients depend only on the table, so they are computed once per pass.
            weight = routing.transpose(0, 1).reshape(2 * width, sources).T     # [sources, 2*width]: all a, then all b
            c0, c1, c2, c3 = table.unbind(-1)
            layers.append((weight, c0, c1 - c0, c2 - c0, c3 - c2 - c1 + c0))
        device = photons.device
        windows = torch.tensor(c.windows, dtype=torch.float32, device=device)
        top_q = 2**c.conf_bits - 1
        levels = torch.tensor(list(c.conf_levels) + [top_q], dtype=torch.float32, device=device)
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
        """Loop `step` over the photon sequence; arrivals/valids are [steps, rays]."""
        c = self.config
        candidate, confidence, state = start
        for k in range(len(arrivals)):
            candidate, confidence, state = step(candidate, confidence, state, arrivals[k], valids[k], windows,
                                                levels, consts, layers, binary, c.state_bits,
                                                float((2**(c.cand_bits + c.frac_bits) - 1) / c.scale),
                                                float(2**c.conf_bits - 1), c.step_bits)
        return candidate

    @torch.no_grad()
    def circuit(self):
        """Harden the model and export it as a photon-stream-core-v1 dictionary."""
        layers = []
        for layer in self.layers:
            routes, table = layer.prepared(hard=True)
            layers.append({"inputs": routes.argmax(-1).tolist(), "truth_tables": table.int().tolist()})
        return {"format": "photon-stream-core-v1", "config": asdict(self.config),
                "inputs": input_names(self.config), "actions": list(ACTIONS) + ["swap"] * (self.config.rivals > 0),
                "layers": layers}

    @torch.no_grad()
    def load_circuit(self, circuit, sharpness=4.):
        """Set logits so the hard model equals a circuit, with room to keep learning.

        Each chosen route gets logit +sharpness over a near-zero background; each table
        entry gets +/- sharpness/2 (a 1 maps to +sharpness/2, a 0 to -sharpness/2).
        """
        for layer, spec in zip(self.layers, circuit["layers"]):
            layer.routes.normal_(0, 0.01)
            device = layer.routes.device
            layer.routes.scatter_add_(-1, torch.tensor(spec["inputs"], device=device)[..., None],
                                      torch.full((*layer.routes.shape[:2], 1), sharpness, device=device))
            layer.table_logits.copy_((torch.tensor(spec["truth_tables"], device=device).float()*2-1)*sharpness/2)


def _step_size(select):
    """Step in bins, 2**-s, for select bits [rays, step_bits] (soft bits blend the sizes)."""
    size = 1.
    for i in range(select.shape[-1]):
        size = size * (1 - select[:, i] * (1 - 2.**-(2**i)))
    return size


def _fused_step(candidate, confidence, state, arrival, valid, windows, levels, consts, layers, binary,
                state_bits: int, top_c: float, top_q: float, step_bits: int = 0):
    """One photon through the comparator, the gate layers and the update (soft or STE)."""
    # Same flags and update as StreamCore.features / forward_reference, vectorized over
    # all windows and levels. `layers` holds the precomputed (weight, c0, ...) coefficients.
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
    move = up - down
    for i in range(step_bits):
        move = move * (1 - out[:, state_bits + 5 + i] * (1 - 2.**-(2**i)))
    stepped = (candidate + move).clamp(0, top_c)
    new_candidate = stepped + replace * (arrival - stepped)
    new_confidence = (confidence + inc - dec).clamp(0, top_q)
    candidate = torch.where(valid, new_candidate, candidate)
    confidence = torch.where(valid, new_confidence, confidence)
    state = torch.where(valid[:, None], new_state, state)
    return candidate, confidence, state


def swap_slot(config):
    """Index of the swap action among the last layer's gates."""
    return config.state_bits + len(ACTIONS) + config.step_bits


def swap_rule(names):
    """Hand-written swap: move to the best rival when it is far away and has at least two votes."""
    return [names.index("rival_far"), names.index("rival2")], [0, 0, 0, 1]


def rule_circuit(config=None, window=8):
    """Hand-written baseline circuit in the same format as a trained one.

    Uses only the window flag `near{window}` (in bins), gt/lt, zero, and constants:
      replace if the confidence is zero and the photon is outside the window;
      step up (down) one bin if the photon is inside the window and later (earlier);
      confidence +1 if inside the window or confidence is zero; -1 otherwise
        (the table 1,0,0,0 is NOR of near and zero).
    Gates in layers before the last are constant 0 and unused. Each state bit
    just holds its value.
    """
    c = config or StreamConfig()
    names = input_names(c)
    near, zero, gt, lt = (names.index(n) for n in (window_name(window), "zero", "gt", "lt"))
    const = names.index("const0")
    # Gain schedule for sub-bin cores: whole-bin steps until confident, then finer ones.
    schedule = [names.index(n) for n in ("conf4", "conf8") if n in names][:c.step_bits]
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
            for i, flag in enumerate(schedule):
                inputs[c.state_bits + len(ACTIONS) + i], tables[c.state_bits + len(ACTIONS) + i] = [flag, const], [0, 0, 1, 1]
            if c.rivals:
                inputs[swap_slot(c)], tables[swap_slot(c)] = swap_rule(names)
        layers.append({"inputs": inputs, "truth_tables": tables})
    return {"format": "photon-stream-core-v1", "config": asdict(c), "inputs": names,
            "actions": list(ACTIONS) + ["swap"] * (c.rivals > 0), "layers": layers}


@torch.no_grad()
def predict_bins(circuit, photons):
    """Final candidates as range in time bins (fractional for a sub-bin core)."""
    return simulate_stream(circuit, photons).float() / 2**circuit["config"].get("frac_bits", 0)


@torch.no_grad()
def simulate_stream(circuit, photons):
    """Independent integer implementation of the core.

    Returns the final candidate registers: whole bins, or units of 1/2**frac_bits bins.
    """
    c = StreamConfig(**circuit["config"])
    rays = len(photons)
    photons = photons.long()
    device = photons.device
    candidate = torch.zeros(rays, dtype=torch.long, device=device)
    confidence = torch.zeros_like(candidate)
    state = torch.zeros(rays, c.state_bits, dtype=torch.long, device=device)
    top_c, top_q = 2**(c.cand_bits + c.frac_bits) - 1, 2**c.conf_bits - 1
    first = c.state_bits + len(ACTIONS)
    specs = [(torch.tensor(x["inputs"], device=device), torch.tensor(x["truth_tables"], device=device))
             for x in circuit["layers"]]
    gates = torch.arange(c.width, device=device)[None]
    rival_pos, rival_votes = rival_trace(c, photons) if c.rivals else (None, None)
    coinc = coincidence_trace(c, photons) if c.coincidence_depth else None
    evidence = coincidence_count_trace(c, photons) + 1 if c.challenge_cap else None
    acquired = torch.zeros(rays, dtype=torch.bool, device=device)
    limits = window_units(c)
    for step in range(photons.shape[1]):
        arrival, valid = photons[:, step] << c.frac_bits, photons[:, step] >= 0
        distance = arrival - candidate
        flags = [(distance.abs() <= units) for units in limits]
        flags += [distance > 0, distance < 0, confidence == 0]
        flags += [confidence >= level for level in c.conf_levels]
        flags += [confidence == top_q, torch.zeros_like(valid), torch.ones_like(valid)]
        if c.rivals:
            votes = rival_votes[:, step]
            flags += [(votes > 0) & ((rival_pos[:, step] - (candidate >> c.frac_bits)).abs() > RIVAL_FAR)]
            flags += [votes >= level for level in c.rival_levels]
        if c.coincidence_depth:
            flags += [coinc[:, step]]
        if c.challenge_cap:
            outnumber = evidence[:, step] > confidence.clamp(max=c.challenge_cap)
            flags += [outnumber]
        base = torch.cat((torch.stack(flags, 1).long(), state), 1)
        output = None
        for inputs, tables in specs:
            pool = base if output is None else torch.cat((base, output), 1)
            output = tables[gates, 2*pool[:, inputs[:, 0]] + pool[:, inputs[:, 1]]]
        new_state = output[:, :c.state_bits]
        replace, up, down, inc, dec = output[:, c.state_bits:first].T
        if c.challenge_cap:
            # A far replace needs the challenger to outnumber the incumbent; blocked, the candidate holds.
            blocked = (replace == 1) & (distance.abs() > GATE_NEAR * c.scale) & ~outnumber
            replace, up, down = (torch.where(blocked, 0, x) for x in (replace, up, down))
        elif c.coincidence_depth:
            # A far replace after the first acquisition needs a coincidence; blocked, the candidate holds.
            blocked = (replace == 1) & acquired & (distance.abs() > GATE_NEAR * c.scale) & ~coinc[:, step]
            replace, up, down = (torch.where(blocked, 0, x) for x in (replace, up, down))
            acquired = acquired | (valid & (replace == 1))
        select = sum(output[:, first + i] << i for i in range(c.step_bits))
        size = (distance.abs() >> (select + 1)) if c.track == "prop" else (c.scale >> select)
        stepped = (candidate + (up - down) * size).clamp(0, top_c)
        moved = torch.where(replace == 1, arrival, stepped)
        if c.rivals:
            moved = torch.where(output[:, swap_slot(c)] == 1, rival_pos[:, step] << c.frac_bits, moved)
        candidate = torch.where(valid, moved, candidate)
        counted = (confidence + inc - dec).clamp(0, top_q)
        if c.challenge_cap:
            counted = torch.where(replace == 1, evidence[:, step].clamp(max=top_q), counted)
        confidence = torch.where(valid, counted, confidence)
        state = torch.where(valid[:, None], new_state, state)
    return candidate


def pack_circuit(circuit, device=None):
    """Return wiring [layers, width, 2] and truth tables as 4-bit codes [layers, width].

    A code is sum(table[i] << i), with i = 2a + b, so bit 0 is the output for (0, 0).
    """
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
    """Pack booleans [..., rays] into int64 words [..., ceil(rays/64)], 64 rays per word.

    Ray r goes to bit (r % 64) of word (r // 64). The packed simulator treats each
    bit position as an independent ray, so one bitwise op on a word acts on 64 rays.
    """
    rays = bits.shape[-1]
    words = -(-rays // 64)
    bits = torch.nn.functional.pad(bits.long(), (0, words*64 - rays)).reshape(*bits.shape[:-1], words, 64)
    # Distinct powers of two never carry, so the sum is a bitwise OR (bit 63 wraps to the sign bit).
    return (bits << torch.arange(64, device=bits.device)).sum(-1)


def _unpack_bits(words, rays):
    """Inverse of _pack_bits: int64 words [..., W] to 0/1 values [..., rays]."""
    shifts = torch.arange(64, device=words.device)
    return ((words[..., None] >> shifts) & 1).reshape(*words.shape[:-1], -1)[..., :rays]


def packable(config):
    """The packed simulator needs power-of-two confidence levels (windows may be any fixed-point value)."""
    powers = lambda xs: all(x > 0 and x & (x - 1) == 0 for x in xs)
    return powers(config.conf_levels) and not config.challenge_cap and config.track == "step"


def _window_codes(config):
    """Window limits for _packed_step: k >= 0 means size <= 2**k units (the original fast test),
    a negative -u means size <= u units for any other u."""
    return tuple(u.bit_length() - 1 if u & (u - 1) == 0 else -u for u in window_units(config))


def _at_most(planes, limit, none):
    """value <= limit on bit-planes (least significant first), for a constant limit >= 0."""
    if limit >= 2**len(planes) - 1:
        return ~none
    result = ~none                                     # the empty low part is <= anything
    for i, plane in enumerate(planes):
        result = (~plane | result) if (limit >> i) & 1 else (~plane & result)
    return result


def _subtract(x, y, none):
    """x - y on bit-planes: (difference planes, borrow-out plane meaning x < y).

    x, y are lists of planes, least significant first; each plane holds one bit of
    64 rays per word. This is a ripple-borrow subtractor written as bitwise logic.
    """
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
    # top: counter is all ones (cannot go up); bottom: all zeros (cannot go down).
    top, bottom = planes[0], ~planes[0]
    for p in planes[1:]:
        top, bottom = top & p, bottom & ~p
    carry, borrow = up & ~down & ~top, down & ~up & ~bottom
    result = []   # ripple-carry increment, then ripple-borrow decrement
    for p in planes:
        result.append(p ^ carry)
        carry = p & carry
    out = []
    for p in result:
        out.append(p ^ borrow)
        borrow = ~p & borrow
    return out


def _step_by(planes, up, down, step):
    """Saturating +step/-step on bit-planes, step given as planes (both or neither: hold)."""
    add, sub = up & ~down, down & ~up
    carry, total = add ^ add, []
    for p, s in zip(planes, step):
        a = s & add
        total.append(p ^ a ^ carry)
        carry = (p & a) | (carry & (p ^ a))
    total = [t | carry for t in total]                 # overflow: all ones
    borrow, out = sub ^ sub, []
    for p, s in zip(total, step):
        b = s & sub
        out.append(p ^ b ^ borrow)
        borrow = (~p & b) | (~(p ^ b) & borrow)
    return [o & ~borrow for o in out]                  # underflow: zero


def _packed_step(cand, conf, state, a_planes, valid, wires, masks, window_bits, conf_bits, state_bits: int,
                 frac_bits: int = 0, step_bits: int = 0, rival_planes=None, rival_flags=None, rivals: int = 0,
                 coinc=None, gate_flag: int = -1):
    """One photon for every circuit and 64 rays per word. Registers are [circuits, bits, words].

    window_bits: per window, k >= 0 tests size <= 2**k register units, -u tests size <= u.
    With the coincidence gate (gate_flag >= 0, the index of the near16 flag), coinc is this
    photon's coincidence plane [words] and state carries one extra plane, the acquired bit.
    """
    circuits, _, words = cand.shape
    none = torch.zeros((circuits, words), dtype=cand.dtype, device=cand.device)
    ones = ~none
    cand_l, conf_l = list(cand.unbind(1)), list(conf.unbind(1))
    state_l = list(state.unbind(1))[:state_bits] if state_bits else []
    a = [plane[None].expand(circuits, words) for plane in a_planes.unbind(0)]
    valid = valid[None]
    above_d, lt = _subtract(a, cand_l, none)        # arrival - candidate; borrow: arrival < candidate
    below_d, gt = _subtract(cand_l, a, none)        # candidate - arrival; borrow: arrival > candidate
    size = [(gt & x) | (~gt & y) for x, y in zip(above_d, below_d)]   # |arrival - candidate| bit-planes
    above = _suffix_or(size, none)
    lower, acc = [none], none                         # lower[k] = OR of size[:k]
    for plane in size:
        acc = acc | plane
        lower.append(acc)
    flags = []
    for k in window_bits:
        if k < 0:
            flags.append(_at_most(size, -k, none))      # any other limit
        elif k >= len(size):
            flags.append(ones)                          # beyond the register: always near
        else:
            exact = size[k] & ~above[k + 1] & ~lower[k]     # size == 2**k
            flags.append(~above[k] | exact)                 # size <= 2**k
    conf_above = _suffix_or(conf_l, none)
    full = conf_l[0]
    for p in conf_l[1:]:
        full = full & p
    flags += [gt, lt, ~conf_above[0]]
    flags += [conf_above[m] for m in conf_bits]
    flags += [full, none, ones]
    rival = []
    if rivals:
        # Whole-bin gap between the best rival register and the candidate: far if above RIVAL_FAR.
        rival = [plane[None].expand(circuits, words) for plane in rival_planes.unbind(0)]
        whole = cand_l[frac_bits:]
        one_way, behind = _subtract(rival, whole, none)
        other_way, _ = _subtract(whole, rival, none)
        gap = [(behind & y) | (~behind & x) for x, y in zip(one_way, other_way)]
        gap_above, k = _suffix_or(gap, none), RIVAL_FAR.bit_length() - 1
        low = none
        for plane in gap[:k]:
            low = low | plane
        within = ~gap_above[k] | (gap[k] & ~gap_above[k + 1] & ~low)        # gap <= RIVAL_FAR
        occupied = rival_flags[0][None].expand(circuits, words)
        flags += [occupied & ~within] + [f[None].expand(circuits, words) for f in rival_flags[1:].unbind(0)]
    if gate_flag >= 0:
        near_gate = flags[gate_flag]
        coinc = coinc[None].expand(circuits, words)
        flags += [coinc]
    base = torch.stack(flags + state_l, 1)            # [circuits, inputs, words]
    pool, out = base, base
    # Each gate is a 4-way select. masks are all-ones/all-zeros words (-bit), so
    # (t & x & y) style terms pick the truth-table entry for each ray's (x, y).
    for wire, (t0, t1, t2, t3) in zip(wires, masks):
        index = wire[..., None].expand(-1, -1, -1, words)
        x = pool.gather(1, index[:, :, 0])
        y = pool.gather(1, index[:, :, 1])
        out = (t0 & ~x & ~y) | (t1 & ~x & y) | (t2 & x & ~y) | (t3 & x & y)
        pool = torch.cat((base, out), 1)
    replace, up, down, inc, dec = (out[:, state_bits + i] for i in range(len(ACTIONS)))
    if gate_flag >= 0:
        acquired = state[:, state_bits]
        keep = ~(replace & acquired & ~near_gate & ~coinc)          # ~blocked
        replace, up, down = replace & keep, up & keep, down & keep
        acquired = acquired | (valid & replace)
    if frac_bits == 0 and step_bits == 0:
        stepped = _step_counter(cand_l, up, down)
    else:
        # One-hot step: select value s puts a one on plane frac_bits - s (2**-s of a bin).
        step = [none] * len(cand_l)
        for s in range(2**step_bits):
            hot = ones
            for i in range(step_bits):
                bit = out[:, state_bits + len(ACTIONS) + i]
                hot = hot & (bit if (s >> i) & 1 else ~bit)
            step[frac_bits - s] = hot
        stepped = _step_by(cand_l, up, down, step)
    moved = [(replace & ai) | (~replace & si) for ai, si in zip(a, stepped)]
    if rivals:
        swap = out[:, state_bits + len(ACTIONS) + step_bits]
        target = [none] * frac_bits + rival
        moved = [(swap & ti) | (~swap & mi) for ti, mi in zip(target, moved)]
    cand = torch.stack([(valid & m) | (~valid & p) for m, p in zip(moved, cand_l)], 1)
    counted = _step_counter(conf_l, inc, dec)
    conf = torch.stack([(valid & m) | (~valid & p) for m, p in zip(counted, conf_l)], 1)
    if gate_flag >= 0:
        state = torch.stack([(valid & out[:, i]) | (~valid & p) for i, p in enumerate(state_l)] + [acquired], 1)
    elif state_bits:
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
    if not packable(c):   # window sizes that are not powers of two use the plain simulator
        return simulate_population(config, inputs, codes, photons)
    circuits, rays = len(inputs), len(photons)
    device = photons.device
    cb, qb, sb = c.cand_bits + c.frac_bits, c.conf_bits, c.state_bits
    photons = photons.long()
    valid_all = _pack_bits((photons >= 0).T)                                    # [steps, words]
    arrival = photons.clamp_min(0).T << c.frac_bits                             # [steps, rays], register units
    arrival_all = _pack_bits(((arrival[:, None, :] >> torch.arange(cb, device=device)[None, :, None]) & 1).bool())
    words = valid_all.shape[-1]
    cand = torch.zeros((circuits, cb, words), dtype=torch.long, device=device)
    conf = torch.zeros((circuits, qb, words), dtype=torch.long, device=device)
    # With the coincidence gate, state carries one more plane: the acquired bit.
    state = torch.zeros((circuits, sb + (c.coincidence_depth > 0), words), dtype=torch.long, device=device)
    masks = tuple(tuple(-((codes[:, layer, :, None].long() >> i) & 1) for i in range(4)) for layer in range(c.layers))
    wires = tuple(inputs[:, layer].long() for layer in range(c.layers))         # [circuits, width, 2]
    window_bits = _window_codes(c)
    conf_bits = tuple(level.bit_length() - 1 for level in c.conf_levels)
    rival_planes = rival_flags = coinc = None
    if c.rivals:
        place, votes = rival_trace(c, photons)
        bits = torch.arange(c.cand_bits, device=device)[None, :, None]
        rival_planes = _pack_bits(((place.T[:, None, :] >> bits) & 1).bool())            # [steps, cand_bits, words]
        rival_flags = _pack_bits(torch.stack([votes.T > 0] + [votes.T >= level for level in c.rival_levels], 1))
    gate_flag = c.windows.index(GATE_NEAR) if c.coincidence_depth else -1
    if c.coincidence_depth:
        coinc = _pack_bits(coincidence_trace(c, photons).T)                         # [steps, words]
    run = lambda step: _run_packed(step, cand, conf, state, arrival_all, valid_all, wires, masks, window_bits,
                                   conf_bits, sb, c.frac_bits, c.step_bits, rival_planes, rival_flags, c.rivals,
                                   coinc, gate_flag)
    if _PACKED["step"] is not None:
        try:
            return _unpack_candidates(run(_PACKED["step"]), rays)
        except Exception as error:
            print(f"torch.compile of the search failed ({type(error).__name__}); continuing without it", flush=True)
            _PACKED["step"] = None
    return _unpack_candidates(run(_packed_step), rays)


def _run_packed(step, cand, conf, state, arrival_all, valid_all, wires, masks, window_bits, conf_bits, sb,
                frac_bits=0, step_bits=0, rival_planes=None, rival_flags=None, rivals=0, coinc=None, gate_flag=-1):
    for k in range(len(valid_all)):
        # Without rival registers (or the gate) their arguments are unused placeholders of a fixed type.
        cand, conf, state = step(cand, conf, state, arrival_all[k], valid_all[k], wires, masks, window_bits,
                                 conf_bits, sb, frac_bits, step_bits,
                                 rival_planes[k] if rivals else arrival_all[k],
                                 rival_flags[k] if rivals else arrival_all[k], rivals,
                                 coinc[k] if gate_flag >= 0 else valid_all[k], gate_flag)
    return cand


def _unpack_candidates(cand, rays):
    """Rebuild integer candidates [circuits, rays] from bit-planes [circuits, bits, words]."""
    return sum(_unpack_bits(cand[:, i], rays) << i for i in range(cand.shape[1])).int()


@torch.no_grad()
def simulate_population(config, inputs, codes, photons):
    """Run many circuits on shared rays at once. Returns candidates [circuits, rays].

    Takes wiring [circuits, layers, width, 2] and codes [circuits, layers, width]
    (see pack_circuit), and photons [rays, steps] of arrival bins (-1 = none).
    Matches simulate_stream for every member, so it is safe for discrete search.
    """
    c = config
    circuits, rays = len(inputs), len(photons)
    device = photons.device
    candidate = torch.zeros(circuits, rays, dtype=torch.int32, device=device)
    confidence = torch.zeros_like(candidate)
    state = torch.zeros(circuits, rays, c.state_bits, dtype=torch.int32, device=device)
    top_c, top_q = 2**(c.cand_bits + c.frac_bits) - 1, 2**c.conf_bits - 1
    first = c.state_bits + len(ACTIONS)
    wires = [inputs[:, i, None, :, :].expand(circuits, rays, c.width, 2) for i in range(c.layers)]
    tables = [codes[:, i, None, :] for i in range(c.layers)]
    never, always = torch.zeros_like(candidate, dtype=torch.bool), torch.ones_like(candidate, dtype=torch.bool)
    rival_pos, rival_votes = rival_trace(c, photons) if c.rivals else (None, None)
    coinc = coincidence_trace(c, photons) if c.coincidence_depth else None
    evidence = coincidence_count_trace(c, photons).int() + 1 if c.challenge_cap else None
    acquired = never.clone()
    limits = window_units(c)
    for step in range(photons.shape[1]):
        valid = photons[:, step][None] >= 0
        arrival = photons[:, step].int()[None] << c.frac_bits
        distance = arrival - candidate
        size = distance.abs()
        flags = [size <= units for units in limits]
        flags += [distance > 0, distance < 0, confidence == 0]
        flags += [confidence >= level for level in c.conf_levels]
        flags += [confidence == top_q, never, always]
        if c.rivals:
            votes, place = rival_votes[None, :, step], rival_pos[None, :, step].int()
            flags += [(votes > 0) & ((place - (candidate >> c.frac_bits)).abs() > RIVAL_FAR)]
            flags += [(votes >= level).expand_as(never) for level in c.rival_levels]
        if c.coincidence_depth:
            flags += [coinc[None, :, step].expand_as(never)]
        if c.challenge_cap:
            outnumber = evidence[None, :, step] > confidence.clamp(max=c.challenge_cap)
            flags += [outnumber]
        base = torch.cat((torch.stack(flags, -1).int(), state), -1)
        output = None
        for wire, table in zip(wires, tables):
            pool = base if output is None else torch.cat((base, output), -1)
            index = 2*pool.gather(2, wire[..., 0]) + pool.gather(2, wire[..., 1])
            output = (table >> index) & 1
        new_state = output[..., :c.state_bits]
        replace, up, down, inc, dec = output[..., c.state_bits:first].unbind(-1)
        if c.challenge_cap:
            blocked = (replace == 1) & (size > GATE_NEAR * c.scale) & ~outnumber
            replace, up, down = (torch.where(blocked, 0, x) for x in (replace, up, down))
        elif c.coincidence_depth:
            blocked = (replace == 1) & acquired & (size > GATE_NEAR * c.scale) & ~coinc[None, :, step]
            replace, up, down = (torch.where(blocked, 0, x) for x in (replace, up, down))
            acquired = acquired | (valid & (replace == 1))
        select = sum(output[..., first + i] << i for i in range(c.step_bits))
        amount = (size >> (select + 1)) if c.track == "prop" else (c.scale >> select)
        stepped = (candidate + (up - down) * amount).clamp(0, top_c)
        moved = torch.where(replace == 1, arrival.expand_as(stepped), stepped)
        if c.rivals:
            moved = torch.where(output[..., swap_slot(c)] == 1, (place << c.frac_bits).expand_as(stepped), moved)
        candidate = torch.where(valid, moved, candidate)
        counted = (confidence + inc - dec).clamp(0, top_q)
        if c.challenge_cap:
            counted = torch.where(replace == 1, evidence[None, :, step].clamp(max=top_q).expand_as(counted), counted)
        confidence = torch.where(valid, counted, confidence)
        state = torch.where(valid[..., None], new_state, state)
    return candidate


CHALLENGE_SHAPE = dict(state_bits=8, width=40, layers=3, conf_bits=5, cand_bits=10, windows=(1, 2, 4, 8, 10, 16),
                       frac_bits=4, step_bits=3, conf_levels=(4, 8, 16), coincidence_depth=8, coincidence_window=8,
                       challenge_cap=7, track="prop")


def challenge_circuit(config=None, hit=10, decay_every=8):
    """Hand-written controller for the challenge core (no search).

    hit     = near{hit}: the photon belongs to the incumbent.
    replace = ~hit & outnumber          (the challenger's cluster in the FIFO beats the incumbent's confidence)
    up/down = hit & gt / hit & lt       (proportional: move by |d| >> (select + 1), a running mean)
    inc     = hit; dec = ~hit on every {decay_every}-th miss in a row (3-bit miss counter in state0..2)
    select  = number of (conf4, conf8, conf16, full) that hold: gain 1/2, 1/4, ... 1/32 as support grows.
    """
    c = config or StreamConfig(**CHALLENGE_SHAPE)
    if decay_every != 8 or c.state_bits < 3 or c.step_bits < 3 or c.layers != 3 or not c.challenge_cap:
        raise ValueError("challenge_circuit needs 3 layers, 3 state bits, 3 step bits, the challenge rule, decay_every=8")
    names = input_names(c)
    at = names.index
    h, gt, lt, out = at(window_name(hit)), at("gt"), at("lt"), at("outnumber")
    c4, c8, c16, full, zero = at("conf4"), at("conf8"), at("conf16"), at("full"), at("const0")
    m0, m1, m2 = (at(f"state{i}") for i in range(3))
    base = len(names)
    AND, ANDN, XOR, OR, NOR, COPY = [0, 0, 0, 1], [0, 0, 1, 0], [0, 1, 1, 0], [0, 1, 1, 1], [1, 0, 0, 0], [0, 0, 1, 1]
    NOTA_AND_B = [0, 1, 0, 0]               # ~a & b
    layers = []
    blank = lambda: ([[zero, zero] for _ in range(c.width)], [[0, 0, 0, 0] for _ in range(c.width)])
    # layer 1
    inputs, tables = blank()
    first = [([m1, m0], AND), ([c4, c8], ANDN), ([c16, full], ANDN), ([c8, full], ANDN), ([m1, m0], XOR), ([m2, zero], COPY)]
    for i, (w, t) in enumerate(first):
        inputs[i], tables[i] = w, t
    layers.append({"inputs": inputs, "truth_tables": tables})
    # layer 2: sources are base inputs, then layer-1 outputs at base + i
    L1 = lambda i: base + i
    inputs, tables = blank()
    second = [([L1(0), m2], AND),           # 0: m0 & m1 & m2 (eighth miss in a row if this one misses)
              ([L1(0), m2], XOR),           # 1: next m2 before the hit reset
              ([L1(4), zero], COPY),        # 2: next m1 before the hit reset
              ([L1(1), L1(2)], OR),         # 3: select bit 0
              ([L1(3), zero], COPY),        # 4: select bit 1
              ([full, zero], COPY)]         # 5: select bit 2
    for i, (w, t) in enumerate(second):
        inputs[i], tables[i] = w, t
    layers.append({"inputs": inputs, "truth_tables": tables})
    L2 = lambda i: base + i
    inputs, tables = blank()
    s, first_action = c.state_bits, c.state_bits + len(ACTIONS)
    last = {0: ([h, m0], NOR), 1: ([h, L2(2)], NOTA_AND_B), 2: ([h, L2(1)], NOTA_AND_B),
            s + 0: ([h, out], NOTA_AND_B),             # replace
            s + 1: ([h, gt], AND), s + 2: ([h, lt], AND),  # up, down
            s + 3: ([h, zero], COPY),                    # inc
            s + 4: ([h, L2(0)], NOTA_AND_B),             # dec
            first_action + 0: ([L2(3), zero], COPY), first_action + 1: ([L2(4), zero], COPY),
            first_action + 2: ([L2(5), zero], COPY)}
    for i, (w, t) in last.items():
        inputs[i], tables[i] = w, t
    layers.append({"inputs": inputs, "truth_tables": tables})
    return {"format": "photon-stream-core-v1", "config": asdict(c), "inputs": names,
            "actions": list(ACTIONS) + ["swap"] * (c.rivals > 0), "layers": layers}
