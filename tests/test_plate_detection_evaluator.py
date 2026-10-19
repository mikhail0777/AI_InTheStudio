import unittest

from scripts.evaluate_plate_detection_dataset import intersection_over_union, match_boxes


class PlateDetectionEvaluatorTests(unittest.TestCase):
    def test_intersection_over_union(self):
        self.assertEqual(intersection_over_union([0, 0, 10, 10], [0, 0, 10, 10]), 1.0)
        self.assertEqual(intersection_over_union([0, 0, 10, 10], [20, 20, 30, 30]), 0.0)
        self.assertAlmostEqual(intersection_over_union([0, 0, 10, 10], [5, 0, 15, 10]), 1 / 3)

    def test_matching_is_one_to_one_and_thresholded(self):
        ground_truth = [[0, 0, 10, 10], [20, 20, 30, 30]]
        predictions = [[0, 0, 10, 10], [1, 1, 9, 9], [21, 21, 31, 31]]
        matches = match_boxes(ground_truth, predictions, 0.5)
        self.assertEqual(len(matches), 2)
        self.assertEqual({match[0] for match in matches}, {0, 1})
        self.assertEqual(len({match[1] for match in matches}), 2)


if __name__ == "__main__":
    unittest.main()
