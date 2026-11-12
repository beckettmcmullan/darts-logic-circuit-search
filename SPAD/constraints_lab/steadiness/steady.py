"""Steadiness of the range offset across photon counts and background levels.

Offset = median signed error (prediction minus label, in range bins) within a bucket of pixels.
Steadiness = spread (max minus min) of those offsets over buckets. A constant offset cancels in
the spread, so no offset fit is needed.

Two ways to measure it:

* `audit_spread`: the audit's own buckets on randomly drawn conditions (photon count log-uniform
  16-256, extra ambient uniform 0-0.6). Each bucket holds different pixels, so pixel-to-pixel
  differences leak into the spread.
* `grid_spread`: a paired design. Each pixel gets one photon stream with common random numbers,
  and is read out at fixed photon counts (23, 45, 91, 181: the geometric centres of the audit's
  16-32 ... 128-256 buckets; prefixes of one stream) under three fixed extra-ambient levels
  (0.1, 0.3, 0.5: centres of the audit's background buckets; the same replacement draws, so a
  photon replaced at 0.1 is also replaced at 0.3). Every bucket then holds the same pixels, and
  one packed simulation per level gives all four counts.
"""
import torch

from spad.core.stream_model import (CONF_LEVELS, _PACKED, _pack_bits, _packed_step, _unpack_candidates,
                                    packable, simulate_population)
from spad.dataset.photons import sample_photons

COUNTS = (23, 45, 91, 181)
LEVELS = (.1, .3, .5)
PHOTON_BUCKETS = ((16, 32), (32, 64), (64, 128), (128, 257))
BACKGROUND_BUCKETS = ((0, .2), (.2, .4), (.4, 1.01))


def audit_spread(error, counts, background):
    """error [members, rays] (prediction - target). Returns photon offsets, background offsets, spreads."""
    photon = torch.stack([error[:, (counts >= lo) & (counts < hi)].median(-1).values for lo, hi in PHOTON_BUCKETS], -1)
    ambient = torch.stack([error[:, (background >= lo) & (background < hi)].median(-1).values
                           for lo, hi in BACKGROUND_BUCKETS], -1)
    return photon, ambient, photon.amax(-1) - photon.amin(-1), ambient.amax(-1) - ambient.amin(-1)


def grid_photons(histograms, generator, levels=LEVELS, max_count=max(COUNTS), bins=672):
    """One stream per pixel, [levels, rays, max_count], common random numbers across levels."""
    device = histograms.device
    signal = sample_photons(histograms, max_count, generator)
    noise = torch.randint(0, bins, signal.shape, generator=generator, device=device)
    uniform = torch.rand(signal.shape, generator=generator, device=device)
    return torch.stack([torch.where((uniform < b) & (signal >= 0), noise, signal) for b in levels])


@torch.no_grad()
def simulate_checkpoints(config, inputs, codes, photons, checkpoints=COUNTS):
    """simulate_population_packed, but returns candidates after each checkpoint photon count.

    Returns [len(checkpoints), circuits, rays]. Same arithmetic as the shared packed simulator.
    """
    c = config
    if not packable(c):
        return torch.stack([simulate_population(config, inputs, codes, photons[:, :k]) for k in checkpoints])
    rays = len(photons)
    device = photons.device
    cb, qb, sb = c.cand_bits, c.conf_bits, c.state_bits
    photons = photons.long()
    valid_all = _pack_bits((photons >= 0).T)
    arrival = photons.clamp_min(0).T
    arrival_all = _pack_bits(((arrival[:, None, :] >> torch.arange(cb, device=device)[None, :, None]) & 1).bool())
    words = valid_all.shape[-1]
    circuits = len(inputs)
    cand = torch.zeros((circuits, cb, words), dtype=torch.long, device=device)
    conf = torch.zeros((circuits, qb, words), dtype=torch.long, device=device)
    state = torch.zeros((circuits, sb, words), dtype=torch.long, device=device)
    masks = tuple(tuple(-((codes[:, layer, :, None].long() >> i) & 1) for i in range(4)) for layer in range(c.layers))
    wires = tuple(inputs[:, layer].long() for layer in range(c.layers))
    window_bits = tuple(w.bit_length() - 1 for w in c.windows)
    conf_bits = tuple(level.bit_length() - 1 for level in CONF_LEVELS)
    step = _PACKED["step"] or _packed_step
    out, wanted = [], set(checkpoints)
    for k in range(max(checkpoints)):
        cand, conf, state = step(cand, conf, state, arrival_all[k], valid_all[k], wires, masks, window_bits, conf_bits, sb)
        if k + 1 in wanted:
            out.append(_unpack_candidates(cand, rays))
    return torch.stack(out)


def grid_errors(config, inputs, codes, grid, targets):
    """Signed error [levels, counts, members, rays]."""
    return torch.stack([simulate_checkpoints(config, inputs, codes, level).float() - targets for level in grid])


def grid_spread(errors):
    """From grid_errors: photon offsets [members, counts], background offsets [members, levels], spreads."""
    levels, counts, members, rays = errors.shape
    photon = errors.permute(2, 1, 0, 3).reshape(members, counts, -1).median(-1).values
    ambient = errors.permute(2, 0, 1, 3).reshape(members, levels, -1).median(-1).values
    return photon, ambient, photon.amax(-1) - photon.amin(-1), ambient.amax(-1) - ambient.amin(-1)


class GridSample:
    """A fixed paired steadiness sample from one split: scores many circuits on the same pixels."""

    def __init__(self, split, rays, generator):
        histograms, targets = split
        pick = torch.randperm(len(targets), generator=generator, device=targets.device)[:rays]
        self.grid, self.targets = grid_photons(histograms[pick], generator), targets[pick].float()

    def __call__(self, config, inputs, codes):
        """Returns (photon spread, background spread, photon offsets, background offsets) per member."""
        photon, ambient, ps, bs = grid_spread(grid_errors(config, inputs, codes, self.grid, self.targets))
        return ps, bs, photon, ambient
