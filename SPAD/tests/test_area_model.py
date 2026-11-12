import unittest

import torch

from spad.core.stream_model import StreamConfig, pack_circuit, rule_circuit
from spad.hardware.area_model import AreaModel, feature_names, probe_photons, usage


class AreaFeatures(unittest.TestCase):
    def setUp(self):
        self.config = StreamConfig()
        self.names = feature_names(self.config)

    def features(self, circuit):
        inputs, codes = pack_circuit(circuit)
        return dict(zip(self.names, usage(self.config, inputs[None], codes[None], probe_photons())[0].tolist()))

    def test_rule_uses_only_its_flags(self):
        f = self.features(rule_circuit(self.config, window=8))
        self.assertEqual(f["flag_near8"], 1.)
        self.assertEqual(f["flag_near1"], 0.)
        self.assertEqual(f["flag_conf4"], 0.)
        self.assertEqual(f["state_flops"], 0.)       # the rule never reads its state bits

    def test_constant_actions_remove_logic(self):
        circuit = rule_circuit(self.config, window=8)
        quiet = {**circuit, "layers": [dict(x) for x in circuit["layers"]]}
        last = quiet["layers"][-1]
        last["truth_tables"] = [[0, 0, 0, 0]] * len(last["truth_tables"])
        f = self.features(quiet)
        self.assertEqual(f["live_gates"], 0.)
        self.assertEqual(f["any_distance_flag"], 0.)

    def test_population_matches_single_estimates(self):
        model = AreaModel()
        circuits = [rule_circuit(self.config, window=w) for w in (4, 8, 16)]
        packed = [pack_circuit(c) for c in circuits]
        together = model.estimate(self.config, torch.stack([p[0] for p in packed]), torch.stack([p[1] for p in packed]))
        for k, circuit in enumerate(circuits):
            self.assertAlmostEqual(float(together[k]), model.circuit_area(circuit), places=4)


if __name__ == "__main__":
    unittest.main()
