import unittest

from scripts.calibrate_plate_ocr_review import calibrate, row_confidence


class PlateOCRReviewCalibrationTests(unittest.TestCase):
    def test_yolo_sequence_uses_weakest_selected_character(self):
        row = {"predictions": [
            {"confidence": .9}, {"confidence": .7}, {"confidence": .4},
        ]}
        self.assertEqual(row_confidence(row, .5), .7)

    def test_policy_is_rejected_when_wilson_lower_bound_misses_target(self):
        report = {"rows": [
            {"expected": "ABC123", "observed": "ABC123", "confidence": .99},
            {"expected": "ABC124", "observed": "ABC12A", "confidence": .99},
        ]}
        result = calibrate(report, [.9], target_precision=.99, minimum_accepts=1)
        self.assertFalse(result["release_gate_met"])
        self.assertIsNone(result["selected_policy"])
        self.assertEqual(result["tradeoff"][0]["incorrect_auto_accepts"], 1)


if __name__ == "__main__":
    unittest.main()
