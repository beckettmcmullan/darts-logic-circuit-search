"""Background-only ("no target") photon streams built from the design splits.

Three constructions, each at the same photon counts as the real-return pixels
(log-uniform 16-256, as in sample_conditions):

uniform    Every photon uniform over the 672 bins. Assumes no-target light is flat in time:
           ambient in the low-flux limit, no pile-up, no dark-count structure and no optical
           crosstalk. This is the limit of the training data's own extra-ambient model (b = 1).
residual   Each capture's mean return-removed histogram: the labelled return window
           [target-12, target+30] is cut from every pixel, the rest is normalised per pixel and
           averaged over the capture. Draws use the smooth capture profile, so no artificial
           peaks from re-drawing a handful of photons. Keeps what the sensor sees besides the
           labelled return: an early peak at bins ~20-35 (optical crosstalk or near clutter),
           the slow tail, other surfaces. Assumes the label marks the only target, and that a
           no-target pixel's stray light has the capture-average time profile.
residual_far  The same with bins below 48 (about 3.5 m) also removed: stray light without the
           early peak, for a readout that blanks the crosstalk zone.
pixel      The return-removed histogram of each pixel itself, only for pixels that keep at
           least `min_residual` photons after the cut. Keeps per-pixel second surfaces, but
           re-drawing up to 256 photons from ~100 inflates clustering; a stress test only.

Extra ambient (0-0.6, uniform photons) is added to residual and pixel streams the same way as
to real returns. Real exposure note: in these indoor captures a pixel's residual holds only about
1-3% of its photons, so at a fixed exposure a true no-target pixel would deliver far fewer photons
than a pixel with a return. Using equal counts is the hard case (bright ambient that fills the
photon budget either way).
"""
import torch

from spad.dataset.photons import sample_conditions

BINS = 672
CUT = (-12, 30)


def _counts(rays, low, high, generator, device):
    a, b = torch.log(torch.tensor(float(low))), torch.log(torch.tensor(float(high)))
    u = torch.rand(rays, generator=generator, device=device)
    return torch.exp(a + (b - a) * u.cpu()).round().long().to(device)


def uniform_streams(rays, low=16, high=256, generator=None, device="cpu"):
    """Pure uniform background at log-uniform counts. Returns photons [rays, high], counts."""
    counts = _counts(rays, low, high, generator, device)
    photons = torch.randint(0, BINS, (rays, high), generator=generator, device=device)
    keep = torch.arange(high, device=device)[None] < counts[:, None]
    return torch.where(keep, photons, torch.full_like(photons, -1)), counts


def cut_return(histograms, targets, cut=CUT):
    index = torch.arange(BINS, device=histograms.device)[None]
    offset = index - targets.round().long()[:, None]
    return torch.where((offset >= cut[0]) & (offset <= cut[1]), torch.zeros_like(histograms), histograms)


def residual_profiles(histograms, targets, groups, cut=CUT, min_bin=0):
    """Mean normalised return-removed histogram per group (capture). Returns [groups, 672] float.

    min_bin > 0 also drops the early crosstalk zone (bins below min_bin): "residual_far".
    """
    residual = cut_return(histograms, targets, cut).double()
    residual[:, :min_bin] = 0
    total = residual.sum(1, keepdim=True)
    shares = torch.where(total > 0, residual / total.clamp_min(1), torch.zeros_like(residual))
    n = int(groups.max()) + 1
    profile = torch.zeros(n, BINS, dtype=torch.float64).index_add_(0, groups, shares)
    return profile / profile.sum(1, keepdim=True).clamp_min(1e-12)


def residual_streams(profiles, groups, low=16, high=256, max_background=.6, generator=None):
    """Background-only streams drawn from each ray's capture profile, plus extra ambient."""
    # Scaled to large integer histograms so the shared sampler draws from the smooth shape.
    hist = (profiles[groups] * 1e6).round().long()
    photons, counts, background = sample_conditions(hist, low, high, max_background, generator)
    return photons, counts, background


def pixel_streams(histograms, targets, low=16, high=256, max_background=.6, generator=None,
                  min_residual=128, cut=CUT):
    residual = cut_return(histograms, targets, cut)
    keep = residual.sum(1) >= min_residual
    photons, counts, background = sample_conditions(residual[keep], low, high, max_background, generator)
    return photons, counts, background, keep


def capture_groups(root, split):
    """Capture index of every labelled ray of a split, in load_rays order."""
    import json
    import numpy as np
    metadata = json.loads((root/"processed/metadata.json").read_text())
    groups, g = [], 0
    for capture, info in metadata["captures"].items():
        if info["split"] != split:
            continue
        with np.load(root/"processed"/f"labels_{capture}.npz") as labels:
            groups.append(np.full(int(labels["labelled"].sum()), g))
        g += 1
    return torch.from_numpy(np.concatenate(groups)).long()


def capture_groups_clean(root, split):
    import json
    import numpy as np
    metadata = json.loads((root/"processed/metadata.json").read_text())
    groups, g = [], 0
    for capture, info in metadata["captures"].items():
        if info["split"] != split:
            continue
        with np.load(root/"processed"/f"labels_{capture}.npz") as labels:
            groups.append(np.full(int((labels["labelled"] & labels["clean"]).sum()), g))
        g += 1
    return torch.from_numpy(np.concatenate(groups)).long()
