"""Whole-core area estimate for photon-stream circuits, fitted to real Yosys + ASAP7 synthesis.

The old training penalty summed the controller's 48 truth tables. That misses most of
the chip: the fixed datapath (candidate register, distance comparator, window flags,
confidence counter) is about 85% of the synthesized area, and synthesis deletes the
parts of it no live gate reads. So the area a circuit really costs depends on which
flags and actions it uses, which the controller's wiring decides.

estimate() counts, per circuit (vectorized over a population):
  - the cells of live controller gates (gates whose output reaches an action or a
    state bit that is itself read), from the ASAP7 truth-table costs,
  - a flip-flop per live state bit,
  - each datapath flag and action that a live gate reads or that is not constant 0,
and weights them with coefficients fitted by least squares to synthesized circuits.

Fit (from SPAD/):  ../.venv/bin/python -m spad.hardware.area_model --circuits 400
"""
import argparse
import json
from pathlib import Path
import random

import torch

from spad import ROOT
from spad.core.stream_model import ACTIONS, StreamConfig, input_names, pack_circuit, unpack_circuit

MODEL_PATH = Path(__file__).with_name("area_model.json")
CONFIDENCE_FLAGS = ("zero", "conf2", "conf4", "conf8", "full")


def feature_names(config):
    names = input_names(config)
    flags = [n for n in names if not n.startswith(("state", "const"))]
    return (["live_gates", "state_flops"] + [f"flag_{n}" for n in flags] + ["any_distance_flag", "confidence_counter"]
            + ["action_replace", "action_up", "action_down", "counter_inc", "counter_dec", "replace_always"]
            + ["intercept"])


def _uses(codes):
    """Whether each gate's truth table depends on input a and on input b. codes: 4-bit, bit index 2a+b."""
    bit = lambda k: (codes >> k) & 1
    t0, t1, t2, t3 = bit(0), bit(1), bit(2), bit(3)
    return (t0 != t2) | (t1 != t3), (t0 != t1) | (t2 != t3)


def usage(config, inputs, codes, probe):
    """Feature matrix [members, features] for circuits inputs [M, L, W, 2], codes [M, L, W].

    A signal counts only if it is live (reaches an action or a read state bit) and it
    varies while the circuit runs on `probe` photons; constant signals cost no logic.
    """
    c = config
    names = input_names(c)
    base = len(names)
    first_state = base - c.state_bits
    members, layers, width = codes.shape
    device = codes.device
    codes, inputs = codes.long(), inputs.long()
    flag_varies, gate_varies, gate_on = activity(c, inputs, codes, probe.to(device))
    source_varies = torch.cat((flag_varies, gate_varies.reshape(members, -1)), 1)
    uses_a, uses_b = _uses(codes)
    action_slice = slice(c.state_bits, c.state_bits + len(ACTIONS))
    actions = torch.zeros(members, width, dtype=torch.bool, device=device)
    actions[:, action_slice] = gate_varies[:, -1, action_slice]
    state_live = torch.zeros(members, c.state_bits, dtype=torch.bool, device=device)
    for _ in range(c.state_bits + 1):                  # a read state bit makes its next-state gate live
        live = [None] * layers
        reads = torch.zeros(members, base + width * layers, dtype=torch.long, device=device)
        wanted = actions.clone()
        if c.state_bits:
            wanted[:, :c.state_bits] |= state_live
        live[-1] = wanted & gate_varies[:, -1]
        for layer in range(layers - 1, -1, -1):
            if layer < layers - 1:
                start = base + width * layer
                live[layer] = (reads[:, start:start + width] > 0) & gate_varies[:, layer]
            for port, used in ((0, uses_a), (1, uses_b)):
                source = inputs[:, layer, :, port]
                mark = live[layer] & used[:, layer] & source_varies.gather(1, source)
                reads.scatter_add_(1, source, mark.long())   # scatter_add: two readers of one wire both count
        read = reads > 0
        new_state = read[:, first_state:base] if c.state_bits else state_live
        if torch.equal(new_state, state_live):
            break
        state_live = new_state
    gate_live = torch.stack(live, 1)
    flags = [i for i, n in enumerate(names) if not n.startswith(("state", "const"))]
    distance = [i for i, n in enumerate(names) if n.startswith("near") or n in ("gt", "lt")]
    confidence = [names.index(n) for n in CONFIDENCE_FLAGS]
    counter = read[:, confidence].any(1)
    acting = gate_varies[:, -1, action_slice]
    replace, up, down, inc, dec = acting.unbind(-1)
    replace_always = gate_on[:, -1, c.state_bits] & ~replace
    column = lambda x: x.float()[:, None]
    return torch.cat((column(gate_live.sum((1, 2))), column(state_live.sum(1)), read[:, flags].float(),
                      column(read[:, distance].any(1)), column(counter), column(replace), column(up), column(down),
                      column(inc & counter), column(dec & counter), column(replace_always),
                      torch.ones(members, 1, device=device)), 1)


def probe_photons(rays=64, steps=48, seed=0, device=None):
    """Varied photon streams (a return near a random range plus ambient) for activity checks."""
    g = torch.Generator().manual_seed(seed)
    centre = torch.randint(0, 672, (rays, 1), generator=g)
    photons = (centre + torch.randint(-12, 13, (rays, steps), generator=g)).clamp(0, 671)
    noise = torch.rand(rays, steps, generator=g) < .3
    return torch.where(noise, torch.randint(0, 672, (rays, steps), generator=g), photons).to(device)


@torch.no_grad()
def activity(config, inputs, codes, photons):
    """Which signals ever change while the circuits run from reset.

    Returns (flag_varies [M, base], gate_varies [M, layers, width]): True where a datapath
    flag, state bit or gate output takes both values on some valid photon. A signal stuck
    at one value is a constant to synthesis, which deletes the logic behind it.
    """
    from spad.core.stream_model import CONF_LEVELS
    c = config
    members, rays = len(inputs), len(photons)
    device = photons.device
    candidate = torch.zeros(members, rays, dtype=torch.long, device=device)
    confidence = torch.zeros_like(candidate)
    state = torch.zeros(members, rays, c.state_bits, dtype=torch.long, device=device)
    top_c, top_q = 2**c.cand_bits - 1, 2**c.conf_bits - 1
    gates = torch.arange(c.width, device=device)
    tables = ((codes.long()[..., None] >> torch.arange(4, device=device)) & 1)          # [M, L, W, 4]
    base = len(input_names(c))
    seen1 = torch.zeros(members, base + c.layers * c.width, dtype=torch.bool, device=device)
    seen0 = torch.zeros_like(seen1)
    for step in range(photons.shape[1]):
        arrival, valid = photons[:, step].long()[None], photons[:, step][None] >= 0
        distance = arrival - candidate
        size = distance.abs()
        flags = [size <= w for w in c.windows] + [distance > 0, distance < 0, confidence == 0]
        flags += [confidence >= level for level in CONF_LEVELS]
        flags += [confidence == top_q, torch.zeros_like(valid.expand(members, -1)), torch.ones_like(valid.expand(members, -1))]
        pool = torch.cat((torch.stack(flags, -1).long(), state), -1)                     # [M, R, base]
        for layer in range(c.layers):
            a = pool.gather(2, inputs[:, layer, None, :, 0].long().expand(-1, rays, -1))
            b = pool.gather(2, inputs[:, layer, None, :, 1].long().expand(-1, rays, -1))
            table = tables[:, layer, None].expand(-1, rays, -1, -1)
            out = table.gather(3, (2 * a + b)[..., None])[..., 0]
            pool = torch.cat((pool, out), -1)
        mask = valid[..., None].expand_as(pool)
        seen1 |= (pool.bool() & mask).any(1)
        seen0 |= (~pool.bool() & mask).any(1)
        new_state = out[..., :c.state_bits]
        replace, up, down, inc, dec = out[..., c.state_bits:c.state_bits + len(ACTIONS)].unbind(-1)
        stepped = (candidate + up - down).clamp(0, top_c)
        candidate = torch.where(valid, torch.where(replace == 1, arrival, stepped), candidate)
        confidence = torch.where(valid, (confidence + inc - dec).clamp(0, top_q), confidence)
        state = torch.where(valid[..., None], new_state, state)
    varies = seen0 & seen1
    return varies[:, :base], varies[:, base:].reshape(members, c.layers, c.width), seen1[:, base:].reshape(members, c.layers, c.width)


class AreaModel:
    """Fitted coefficients; estimate() returns synthesized-area estimates in ASAP7 µm²."""

    def __init__(self, path=MODEL_PATH, device=None):
        saved = json.loads(Path(path).read_text())
        self.names, self.coefficients = saved["features"], torch.tensor(saved["coefficients"], device=device)
        self.fit = saved.get("fit", {})
        self.probe = probe_photons(device=device)

    def to(self, device):
        self.coefficients, self.probe = self.coefficients.to(device), self.probe.to(device)
        return self

    def features(self, config, inputs, codes):
        found = usage(config, inputs, codes, self.probe)
        if found.shape[1] != len(self.names):
            raise ValueError("Area model was fitted for a different datapath configuration")
        return found

    def estimate(self, config, inputs, codes):
        return self.features(config, inputs, codes) @ self.coefficients

    def circuit_area(self, circuit):
        config = StreamConfig(**circuit["config"])
        inputs, codes = pack_circuit(circuit, self.coefficients.device)
        return float(self.estimate(config, inputs[None], codes[None])[0])


def degenerate(circuit, rays=512, seed=0):
    """True if the circuit's output is the same for every ray of varied photon streams."""
    from spad.core.stream_model import simulate_stream
    g = torch.Generator().manual_seed(seed)
    centre = torch.randint(0, 672, (rays, 1), generator=g)
    photons = (centre + torch.randint(-12, 13, (rays, 64), generator=g)).clamp(0, 671)
    noise = torch.rand(rays, 64, generator=g) < .3
    photons = torch.where(noise, torch.randint(0, 672, (rays, 64), generator=g), photons)
    return bool((simulate_stream(circuit, photons) == simulate_stream(circuit, photons)[0]).all())


def _variants(templates, count, seed):
    """Diverse circuits: trained circuits with random edits, and with random gates switched off."""
    rng = random.Random(seed)
    for k in range(count):
        circuit = json.loads(json.dumps(rng.choice(templates)))
        config = StreamConfig(**circuit["config"])
        sources = len(input_names(config))
        for _ in range(rng.choice((0, 2, 5, 10, 20, 40))):
            layer = rng.randrange(config.layers)
            gate = rng.randrange(config.width)
            spec = circuit["layers"][layer]
            if rng.random() < .5:
                spec["truth_tables"][gate][rng.randrange(4)] ^= 1
            else:
                spec["inputs"][gate][rng.randrange(2)] = rng.randrange(sources + config.width * (layer > 0))
        for _ in range(rng.choice((0, 0, 3, 8, 16))):     # remove logic, as an area search would
            layer = rng.randrange(config.layers)
            circuit["layers"][layer]["truth_tables"][rng.randrange(config.width)] = [0, 0, 0, 0]
        yield f"variant{k}", circuit


def main():
    from spad.hardware.synth import synthesize
    from spad.hardware.verilog import stream_verilog
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--data", type=Path, default=ROOT/"data")
    parser.add_argument("--runs", type=Path, nargs="*",
                        default=[ROOT/"runs/2026-11-10_kaggle-t4_batch3_fused-larger-search"])
    parser.add_argument("--circuits", type=int, default=400)
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--out", type=Path, default=MODEL_PATH)
    args = parser.parse_args()
    templates = [json.loads(p.read_text()) for run in args.runs for p in sorted(run.glob("*/circuit.json"))]
    templates = [t for t in templates if t["config"]["state_bits"] == 4]
    config = StreamConfig(**templates[0]["config"])
    probe = probe_photons()
    # Synthesis results are cached, so a refit or a longer fit reuses earlier work.
    cache_path = ROOT/"runs/area_model_samples.json"
    cache = json.loads(cache_path.read_text()) if cache_path.exists() else {}
    rows, areas = [], []
    for name, circuit in _variants(templates, args.circuits, args.seed):
        key = json.dumps(circuit["layers"], separators=(",", ":"))
        if key not in cache:
            cache[key] = synthesize(stream_verilog(circuit), "photon_core", args.data)["area"]
            if len(cache) % 50 == 0:
                cache_path.write_text(json.dumps(cache))
                print(f"{len(cache)} synthesized", flush=True)
        if cache[key] is None or degenerate(circuit):
            # Circuits whose range output can never change synthesize to almost nothing (Yosys proves
            # the registers constant). They are useless and fail any accuracy limit, so the model is
            # fitted only on circuits that actually measure something.
            continue
        inputs, codes = pack_circuit(circuit)
        rows.append(usage(config, inputs[None], codes[None], probe)[0])
        areas.append(cache[key])
    cache_path.parent.mkdir(exist_ok=True)
    cache_path.write_text(json.dumps(cache))
    print(f"{len(areas)} circuits used, {args.circuits - len(areas)} empty or degenerate", flush=True)
    x, y = torch.stack(rows).double(), torch.tensor(areas).double()
    order = torch.randperm(len(y), generator=torch.Generator().manual_seed(args.seed))
    held = order[:len(y) // 5]
    fit = order[len(y) // 5:]
    ridge = 1e-3 * torch.eye(x.shape[1], dtype=x.dtype)
    solve = lambda idx: torch.linalg.solve(x[idx].T @ x[idx] + ridge, x[idx].T @ y[idx])
    coefficients = solve(fit)
    error = (x[held] @ coefficients - y[held]).abs()
    report = {"circuits": len(y), "held_out": len(held), "held_out_mean_abs_error_um2": float(error.mean()),
              "held_out_max_abs_error_um2": float(error.max()), "area_range_um2": [float(y.min()), float(y.max())]}
    coefficients = solve(torch.arange(len(y)))          # final fit on everything
    names = feature_names(config)
    args.out.write_text(json.dumps({"features": names, "coefficients": coefficients.tolist(), "fit": report,
                                    "config": templates[0]["config"],
                                    "note": "Yosys + ABC (-D 1000) with ASAP7 RVT TT Liberty; area in µm²"}, indent=2) + "\n")
    print(json.dumps(report, indent=2))
    for name, value in zip(names, coefficients.tolist()):
        print(f"  {name:22s} {value:7.3f}")


if __name__ == "__main__":
    main()
