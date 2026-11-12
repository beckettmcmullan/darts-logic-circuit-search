"""Checks for photon replay and the streaming core."""
import json
from pathlib import Path
import sys
import tempfile
import unittest

import torch

from spad import ROOT
from spad.dataset.photons import photon_histogram, sample_photons
from spad.core.stream_model import (StreamConfig, StreamCore, input_names, pack_circuit, packable, rule_circuit,
                          simulate_population, simulate_population_packed, simulate_stream, unpack_circuit)
from spad.hardware.synth import verify
from spad.training.train_stream import mutate
from spad.hardware.verilog import stream_verilog

sys.path.insert(0, str(ROOT/"kaggle"))
from pack import build


def random_core(seed=0, state_bits=3):
    torch.manual_seed(seed)
    model = StreamCore(StreamConfig(state_bits=state_bits, width=12, layers=3))
    for layer in model.layers:
        layer.table_logits.data.normal_()
        layer.routes.data.normal_()
    return model


class PhotonTests(unittest.TestCase):
    def test_replay_stays_inside_occupied_bins(self):
        hist = torch.zeros(2, 672, dtype=torch.long)
        hist[0, 0], hist[0, 671], hist[1, 40] = 100, 100, 200
        photons = sample_photons(hist, 150, torch.Generator().manual_seed(1))
        self.assertEqual(set(photons[0].tolist()), {0, 671})
        self.assertEqual(set(photons[1].tolist()), {40})

    def test_short_rays_are_padded(self):
        hist = torch.zeros(1, 672, dtype=torch.long)
        hist[0, 9] = 3
        photons = sample_photons(hist, 8, torch.Generator().manual_seed(1))
        self.assertEqual(photons.tolist(), [[9, 9, 9, -1, -1, -1, -1, -1]])

    def test_photon_histogram_ignores_padding(self):
        counts = photon_histogram(torch.tensor([[3, 3, 671, -1]]))
        self.assertEqual((counts[0, 3].item(), counts[0, 671].item(), counts.sum().item()), (2, 1, 3))


class CoreTests(unittest.TestCase):
    def test_hard_model_matches_integer_simulator(self):
        for seed in range(5):
            model = random_core(seed)
            photons = torch.randint(-1, 672, (64, 40))
            with torch.no_grad():
                hard = model(photons, hard=True)
            self.assertTrue(torch.equal(hard.long(), simulate_stream(model.circuit(), photons)))

    def test_straight_through_forward_is_boolean(self):
        model = random_core(2)
        photons = torch.randint(0, 672, (16, 20))
        with torch.no_grad():
            self.assertTrue(torch.allclose(model(photons, ste=True), model(photons, hard=True), atol=1e-3))

    def test_padding_leaves_state_unchanged(self):
        model = random_core(3)
        photons = torch.randint(0, 672, (8, 10))
        padded = torch.cat((photons, torch.full((8, 6), -1)), 1)
        circuit = model.circuit()
        self.assertTrue(torch.equal(simulate_stream(circuit, photons), simulate_stream(circuit, padded)))

    def test_rule_finds_a_dominant_return(self):
        photons = torch.full((1, 60), 300)
        photons[0, ::4] = torch.arange(15) * 40
        self.assertLessEqual(abs(simulate_stream(rule_circuit(), photons).item() - 300), 1)

    def test_extreme_bins_do_not_wrap(self):
        for bin_ in (0, 671):
            self.assertEqual(simulate_stream(rule_circuit(), torch.full((1, 30), bin_)).item(), bin_)

    def test_loaded_rule_is_exact_and_gradients_reach_all_parameters(self):
        config = StreamConfig()
        model = StreamCore(config)
        rule = rule_circuit(config)
        model.load_circuit(rule)
        photons = torch.randint(0, 672, (16, 24))
        with torch.no_grad():
            self.assertTrue(torch.equal(model(photons, hard=True).long(), simulate_stream(rule, photons)))
        model = StreamCore(config)
        model(photons, temperature=1.).sum().backward()
        self.assertTrue(all(p.grad is not None and torch.isfinite(p.grad).all() for p in model.parameters()))
        self.assertTrue(any(p.grad.abs().sum() > 0 for p in model.architecture_parameters()))


class FusedForwardTests(unittest.TestCase):
    def test_fused_forward_matches_reference(self):
        for state_bits in (0, 3):
            model = random_core(7, state_bits)
            photons = torch.randint(-1, 672, (64, 40))
            for kwargs in (dict(temperature=1.), dict(temperature=.4, ste=True)):
                fused, reference = model(photons, **kwargs), model.forward_reference(photons, **kwargs)
                self.assertLess(float((fused - reference).abs().max()), 1e-3)
                grads = torch.autograd.grad(fused.sum(), list(model.parameters()))
                expected = torch.autograd.grad(reference.sum(), list(model.parameters()))
                for g, e in zip(grads, expected):
                    self.assertTrue(torch.allclose(g, e, rtol=1e-3, atol=1e-4))
            self.assertTrue(torch.equal(model(photons, hard=True), model.forward_reference(photons, hard=True)))


class PackedPopulationTests(unittest.TestCase):
    def test_packed_simulator_matches_reference_exactly(self):
        torch.manual_seed(5)
        for state_bits in (0, 3):
            config = StreamConfig(state_bits=state_bits, width=12, layers=3)
            circuits = [random_core(seed, state_bits).circuit() for seed in range(4)] + [rule_circuit(config)]
            packed = [pack_circuit(c) for c in circuits]
            inputs, codes = torch.stack([p[0] for p in packed]), torch.stack([p[1] for p in packed])
            photons = torch.randint(0, 672, (130, 90))      # 130 rays: a partly filled last word
            photons[:4] = torch.where(torch.rand(4, 90) < .5, 671, 0)
            photons = torch.where(torch.rand(130, 90) < .1, -1, photons)
            expected = simulate_population(config, inputs, codes, photons)
            self.assertTrue(torch.equal(simulate_population_packed(config, inputs, codes, photons), expected))
            for i, circuit in enumerate(circuits):
                self.assertTrue(torch.equal(simulate_stream(circuit, photons).int(), expected[i]))

    def test_unpackable_windows_fall_back_to_reference(self):
        config = StreamConfig(state_bits=0, windows=(1, 3, 5))
        self.assertFalse(packable(config))
        inputs, codes = pack_circuit(rule_circuit(config, window=3))
        photons = torch.randint(0, 672, (20, 30))
        self.assertTrue(torch.equal(simulate_population_packed(config, inputs[None], codes[None], photons),
                                    simulate_population(config, inputs[None], codes[None], photons)))


class PopulationTests(unittest.TestCase):
    def test_population_matches_single_simulator_for_every_member(self):
        circuits = [random_core(seed).circuit() for seed in range(4)] + [rule_circuit(StreamConfig(state_bits=3, width=12))]
        packed = [pack_circuit(c) for c in circuits]
        inputs, codes = torch.stack([p[0] for p in packed]), torch.stack([p[1] for p in packed])
        photons = torch.randint(-1, 672, (128, 48))
        config = StreamConfig(state_bits=3, width=12)
        result = simulate_population(config, inputs, codes, photons)
        for member, circuit in zip(result, circuits):
            self.assertTrue(torch.equal(member.long(), simulate_stream(circuit, photons)))

    def test_pack_round_trip_preserves_a_circuit(self):
        circuit = random_core(1).circuit()
        self.assertEqual(unpack_circuit(circuit, *pack_circuit(circuit))["layers"], circuit["layers"])


class SearchTests(unittest.TestCase):
    def test_mutations_keep_every_wire_in_range(self):
        config = StreamConfig()
        inputs, codes = pack_circuit(rule_circuit(config))
        base = len(input_names(config))
        generator = torch.Generator().manual_seed(0)
        for kind in ("table", "wire"):
            mutated, tables = mutate(inputs, codes, 256, kind, base, generator)
            self.assertLess(mutated[:, 0].max().item(), base)
            self.assertLess(mutated.max().item(), base + config.width)
            self.assertLess(tables.max().item(), 16)
            changed = (mutated != inputs).flatten(1).any(1) | (tables != codes).flatten(1).any(1)
            self.assertGreater(changed.float().mean().item(), .5)


@unittest.skipUnless((ROOT/"data/processed/metadata.json").exists(), "prepared data absent")
class BundleTests(unittest.TestCase):
    def test_bundle_contains_design_captures_only(self):
        with tempfile.TemporaryDirectory() as name:
            out = Path(name)/"bundle"
            design = build(ROOT/"data", out)
            self.assertEqual([c for c in design if c.isdigit()], ["1", "2", "3", "4", "5", "6"])
            source = json.loads((ROOT/"data/processed/metadata.json").read_text())["captures"]
            held_out = {c for c, v in source.items() if v["split"] in ("test", "fresh_test", "scene_test")}
            files = {p.name for p in (out/"data/processed").iterdir()}
            for capture in held_out | {"7", "8", "9", "10"}:
                self.assertNotIn(f"{capture}.npz", files)
                self.assertNotIn(f"labels_{capture}.npz", files)
            metadata = json.loads((out/"data/processed/metadata.json").read_text())
            self.assertEqual(set(metadata["captures"]), set(design))
            self.assertFalse(set(design) & held_out)


class HardwareTests(unittest.TestCase):
    def test_verilog_netlist_matches_simulator_for_random_circuits(self):
        for seed in range(3):
            circuit = random_core(seed).circuit()
            self.assertEqual(verify(stream_verilog(circuit), "photon_core", circuit, rays=500), 0)

    def test_verilog_handles_a_stateless_core(self):
        config = StreamConfig(state_bits=0, width=8, layers=2)
        circuit = rule_circuit(config)
        self.assertEqual(verify(stream_verilog(circuit), "photon_core", circuit, rays=200), 0)


if __name__ == "__main__":
    unittest.main()
