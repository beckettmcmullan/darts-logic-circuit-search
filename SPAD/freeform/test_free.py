"""The three implementations of the free-form core must agree exactly.

Run from SPAD/:  ../.venv/bin/python -m unittest freeform.test_free -v
"""
import unittest

import torch

from freeform.free_model import (FreeConfig, FreeCore, live_gates, pack_circuit, pack_photons, simulate_free,
                                 simulate_population_packed, unpack_circuit)


def random_model(seed, config):
    torch.manual_seed(seed)
    model = FreeCore(config, init="random")
    for routes, logits in zip(model.routes, model.table_logits):
        routes.data.normal_()
        logits.data.normal_()
    return model


class FreeCoreParity(unittest.TestCase):
    def setUp(self):
        self.config = FreeConfig(state_bits=12, width=20, layers=3)
        torch.manual_seed(0)
        self.photons = torch.randint(-1, 672, (200, 40))

    def test_straight_through_forward_equals_integer_circuit(self):
        for seed in range(3):
            model = random_model(seed, self.config)
            expected = simulate_free(model.circuit(), self.photons)
            got = model(self.photons, temperature=.5, ste=True)
            self.assertTrue(torch.equal(got.round().long(), expected))

    def test_packed_population_equals_integer_circuit(self):
        circuits = [random_model(seed, self.config).circuit() for seed in range(4)]
        packed = [pack_circuit(c) for c in circuits]
        inputs, codes = torch.stack([p[0] for p in packed]), torch.stack([p[1] for p in packed])
        got = simulate_population_packed(self.config, inputs, codes,
                                         pack_photons(self.photons, self.config.arrival_bits), len(self.photons))
        for k, circuit in enumerate(circuits):
            self.assertTrue(torch.equal(got[k], simulate_free(circuit, self.photons)))

    def test_readouts_after_each_photon(self):
        model = random_model(3, self.config)
        circuit = model.circuit()
        values, bits = model(self.photons, temperature=.5, ste=True, trajectory=True)
        self.assertEqual(tuple(bits.shape), (40, 200, self.config.arrival_bits))
        inputs, codes = pack_circuit(circuit)
        packed = simulate_population_packed(self.config, inputs[None], codes[None],
                                            pack_photons(self.photons, self.config.arrival_bits), 200, readouts=(5, 17))
        for row, k in enumerate((5, 17, 40)):
            expected = simulate_free(circuit, self.photons[:, :k])
            self.assertTrue(torch.equal(values[k - 1].round().long(), expected))
            self.assertTrue(torch.equal(packed[row, 0], expected))

    def test_pack_round_trip_and_load(self):
        model = random_model(5, self.config)
        circuit = model.circuit()
        self.assertEqual(unpack_circuit(circuit, *pack_circuit(circuit)), circuit)
        other = FreeCore(self.config)
        other.load_circuit(circuit)
        self.assertEqual(other.circuit(), circuit)

    def test_flip_flops_hold_without_a_photon(self):
        circuit = random_model(1, self.config).circuit()
        dense = torch.randint(0, 672, (50, 10))
        gaps = torch.full((50, 20), -1)
        gaps[:, ::2] = dense
        self.assertTrue(torch.equal(simulate_free(circuit, gaps), simulate_free(circuit, dense)))

    def test_live_gate_count_is_bounded(self):
        report = live_gates(random_model(2, self.config).circuit())
        self.assertLessEqual(report["live_gates"], report["total_gates"])
        self.assertGreaterEqual(report["flip_flops_used"], self.config.arrival_bits)


if __name__ == "__main__":
    unittest.main()
