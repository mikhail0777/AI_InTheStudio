import unittest

import numpy as np

from app.services.visual_features import color_distribution, color_match_score


class VisualRobustnessTests(unittest.TestCase):
    def test_red_color_survives_bright_and_dim_visible_lighting(self):
        mask = np.full((20, 20), 255, dtype=np.uint8)
        for value in (90, 160, 255):
            image = np.zeros((20, 20, 3), dtype=np.uint8)
            image[:, :] = (0, 0, value)
            distribution = color_distribution(image, mask)
            support, raw = color_match_score("red", distribution)
            self.assertGreaterEqual(raw, .95)
            self.assertGreaterEqual(support, .95)

    def test_tiny_or_heavily_occluded_color_region_stays_unsupported(self):
        image = np.zeros((20, 20, 3), dtype=np.uint8)
        image[:, :] = (0, 0, 255)
        tiny_mask = np.zeros((20, 20), dtype=np.uint8)
        tiny_mask[:5, :5] = 255
        self.assertEqual(color_distribution(image, tiny_mask), {})

    def test_partial_but_sufficient_mask_can_supply_color_evidence(self):
        image = np.zeros((20, 20, 3), dtype=np.uint8)
        image[:, :] = (0, 0, 200)
        partial = np.zeros((20, 20), dtype=np.uint8)
        partial[:10, :10] = 255
        self.assertGreater(color_distribution(image, partial)["red"], .95)


if __name__ == "__main__":
    unittest.main()
