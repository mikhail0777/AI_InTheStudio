import unittest
from unittest.mock import patch

import numpy as np

from app.services.license_plate_reader import LicensePlateReader, PlateReading, normalize_plate, plate_edit_distance, plate_similarity


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

    def test_weak_read_triggers_mirror_recovery_and_restores_bbox(self):
        reader = LicensePlateReader.__new__(LicensePlateReader)
        frame = np.zeros((100, 300, 3), dtype=np.uint8)
        with patch.object(reader, "_read_region", side_effect=[
            [PlateReading("CPCJ000", .65, [20, 30, 80, 50])],
            [PlateReading("60LD4379", .99, [40, 30, 120, 50])],
        ]):
            readings = reader.read_frame(frame, tiled=False)
        recovered = next(item for item in readings if item.text == "60LD4379")
        self.assertEqual(recovered.bbox, [180, 30, 260, 50])
        self.assertEqual(recovered.source_variant, "horizontal_flip")

    def test_confident_normal_read_skips_mirror_recovery(self):
        reader = LicensePlateReader.__new__(LicensePlateReader)
        frame = np.zeros((100, 300, 3), dtype=np.uint8)
        with patch.object(reader, "_read_region", return_value=[
            PlateReading("ABC123", .95, [20, 30, 80, 50])
        ]) as read:
            readings = reader.read_frame(frame, tiled=False)
        self.assertEqual([item.text for item in readings], ["ABC123"])
        read.assert_called_once()

    def test_overlapping_tile_reads_are_deduplicated_even_when_ocr_differs(self):
        readings = LicensePlateReader._deduplicate([
            PlateReading("ABC123", .97, [100, 100, 200, 140]),
            PlateReading("A8C123", .83, [103, 101, 201, 141]),
            PlateReading("XYZ999", .90, [300, 100, 400, 140]),
        ])
        self.assertEqual([item.text for item in readings], ["ABC123", "XYZ999"])


if __name__ == "__main__":
    unittest.main()
