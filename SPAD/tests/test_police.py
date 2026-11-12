"""Randomized photon conditions, the training-only physics police, and scene pairing."""
import io
import unittest
import zipfile

import torch

from spad.dataset.photons import sample_conditions
from spad.dataset.scenes import view_pairs
from spad.training.police import Police, measure_pulse


def synthetic(rays=400, tau=300, photons=128, signal=.5, seed=0):
    """Histograms holding one known return over flat background."""
    g = torch.Generator().manual_seed(seed)
    pulse = torch.tensor([.05, .2, .3, .2, .12, .08, .05])
    hist = torch.full((rays, 672), 2.)
    hist[:, tau - 2:tau + 5] += pulse * 672 * 2 * signal / (1 - signal)
    sampled = torch.multinomial(hist / hist.sum(1, keepdim=True), photons, replacement=True, generator=g)
    return hist.round().int(), sampled


class ConditionTests(unittest.TestCase):
    def test_counts_background_and_padding(self):
        hist = torch.zeros(4000, 672, dtype=torch.int32)
        hist[:, 100] = 1000
        photons, counts, background = sample_conditions(hist, 16, 256, .6, torch.Generator().manual_seed(1))
        self.assertTrue(((counts >= 16) & (counts <= 256)).all())
        self.assertTrue(((background >= 0) & (background <= .6)).all())
        self.assertTrue(torch.equal((photons >= 0).sum(1), counts))
        # Log-uniform counts: about as many rays below 64 as above.
        self.assertAlmostEqual(float((counts < 64).float().mean()), .5, delta=.05)
        # Off-peak photons appear at about the requested ambient rate.
        off = ((photons >= 0) & (photons != 100)).sum(1).float() / counts
        expected = background * 671 / 672
        self.assertLess(float((off - expected).abs().mean()), .05)

    def test_no_background_keeps_photons_on_the_return(self):
        hist = torch.zeros(10, 672, dtype=torch.int32)
        hist[:, 50] = 9
        photons, _, _ = sample_conditions(hist, 8, 8, 0., torch.Generator().manual_seed(2))
        self.assertEqual(set(photons.unique().tolist()), {50})


class PoliceTests(unittest.TestCase):
    def setUp(self):
        self.hist, self.photons = synthetic()
        pulse, zero = measure_pulse(self.hist)
        self.police = Police(pulse, zero)
        self.evidence = self.police.evidence(self.photons)

    def test_measured_pulse_peaks_where_it_was_made(self):
        pulse, zero = measure_pulse(self.hist)
        self.assertAlmostEqual(float(pulse.sum()), 1., places=5)
        self.assertEqual(int(pulse.argmax()), zero)

    def test_finds_the_return_without_labels(self):
        self.assertTrue(self.evidence["any_detection"].all())
        self.assertLess(float((self.evidence["tau_ml"] - 300).abs().median()), 1.5)

    def test_true_answer_passes_and_wrong_answers_fail(self):
        truth = torch.full((len(self.photons),), 300.)
        flags = lambda answer: float(self.police.violations(answer, self.evidence, offset=0.)["physics"].float().mean())
        self.assertLess(flags(truth), .05)
        self.assertLess(flags(truth + 2), .1)               # inside the 3-bin tolerance
        self.assertGreater(flags(truth + 12), .9)
        self.assertGreater(flags(torch.full_like(truth, 50.)), .9)

    def test_label_free_offset_absorbs_a_constant_delay(self):
        delayed = torch.full((len(self.photons),), 300. + 7)
        self.assertLess(float(self.police.violations(delayed, self.evidence)["physics"].float().mean()), .05)

    def test_population_shapes_and_penalty_gradient(self):
        answers = torch.stack([torch.full((len(self.photons),), 300.), torch.full((len(self.photons),), 40.)])
        flags = self.police.violations(answers, self.evidence, offset=torch.zeros(2, 1))["physics"]
        self.assertEqual(tuple(flags.shape), (2, len(self.photons)))
        self.assertLess(float(flags[0].float().mean()), float(flags[1].float().mean()))
        answer = torch.full((len(self.photons),), 330., requires_grad=True)
        penalty = self.police.penalty(answer, {**self.evidence, "tau_ml": self.evidence["tau_ml"] * 0 + 330})
        penalty.backward()
        self.assertTrue(torch.isfinite(answer.grad).all())

    def test_pure_background_reports_no_return(self):
        flat = torch.full((200, 672), 5, dtype=torch.int32)
        photons = torch.multinomial(flat.float(), 64, replacement=True, generator=torch.Generator().manual_seed(3))
        self.assertLess(float(self.police.evidence(photons)["any_detection"].float().mean()), .1)


class ScenePairingTests(unittest.TestCase):
    def test_pose_file_pairs_maps_with_clouds_even_with_an_extra_cloud(self):
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w") as z:
            z.writestr("s/sp_pose_results.csv", "sp_seq,sp_file,livox_csv_name\n"
                       "0,RawDataHistogramMap_frame_0_20.txt,2.csv\n1,RawDataHistogramMap_frame_0_10.txt,1.csv\n")
            for name in ("RawDataHistogramMap_frame_0_10.txt", "RawDataHistogramMap_frame_0_20.txt",
                         "1.csv", "2.csv", "3.csv"):
                z.writestr(f"s/{name}", "")
        with zipfile.ZipFile(buffer) as z:
            self.assertEqual(view_pairs(z, "s"), [(1, "s/RawDataHistogramMap_frame_0_10.txt", "s/1.csv"),
                                                  (2, "s/RawDataHistogramMap_frame_0_20.txt", "s/2.csv")])


if __name__ == "__main__":
    unittest.main()
