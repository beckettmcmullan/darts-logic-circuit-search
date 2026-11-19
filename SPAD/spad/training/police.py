"""Training-only physics police. None of this is in the chip.

The police never sees labels. It looks only at the photons the circuit saw and asks
whether the circuit's range is a time the physics could have produced:

1. Temporal CFAR (constant false alarm rate). A cell-averaging detector slides a
   pulse-sized window over the photon arrivals, estimates the local background from
   training cells on both sides, and keeps a range only if its count is significant
   under Poisson background at a fixed false alarm rate per ray. If the photons
   contain a real return, the answer must sit on one.

2. Poisson point-process likelihood. Arrivals are modelled as an inhomogeneous
   Poisson process, rate(t) = background + signal * pulse(t - tau). Conditioned on
   the photon count, that is the per-photon density q(t) = (1-w)/672 + w*pulse(t-tau),
   whose negative log-likelihood is the user's
       R_renewal = integral(rate) - sum_i ln(rate(t_i) + rate_dark)
   with the signal share w profiled out and dark counts folded into the background.
   Ranges whose likelihood ratio against the best range exceeds the chi-squared
   cut are rejected, unless they sit on another CFAR-detected return (a second
   surface is physical, just not the strongest one).

An answer is flagged only if it is more than `tolerance` bins (default 3, 0.34 m) from every accepted
range, so a 1-bin quantized circuit is not punished for lacking sub-bin precision.
The pulse shape is measured from training histograms (label-free); the published
IRF is about 3 bins wide, but 3x3 binning and surface slant make real returns ~10.
"""
import torch

from spad.dataset.photons import photon_histogram

BINS = 672


def measure_pulse(histograms, span=(-6, 14), min_snr=8., rays=20000):
    """Median background-subtracted return shape, aligned at each ray's peak."""
    h = histograms[:rays].double()
    peak = h.argmax(1)
    background = h.median(1).values
    snr = (h.max(1).values - background) / (background + 1).sqrt()
    keep = (snr > min_snr) & (peak + span[0] >= 0) & (peak + span[1] < h.shape[1])
    offsets = torch.arange(span[0], span[1] + 1)
    windows = h[keep][:, None].expand(-1, len(offsets), -1).gather(
        2, (peak[keep][:, None] + offsets[None]).unsqueeze(-1)).squeeze(-1) - background[keep][:, None]
    windows = windows / windows.sum(1, keepdim=True).clamp_min(1e-9)
    pulse = windows.median(0).values.clamp_min(0)
    return (pulse / pulse.sum()).float(), -span[0]


def _nearest(mask):
    """For every bin, the nearest bin where mask is True (inf distance if none)."""
    index = torch.arange(mask.shape[1], device=mask.device, dtype=torch.float32).expand_as(mask)
    big = torch.tensor(1e9, device=mask.device)
    last = torch.where(mask, index, -big).cummax(1).values
    following = torch.where(mask, index, big).flip(1).cummin(1).values.flip(1)
    return torch.where(index - last <= following - index, last, following)


class Police:
    def __init__(self, pulse, zero, tolerance=3., pfa=0.01, chi2=6.63, guard=6, train_cells=32,
                 signal_shares=(.02, .05, .1, .2, .3, .45, .6, .75, .9)):
        self.pulse, self.zero = pulse, zero          # pulse[k] at offset k - zero from the peak
        self.tolerance, self.pfa, self.chi2 = tolerance, pfa, chi2
        self.guard, self.train_cells = guard, train_cells
        self.shares = torch.tensor(signal_shares)
        mass = pulse.cumsum(0)
        # CFAR window: the pulse core holding ~85% of the return.
        self.core = (int((mass < .075).sum()), int((mass < .925).sum()) + 1)

    def to(self, device):
        self.pulse, self.shares = self.pulse.to(device), self.shares.to(device)
        return self

    @torch.no_grad()
    def evidence(self, photons):
        """Per-ray accepted ranges from the photons alone. Runs once per photon batch."""
        counts = photon_histogram(photons).float()
        n = counts.sum(1)
        k = len(self.pulse)
        # Likelihood scan over every integer tau: windows[b, tau, j] = counts[b, tau - zero + j].
        padded = torch.nn.functional.pad(counts, (self.zero, k - self.zero - 1))
        windows = padded.unfold(1, k, 1)
        background = (1 - self.shares) / BINS
        log_rate = torch.log(background[:, None] + self.shares[:, None] * self.pulse[None])   # [W, k]
        inside = windows.sum(-1, keepdim=True)
        nll = -((n[:, None, None] - inside) * background.log()[None, None] + windows @ log_rate.T)
        nll = torch.cat((nll, -(n[:, None] * torch.log(torch.tensor(1. / BINS)))[..., None].expand(-1, BINS, 1)), -1)
        nll = nll.min(-1).values                                   # profile out the signal share
        best = nll.min(1, keepdim=True).values
        tau_ml = nll.argmin(1).float()
        likely = 2 * (nll - best) <= self.chi2
        # Cell-averaging CFAR on the pulse core, with guard and training cells each side.
        lo, hi = self.core
        width = hi - lo
        cumulative = torch.nn.functional.pad(counts.cumsum(1), (1, 0))
        def window_sum(start, length):
            a = (torch.arange(BINS, device=counts.device) + start).clamp(0, BINS)
            b = (a + length).clamp(0, BINS)
            return cumulative[:, b] - cumulative[:, a], (b - a).float()
        core, _ = window_sum(lo - self.zero, width)
        left, left_n = window_sum(lo - self.zero - self.guard - self.train_cells, self.train_cells)
        right, right_n = window_sum(hi - self.zero + self.guard, self.train_cells)
        cells = (left_n + right_n).clamp_min(1)
        rate = (left + right + .5) / (cells + 1)                     # +0.5 count prior when cells are empty
        expected = rate * width
        # P(Poisson(expected) >= count) is the regularized lower gamma P(count, expected).
        p_value = torch.where(core >= 1, torch.special.gammainc(core.clamp_min(1), expected), torch.ones_like(core))
        significant = (p_value <= self.pfa / BINS) & (core >= 3)
        # Standard CFAR peak picking: a return is the local maximum of its significant
        # region, not every window position that overlaps the pulse.
        radius = width // 2
        local_max = torch.nn.functional.max_pool1d(core[:, None], 2 * radius + 1, 1, radius)[:, 0]
        detected = significant & (core >= local_max)
        accepted = likely | detected
        return {"cfar_nearest": _nearest(detected), "nearest": _nearest(accepted),
                "likely_width": likely.float().sum(1), "detections": detected.float().sum(1),
                "any_detection": detected.any(1), "tau_ml": tau_ml, "photons": n}

    def offset(self, candidate, evidence):
        """Label-free constant aligning a circuit's output with pulse-peak time."""
        use = evidence["any_detection"].expand_as(candidate)
        gap = (candidate.detach() - evidence["tau_ml"]).masked_fill(~use, float("nan"))
        return gap.nanmedian(-1, keepdim=True).values.nan_to_num(0.)

    def distances(self, candidate, evidence, offset=None):
        """Distance in bins from each answer to the nearest accepted / CFAR-detected range."""
        tau = candidate - (self.offset(candidate, evidence) if offset is None else offset)
        # A NaN answer must not become an index: CPUs turn it into 0, CUDA into an
        # out-of-range value that aborts the run.
        tau = torch.nan_to_num(tau, nan=0., posinf=BINS - 1, neginf=0.)
        slot = tau.detach().round().clamp(0, BINS - 1).long()
        def gap(table):
            table = table.expand(*candidate.shape[:-1], -1, -1) if candidate.dim() > 1 else table
            nearest = table.gather(-1, slot.unsqueeze(-1)).squeeze(-1)
            return (tau - nearest).abs()
        return gap(evidence["nearest"]), gap(evidence["cfar_nearest"])

    def violations(self, candidate, evidence, offset=None):
        """Per-ray flags: unsupported by the likelihood or off every CFAR-detected return."""
        physics, cfar = self.distances(candidate, evidence, offset)
        cfar_bad = (cfar > self.tolerance) & evidence["any_detection"]
        return {"physics": (physics > self.tolerance) | cfar_bad, "cfar": cfar_bad,
                "likelihood": physics > self.tolerance}

    def penalty(self, candidate, evidence):
        """Differentiable hinge, in bins, for gradient training."""
        physics, cfar = self.distances(candidate, evidence)
        cfar = torch.where(evidence["any_detection"], cfar, torch.zeros_like(cfar))
        hinge = lambda d: torch.relu(d - self.tolerance).clamp(max=50.)
        return (hinge(physics) + hinge(cfar)).mean()
