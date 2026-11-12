"""Test-time sensor perturbations of replayed photon streams (models, not measurements).

The replay (spad/dataset/photons.py) draws arrivals i.i.d. from each pixel's measured histogram,
in random order. Whatever pile-up, dead time and jitter the capture already had is baked into
that histogram; nothing beyond it is modelled. These functions add more, on top of the replay,
with the labels unchanged (the label is where the return really is, so a perturbation that moves
the photons but not the surface is exactly what the circuit should tolerate).

Models (each applied to the photons after the replay's own extra-ambient replacement, so ambient
photons are perturbed like signal ones):

- jitter(sigma): every arrival moves by round(N(0, sigma^2)) bins, clamped to 0..671. Ignores:
  non-Gaussian tails (the diffusion tail of a real SPAD is one-sided and late), jitter that is
  correlated within a frame (laser trigger jitter moves every photon of a cycle together), and
  sub-bin effects. The capture's own IRF is already in the histogram; this is extra on top.
- pile_up(k): first-photon detection with dead time longer than the rest of the laser cycle.
  Each detected arrival is the earliest of k i.i.d. replay draws (same histogram, same extra
  ambient), so one photon per cycle survives and early arrivals win. k = 1 is the replay itself.
  k plays the role of photons arriving per cycle relative to the capture. Ignores: a Poisson
  (not fixed) number per cycle, cycles with no detection (they only thin the stream), dead time
  that spans several cycles (with i.i.d. cycles it only thins too), multi-event TDCs that can
  catch a second, later photon, afterpulsing and crosstalk.
- bit_errors(rate, wire): with probability `rate` per photon, one wire of the 10-bit arrival bus
  is flipped (a fixed wire, or a uniformly random one when wire is None). The value can leave
  0..671 (up to 1023); the core sees it as is, a 672-bin histogram drops it. Ignores: stuck-at
  faults, bursts, and errors in the core's own registers.
"""
import torch

from spad.dataset.photons import sample_photons

BINS = 672
CHUNK = 4096


def _replay_draws(histograms, background, n, generator):
    """n further i.i.d. replay arrivals per ray, with the ray's own extra-ambient replacement."""
    photons = sample_photons(histograms, n, generator)
    noise = torch.randint(0, BINS, photons.shape, generator=generator)
    replace = torch.rand(photons.shape, generator=generator) < background[:, None]
    return torch.where(replace & (photons >= 0), noise, photons)


def pile_up(photons, histograms, background, k, generator):
    """Keep the earliest of k draws per detected photon (k may be a per-ray tensor)."""
    k = torch.as_tensor(k).expand(len(photons)) if torch.as_tensor(k).dim() == 0 else k
    top = int(k.max())
    if top <= 1:
        return photons
    out = []
    for start in range(0, len(photons), CHUNK):
        part, kk = photons[start:start+CHUNK], k[start:start+CHUNK]
        rays, budget = part.shape
        extra = _replay_draws(histograms[start:start+CHUNK], background[start:start+CHUNK],
                              budget*(top - 1), generator).view(rays, budget, top - 1)
        used = torch.arange(top - 1)[None, None] < (kk[:, None, None] - 1)
        extra = torch.where((extra >= 0) & used, extra, BINS)
        earliest = torch.minimum(part, extra.min(-1).values)
        out.append(torch.where(part >= 0, earliest, part))
    return torch.cat(out)


def jitter(photons, sigma, generator):
    """Zero-mean Gaussian timing noise in bins (sigma may be a per-ray tensor), clamped to the range."""
    sigma = torch.as_tensor(sigma, dtype=torch.float32)
    sigma = sigma[:, None] if sigma.dim() == 1 else sigma
    noise = torch.randn(photons.shape, generator=generator) * sigma
    moved = (photons.float() + noise).round().clamp(0, BINS - 1).long()
    return torch.where(photons >= 0, moved, photons)


def bit_errors(photons, rate, generator, wire=None, bits=10):
    flip = torch.rand(photons.shape, generator=generator) < rate
    which = (torch.full(photons.shape, wire, dtype=torch.long) if wire is not None
             else torch.randint(0, bits, photons.shape, generator=generator))
    return torch.where(flip & (photons >= 0), photons ^ (1 << which), photons)


def parse(spec):
    """'clean', 'jitter:2', 'pileup:4', 'bits:0.01', 'bits:0.01@9', or a '+' combination."""
    steps = []
    for part in spec.split("+"):
        if part == "clean":
            continue
        name, value = part.split(":")
        wire = None
        if "@" in value:
            value, wire = value.split("@")
            wire = int(wire)
        steps.append((name, float(value), wire))
    return steps


def apply(spec, photons, histograms, background, generator):
    """Apply a perturbation spec. Pile-up first (which photon is detected), then jitter (timestamp
    noise on the detection), then bit errors (on the wire into the core)."""
    if spec == "mix":            # the training mixture: half the rays, k in 1..4, sigma in [0, 2]
        return randomized(photons, histograms, background, generator)
    if spec == "mixpileup":      # every ray its own pile-up, k uniform in 1..4: one offset cannot fit all
        return randomized(photons, histograms, background, generator, share=1., max_sigma=0.)
    order = {"pileup": 0, "jitter": 1, "bits": 2}
    for name, value, wire in sorted(parse(spec), key=lambda s: order[s[0]]):
        if name == "pileup":
            photons = pile_up(photons, histograms, background, int(value), generator)
        elif name == "jitter":
            photons = jitter(photons, value, generator)
        elif name == "bits":
            photons = bit_errors(photons, value, generator, wire)
        else:
            raise ValueError(spec)
    return photons


def randomized(photons, histograms, background, generator, share=.5, max_k=4, max_sigma=2.):
    """Domain randomization for training: a `share` of rays get pile-up k uniform in 1..max_k and
    jitter sigma uniform in [0, max_sigma]; the rest stay clean."""
    rays = len(photons)
    chosen = torch.rand(rays, generator=generator) < share
    k = torch.where(chosen, torch.randint(1, max_k + 1, (rays,), generator=generator), 1)
    sigma = torch.where(chosen, torch.rand(rays, generator=generator) * max_sigma, 0.)
    photons = pile_up(photons, histograms, background, k, generator)
    return jitter(photons, sigma, generator)
