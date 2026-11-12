"""Accelerator parity checks. Set SPAD_TEST_DEVICE, or CUDA is used when present.

Kept free of Yosys so it runs first on a fresh Kaggle session.
"""
import os
import unittest

import torch

from spad.dataset.photons import sample_photons
from spad.core.stream_model import (StreamConfig, StreamCore, pack_circuit, rule_circuit, simulate_population,
                                    simulate_population_packed, simulate_stream)

DEVICE = os.environ.get("SPAD_TEST_DEVICE") or ("cuda" if torch.cuda.is_available() else None)


def random_model(seed):
    torch.manual_seed(seed)
    model = StreamCore(StreamConfig())
    for layer in model.layers:
        layer.table_logits.data.normal_()
        layer.routes.data.normal_()
    return model


@unittest.skipUnless(DEVICE, "no accelerator available")
class DeviceParity(unittest.TestCase):
    def test_simulators_match_cpu_exactly(self):
        for seed in range(3):
            model = random_model(seed)
            circuit = model.circuit()
            photons = torch.randint(-1, 672, (512, 64))
            expected = simulate_stream(circuit, photons)
            self.assertTrue(torch.equal(simulate_stream(circuit, photons.to(DEVICE)).cpu(), expected))
            inputs, codes = pack_circuit(circuit, DEVICE)
            result = simulate_population(model.config, inputs[None], codes[None], photons.to(DEVICE))
            self.assertTrue(torch.equal(result[0].long().cpu(), expected))
            packed = simulate_population_packed(model.config, inputs[None], codes[None], photons.to(DEVICE))
            self.assertTrue(torch.equal(packed[0].long().cpu(), expected))

    def test_fused_training_forward_matches_cpu(self):
        model = random_model(5)
        photons = torch.randint(-1, 672, (256, 64))
        expected = model(photons, temperature=.5, ste=True)
        device_model = random_model(5).to(DEVICE)
        result = device_model(photons.to(DEVICE), temperature=.5, ste=True).cpu()
        self.assertLess(float((result - expected).abs().max()), 1e-3)
        self.assertLess(float((device_model.forward_reference(photons.to(DEVICE), temperature=.5, ste=True).cpu()
                               - result).abs().max()), 1e-3)

    def test_hard_float_model_matches_cpu_exactly(self):
        model = random_model(4)
        photons = torch.randint(-1, 672, (512, 64))
        with torch.no_grad():
            expected = model(photons, hard=True)
            result = model.to(DEVICE)(photons.to(DEVICE), hard=True).cpu()
        self.assertTrue(torch.equal(result, expected))

    def test_rule_loads_onto_a_device_model(self):
        config = StreamConfig()
        rule = rule_circuit(config)
        model = StreamCore(config).to(DEVICE)
        model.load_circuit(rule)
        photons = torch.randint(0, 672, (128, 32))
        with torch.no_grad():
            result = model(photons.to(DEVICE), hard=True).cpu().long()
        self.assertTrue(torch.equal(result, simulate_stream(rule, photons)))

    def test_gradients_reach_parameters(self):
        model = random_model(5).to(DEVICE)
        photons = torch.randint(0, 672, (64, 24), device=DEVICE)
        model(photons, temperature=.5, ste=True).sum().backward()
        self.assertTrue(all(p.grad is not None and torch.isfinite(p.grad).all() for p in model.parameters()))

    def test_sampling_stays_on_device_and_in_range(self):
        histograms = torch.zeros(4, 672, dtype=torch.long, device=DEVICE)
        histograms[:, 300] = 50
        generator = torch.Generator(device=DEVICE).manual_seed(0)
        self.assertEqual(set(sample_photons(histograms, 16, generator).unique().tolist()), {300})


if __name__ == "__main__":
    unittest.main()
