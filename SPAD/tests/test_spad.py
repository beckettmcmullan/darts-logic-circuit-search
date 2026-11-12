"""Scientific correctness checks; run with python -m unittest discover -s SPAD."""
import unittest

import numpy as np
import torch

from spad.hardware.costs import core_cost, extract_cells
from spad.core.model import Config, RecurrentLogic, light_gate, simulate_circuit
from spad.dataset.prepare import project_ranges
from spad.pilot.train import depth_loss


class LogicTests(unittest.TestCase):
    def setUp(self):
        torch.set_num_threads(1)
        torch.manual_seed(4)

    def test_every_boolean_truth_table(self):
        a, b = torch.tensor([0., 0., 1., 1.]), torch.tensor([0., 1., 0., 1.])
        for code in range(16):
            table = torch.tensor([(code >> bit) & 1 for bit in range(4)]).float()
            self.assertTrue(torch.equal(light_gate(a, b, table), table))

    def test_export_recurrence_and_reset(self):
        model = RecurrentLogic(Config(width=8, state_bits=4, score_bits=3,
                                      layers=3, bins=19, position_bits=5))
        # Nontrivial gates and routes, including register dependencies.
        for layer in model.layers:
            layer.table_logits.data.normal_()
            layer.routes.data.normal_()
        hist = torch.randint(0, 32, (3, 19))
        hard = model(hist, hard=True)
        self.assertTrue(torch.equal(hard.long(), simulate_circuit(model.circuit(), hist)))
        self.assertTrue(torch.equal(hard[:1], model(hist[:1], hard=True)))
        self.assertTrue(torch.equal(hard, model(hist, ste=True)))

    def test_bilevel_parameter_separation_and_gradients(self):
        model = RecurrentLogic(Config(width=8, state_bits=4, score_bits=3,
                                      bins=16, position_bits=4, truncation=4))
        weights, architecture = model.weight_parameters(), model.architecture_parameters()
        self.assertFalse({id(x) for x in weights} & {id(x) for x in architecture})
        before = [p.detach().clone() for p in weights]
        for p in weights:
            p.requires_grad_(False)
        optimizer = torch.optim.Adam(architecture, lr=0.1)
        loss = depth_loss(model(torch.randint(0, 5, (4, 16))), torch.tensor([2., 3.5, 7., 8.]))
        loss.backward()
        self.assertTrue(all(p.grad is not None and torch.isfinite(p.grad).all() for p in architecture))
        optimizer.step()
        self.assertTrue(all(torch.equal(p, q) for p,q in zip(before, weights)))

    def test_liberty_units_and_nested_tables(self):
        text = '''library(test) { time_unit : "1ns";
          cell (AND2x1) { area : 0.2
            pin(Y) { timing() { cell_rise(t) { index_1("999");
                values("0.01, 0.02", "0.03, 0.04"); }
              cell_fall(t) { values("0.05, 0.06"); } } } } }'''
        cells = extract_cells(text, "fixture")
        self.assertEqual(len(cells), 1)
        self.assertAlmostEqual(cells[0]["area"], 0.2)
        self.assertAlmostEqual(cells[0]["delay_ps"], 60.)

    def test_hardware_cost_gradients(self):
        model = RecurrentLogic(Config(width=8, state_bits=4, score_bits=3, bins=16, position_bits=4))
        costs = {"truth_table_costs": [{"area": float(i % 5), "delay_ps": float(i+1)} for i in range(16)],
                 "selected_cells": {"DFF": {"area": 2., "delay_ps": 1., "setup_ps": 0.5}}}
        area, delay = core_cost(model, costs)
        (area+delay).backward()
        self.assertTrue(all(p.grad is not None and torch.isfinite(p.grad).all() for p in model.parameters()))
        hard_area, _ = core_cost(model, costs, hard=True)
        circuit = model.circuit()
        expected = 4*2 + sum(costs["truth_table_costs"][sum(v << bit for bit,v in enumerate(table))]["area"]
                             for layer in circuit["layers"] for table in layer["truth_tables"])
        self.assertEqual(float(hard_area), expected)

    def test_projection_inverse_transform_nearest_range(self):
        transform = np.eye(4)
        transform[0, 3] = 1.
        # Two returns on one pixel; a behind-camera and a zero-invalid return.
        points = np.array([[1, 0, 3], [1, 0, 2], [1, 0, -2], [0, 0, 0]])
        depth = project_ranges(points, transform, dict(fx=1., fy=1., cx=1., cy=1.), 0., 0., 3, 3)
        self.assertEqual(depth[4], 2.)
        self.assertEqual(np.isfinite(depth).sum(), 1)


if __name__ == "__main__":
    unittest.main()
