"""Simulators that also return the final confidence counter and state bits.

Copies of `simulate_stream` and `simulate_population_packed` from spad/core/stream_model.py
(the shared file is not edited). Same arithmetic; they only return more registers.
"""
import torch

from spad.core.stream_model import (ACTIONS, CONF_LEVELS, StreamConfig, _pack_bits, _packed_step,
                                    _unpack_bits, packable)


@torch.no_grad()
def simulate_stream_full(circuit, photons):
    """Integer reference core. Returns (candidate [rays], confidence [rays], state [rays, state_bits])."""
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
    return candidate, confidence, state


def _unpack(planes, rays):
    """Bit-planes [circuits, bits, words] -> integers [circuits, rays]."""
    return sum(_unpack_bits(planes[:, i], rays) << i for i in range(planes.shape[1])).int()


@torch.no_grad()
def simulate_population_full(config, inputs, codes, photons):
    """Packed population simulator. Returns candidates, confidences [circuits, rays] and states
    [circuits, rays, state_bits]."""
    c = config
    if not packable(c):
        raise ValueError("Needs power-of-two windows")
    circuits, rays = len(inputs), len(photons)
    device = photons.device
    cb, qb, sb = c.cand_bits, c.conf_bits, c.state_bits
    photons = photons.long()
    valid_all = _pack_bits((photons >= 0).T)
    arrival = photons.clamp_min(0).T
    arrival_all = _pack_bits(((arrival[:, None, :] >> torch.arange(cb, device=device)[None, :, None]) & 1).bool())
    words = valid_all.shape[-1]
    cand = torch.zeros((circuits, cb, words), dtype=torch.long, device=device)
    conf = torch.zeros((circuits, qb, words), dtype=torch.long, device=device)
    state = torch.zeros((circuits, sb, words), dtype=torch.long, device=device)
    masks = tuple(tuple(-((codes[:, layer, :, None].long() >> i) & 1) for i in range(4)) for layer in range(c.layers))
    wires = tuple(inputs[:, layer].long() for layer in range(c.layers))
    window_bits = tuple(w.bit_length() - 1 for w in c.windows)
    conf_bits = tuple(level.bit_length() - 1 for level in CONF_LEVELS)
    for k in range(len(valid_all)):
        cand, conf, state = _packed_step(cand, conf, state, arrival_all[k], valid_all[k], wires, masks,
                                         window_bits, conf_bits, sb)
    states = torch.stack([_unpack_bits(state[:, i], rays) for i in range(sb)], -1).int() if sb else \
        torch.zeros((circuits, rays, 0), dtype=torch.int32, device=device)
    return _unpack(cand, rays), _unpack(conf, rays), states
