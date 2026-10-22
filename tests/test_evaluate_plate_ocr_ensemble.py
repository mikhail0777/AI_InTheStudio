import unittest

from scripts.evaluate_plate_ocr_ensemble import canonical_file, evaluate


class PlateOCREnsembleTests(unittest.TestCase):
    def test_region_length_rule_is_explicit_and_reproducible(self):
        yolo = [{"file": "plate.jpg", "expected": "ABC1234", "observed": "ABBC1234"}]
        parseq = [{"file": "primary__plate.jpg", "expected": "ABC1234", "observed": "ABC1234", "confidence": .95}]
        result = evaluate(yolo, parseq, plate_length=7, threshold=.925)
        self.assertEqual(result["exact_matches"], 1)
        self.assertEqual(result["overrides"], 1)
        self.assertEqual(result["rows"][0]["source"], "parseq_length_ranked_alternative")

    def test_low_confidence_alternative_does_not_override(self):
        yolo = [{"file": "plate.jpg", "expected": "ABC1234", "observed": "ABBC1234"}]
        parseq = [{"file": "plate.jpg", "expected": "ABC1234", "observed": "ABC1234", "confidence": .90}]
        result = evaluate(yolo, parseq, plate_length=7, threshold=.925)
        self.assertEqual(result["exact_matches"], 0)
        self.assertEqual(result["overrides"], 0)

    def test_canonical_file_only_removes_known_source_prefix(self):
        self.assertEqual(canonical_file("primary__x.jpg"), "x.jpg")
        self.assertEqual(canonical_file("my_primary__x.jpg"), "my_primary__x.jpg")


if __name__ == "__main__":
    unittest.main()
