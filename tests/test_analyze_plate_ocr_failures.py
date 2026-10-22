import tempfile
import unittest
from pathlib import Path

import cv2
import numpy as np

from scripts.analyze_plate_ocr_failures import analyze, edit_breakdown


class PlateOCRFailureAnalysisTests(unittest.TestCase):
    def test_edit_breakdown_counts_substitution_insertion_and_deletion(self):
        kinds, substitutions = edit_breakdown("ABC123", "A8C1234")
        self.assertEqual(kinds["substitution"], 1)
        self.assertEqual(kinds["extra_character"], 1)
        self.assertEqual(substitutions[("B", "8")], 1)

    def test_analysis_keeps_predictions_and_marks_diagnostic_quality_only(self):
        with tempfile.TemporaryDirectory() as root:
            image_dir = Path(root)
            cv2.imwrite(str(image_dir / "dark.jpg"), np.zeros((30, 100), np.uint8))
            report = {"model": "test", "split": "valid", "rows": [
                {"file": "ok.jpg", "expected": "ABC123", "observed": "ABC123"},
                {"file": "dark.jpg", "expected": "ABC123", "observed": "A8C123"},
            ]}
            result = analyze(report, image_dir)
        self.assertEqual(result["exact_plate_accuracy"], .5)
        self.assertEqual(result["top_substitutions"][0], {"expected": "B", "observed": "8", "count": 1})
        self.assertCountEqual(
            result["failures"][0]["image_quality"]["diagnostic_tags"],
            ["small_crop", "low_sharpness", "dark", "low_contrast"],
        )


if __name__ == "__main__":
    unittest.main()
