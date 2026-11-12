"""Replay photon arrivals from real histograms and load audited labels.

A histogram discards arrival order, so draws are i.i.d. from each pixel's
empirical arrival distribution. Draws use replacement, a negligible difference
when the budget is far below the pixel's total counts. This replay keeps any
pile-up already present in the histogram: thinning does not model the lower
flux a real short exposure would see, and it has no detector dead time.
"""
import json

import numpy as np
import torch


def sample_photons(histograms, budget, generator=None):
    """Return [rays, budget] arrival bins, padded with -1 where a ray has too few."""
    histograms = histograms.long()
    cumulative = histograms.cumsum(-1)
    totals = cumulative[:, -1:]
    device = histograms.device
    ranks = (torch.rand(len(histograms), budget, generator=generator, device=device) * totals).long()
    photons = torch.searchsorted(cumulative, ranks, right=True)
    valid = torch.arange(budget, device=device)[None] < totals
    return torch.where(valid, photons, torch.full_like(photons, -1))


def sample_conditions(histograms, min_photons, max_photons, max_background, generator=None, bins=672):
    """Photons under randomized conditions, so a circuit cannot rely on one exposure.

    Each ray draws its own photon count, log-uniform in [min_photons, max_photons],
    and its own extra-ambient level b, uniform in [0, max_background]. Each photon is
    then replaced, with probability b, by an arrival uniform over the 672 bins: added
    background light on top of the ambient already in the capture. Uniform ambient
    is the low-flux limit; strong pile-up would skew it toward early bins.
    Returns photons [rays, max_photons] padded with -1, plus each ray's count and b.
    """
    device = histograms.device
    rays = len(histograms)
    photons = sample_photons(histograms, max_photons, generator)
    low, high = torch.log(torch.tensor(float(min_photons))), torch.log(torch.tensor(float(max_photons)))
    uniform = torch.rand(rays, generator=generator, device=device)
    counts = torch.exp(low + (high - low) * uniform.cpu()).round().long().to(device)
    background = torch.rand(rays, generator=generator, device=device) * max_background
    noise = torch.randint(0, bins, photons.shape, generator=generator, device=device)
    replace = torch.rand(photons.shape, generator=generator, device=device) < background[:, None]
    photons = torch.where(replace & (photons >= 0), noise, photons)
    keep = torch.arange(max_photons, device=device)[None] < counts[:, None]
    photons = torch.where(keep, photons, torch.full_like(photons, -1))
    return photons, counts, background


def photon_histogram(photons, bins=672):
    """Accumulate replayed photons into the histogram a counter array would hold."""
    slots = torch.where(photons >= 0, photons, torch.full_like(photons, bins))
    result = torch.zeros(len(photons), bins + 1, dtype=torch.long, device=photons.device)
    result.scatter_add_(1, slots, torch.ones_like(photons))
    return result[:, :bins]


def load_rays(root, split, clean_only=False):
    """Return (histograms, refined target bins, clean mask) for a named split."""
    metadata = json.loads((root/"processed/metadata.json").read_text())
    histograms, targets, clean = [], [], []
    for capture, info in metadata["captures"].items():
        if info["split"] != split:
            continue
        with np.load(root/"processed"/f"{capture}.npz") as d, \
                np.load(root/"processed"/f"labels_{capture}.npz") as labels:
            keep = labels["labelled"] & (labels["clean"] if clean_only else True)
            histograms.append(d["histograms"][keep].astype(np.int32))
            targets.append(labels["target_bins"][keep])
            clean.append(labels["clean"][keep])
    if not histograms:
        raise ValueError(f"Empty split {split}")
    return (torch.from_numpy(np.concatenate(histograms)), torch.from_numpy(np.concatenate(targets)),
            torch.from_numpy(np.concatenate(clean)))
