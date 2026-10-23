import unittest

import torch

from scripts.evaluate_vmmr_vehicle_classifier import calculate_metrics


class EvaluateVmmrVehicleClassifierTests(unittest.TestCase):
    def test_reports_exact_make_model_year_and_macro_f1_separately(self):
        classes = [
            {"make": "Honda", "model": "civic", "year_start": 2019, "year_end": 2021},
            {"make": "Honda", "model": "civic", "year_start": 2022, "year_end": 2024},
            {"make": "Kia", "model": "forte", "year_start": 2019, "year_end": 2021},
        ]
        logits = torch.tensor([[5., 1., 0.], [3., 4., 0.], [0., 3., 4.]])
        metrics = calculate_metrics(logits, torch.tensor([0, 0, 2]), classes)
        self.assertEqual(metrics["samples"], 3)
        self.assertEqual(metrics["exact_make_model_year_range_top1_count"], 2)
        self.assertAlmostEqual(metrics["make_top1"], 1.0)
        self.assertAlmostEqual(metrics["make_model_top1"], 1.0)
        self.assertAlmostEqual(metrics["year_range_top1"], 2 / 3)
        self.assertFalse(metrics["year_range_discrimination_measured"])
        self.assertEqual(metrics["year_range_distinct_label_count"], 1)
        self.assertLess(metrics["macro_f1_exact_class"], 1.0)

    def test_does_not_claim_year_discrimination_with_one_truth_range(self):
        classes = [
            {"make": "Honda", "model": "civic", "year_start": 2016, "year_end": 2018},
            {"make": "Kia", "model": "forte", "year_start": 2016, "year_end": 2018},
        ]
        metrics = calculate_metrics(torch.tensor([[2., 1.], [1., 2.]]), torch.tensor([0, 1]), classes)
        self.assertFalse(metrics["year_range_discrimination_measured"])
        self.assertEqual(metrics["year_range_distinct_label_count"], 1)
        self.assertAlmostEqual(metrics["macro_f1_exact_class"], 1.0)


if __name__ == "__main__":
    unittest.main()
