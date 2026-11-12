"""Settling: how many photons a circuit needs before its answer is good.

The core reads its answer after the last photon. Reading the candidate register after the
first N photons of a stream is exactly the answer an exposure of N photons would give, so one
pass over a 256-photon stream yields the whole error-versus-photons curve on the same pixels.

Streams for the curve: every pixel gets a full 256-photon stream (no count truncation) with its
own extra-ambient level, uniform in [0, max_background], as in the standard conditions.
"""
import torch

from spad.dataset.photons import sample_conditions
from spad.training.baselines import BIN_METERS, metrics
from spad.core.stream_model import (_PACKED, CONF_LEVELS, StreamConfig, _pack_bits, _packed_step,
                                    _unpack_candidates, packable)

READOUTS = (8, 16, 32, 64, 128, 256)
FINE = (4, 6, 8, 10, 12, 16, 20, 24, 28, 32, 40, 48, 56, 64, 80, 96, 112, 128, 160, 192, 224, 256)


def full_streams(histograms, photons=256, max_background=.6, generator=None):
    """Every pixel gets `photons` arrivals (fewer only if its histogram is that small)."""
    return sample_conditions(histograms, photons, photons, max_background, generator)


@torch.no_grad()
def trace_stream(circuit, photons, checkpoints):
    """simulate_stream, also reading the candidate after each checkpoint photon count.

    Returns {N: candidates after the first N photons}. Same integer logic as simulate_stream.
    """
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
    wanted, out = set(checkpoints), {}
    for step in range(max(checkpoints)):
        if step < photons.shape[1]:
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
            replace, up, down, inc, dec = output[:, c.state_bits:c.state_bits+5].T
            stepped = (candidate + up - down).clamp(0, top_c)
            candidate = torch.where(valid, torch.where(replace == 1, arrival, stepped), candidate)
            confidence = torch.where(valid, (confidence + inc - dec).clamp(0, top_q), confidence)
            state = torch.where(valid[:, None], new_state, state)
        if step + 1 in wanted:
            out[step + 1] = candidate.clone()
    return out


@torch.no_grad()
def trace_population_packed(config, inputs, codes, photons, checkpoints):
    """simulate_population_packed, returning candidates [len(checkpoints), circuits, rays]."""
    c = config
    assert packable(c)
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
    wanted, out = set(checkpoints), {}
    step = _PACKED["step"] or _packed_step
    for k in range(max(checkpoints)):
        cand, conf, state = step(cand, conf, state, arrival_all[k], valid_all[k], wires, masks,
                                         window_bits, conf_bits, sb)
        if k + 1 in wanted:
            out[k + 1] = _unpack_candidates(cand, rays)
    return torch.stack([out[n] for n in checkpoints])


def curve_metrics(prediction, target):
    row = metrics(prediction, target)
    return {"mae_m": row["mae_m"], "median_m": row["median_m"], "within_3_bins": row["recall_3_bins"],
            "median_signed_bins": float((prediction.float() - target).median())}


def settle_points(rows, final, share=.70, ratio=1.10):
    """Smallest photon count reaching `share` within 3 bins, and MAE within `ratio` of `final`."""
    counts = sorted(rows)
    first = lambda ok: next((n for n in counts if ok(rows[n])), None)
    return {f"photons_to_{round(share*100)}pct_within_3_bins": first(lambda r: r["within_3_bins"] >= share),
            f"photons_to_mae_within_{round((ratio-1)*100)}pct_of_final": first(lambda r: r["mae_m"] <= ratio*final)}


def settle_curve(circuit, photons, targets, offset, checkpoints=FINE, per_count_offsets=None):
    """Error-versus-photons on fixed pixels. `offset`: one constant (bins) for every readout.

    per_count_offsets (optional, {N: bins}) adds a second curve with an offset per readout.
    """
    raw = trace_stream(circuit, photons, checkpoints)
    single = {n: curve_metrics(raw[n].float() - offset, targets) for n in checkpoints}
    result = {"offset_bins": offset, "single_offset": single,
              "settle_single_offset": settle_points(single, single[max(checkpoints)]["mae_m"])}
    if per_count_offsets is not None:
        own = {n: curve_metrics(raw[n].float() - per_count_offsets[n], targets) for n in checkpoints}
        result["per_count_offset"] = own
        result["per_count_offsets_bins"] = per_count_offsets
        result["settle_per_count_offset"] = settle_points(own, own[max(checkpoints)]["mae_m"])
    return result


def per_count_offsets(circuit, fit_photons, fit_targets, checkpoints=FINE):
    raw = trace_stream(circuit, fit_photons, checkpoints)
    return {n: float((raw[n].float() - fit_targets).median()) for n in checkpoints}


__all__ = ["READOUTS", "FINE", "BIN_METERS", "full_streams", "trace_stream", "trace_population_packed",
           "settle_curve", "settle_points", "per_count_offsets", "curve_metrics"]
