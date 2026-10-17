import unittest

from app.services.license_plate_reader import normalize_plate, plate_edit_distance, plate_similarity


class PlateMatchingTests(unittest.TestCase):
    def test_normalization_removes_formatting_without_rewriting_characters(self):
        self.assertEqual(normalize_plate("ab-c 123"), "ABC123")

    def test_exact_plate_is_the_only_perfect_similarity(self):
        self.assertEqual(plate_similarity("DBYC-622", "DBYC622"), 1.0)
        self.assertLess(plate_similarity("DBYC62Z", "DBYC622"), 1.0)

    def test_common_ocr_confusion_is_reviewable_but_not_exact(self):
        score = plate_similarity("ABC12O", "ABC120")
        self.assertGreaterEqual(score, .90)
        self.assertLess(score, 1.0)

    def test_unrelated_plate_stays_below_review_threshold(self):
        self.assertLess(plate_similarity("ZZZZ999", "ABCD123"), .78)

    def test_edit_distance_handles_insertions(self):
        self.assertEqual(plate_edit_distance("ABC123", "ABC0123"), 1)


if __name__ == "__main__":
    unittest.main()
