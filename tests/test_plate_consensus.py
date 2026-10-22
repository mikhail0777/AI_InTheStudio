import tempfile
import unittest
from pathlib import Path

import cv2
import numpy as np

from app.services.plate_consensus import build_plate_consensus, rank_plate_candidates
from app.services.plate_evidence import enhance_plate_crop, quality_metrics, rectify_plate_crop, save_plate_derivatives


class PlateConsensusTests(unittest.TestCase):
    def test_independent_exact_frames_create_consensus(self):
        result = build_plate_consensus([
            {"frame_idx": 10, "quality_score": .8, "candidates": [
                {"text": "CVTV 604", "confidence": .82},
                {"text": "CVTVG04", "confidence": .51},
            ]},
            {"frame_idx": 20, "quality_score": .9, "candidates": [
                {"text": "CVTV604", "confidence": .79},
            ]},
        ])
        self.assertEqual(result["selected_plate"], "CVTV604")
        self.assertEqual(result["state"], "exact_consensus")
        self.assertFalse(result["requires_review"])
        self.assertEqual(result["ranked_candidates"][0]["distinct_frames"], 2)

    def test_enhancement_variants_in_one_frame_do_not_fake_temporal_support(self):
        result = build_plate_consensus([{
            "frame_idx": 10, "quality_score": 1,
            "candidates": [
                {"text": "ABC123", "confidence": .9, "source_variant": "original"},
                {"text": "ABC123", "confidence": .95, "source_variant": "enhanced_crop"},
            ],
        }])
        self.assertEqual(result["state"], "uncertain")
        self.assertEqual(result["ranked_candidates"][0]["distinct_frames"], 1)
        self.assertEqual(result["ranked_candidates"][0]["observation_count"], 2)

    def test_duplicate_detections_in_one_frame_contribute_only_one_weighted_vote(self):
        ranked = rank_plate_candidates([
            {"frame_idx": 10, "quality_score": 1, "text": "ABC123", "confidence": .7},
            {"frame_idx": 10, "quality_score": 1, "text": "ABC123", "confidence": .9},
        ])
        self.assertEqual(ranked[0].distinct_frames, 1)
        self.assertAlmostEqual(ranked[0].weighted_support, .9)

    def test_close_competing_candidates_require_review_without_rewriting(self):
        result = build_plate_consensus([
            {"frame_idx": 1, "quality_score": .8, "text": "ABC12O", "confidence": .8},
            {"frame_idx": 2, "quality_score": .8, "text": "ABC120", "confidence": .8},
        ])
        self.assertEqual(result["state"], "conflicting")
        self.assertCountEqual(
            [item["text"] for item in result["ranked_candidates"]], ["ABC12O", "ABC120"]
        )
        self.assertTrue(result["confusable_alternatives"])
        self.assertTrue(result["requires_review"])
        self.assertTrue(result["near_match_groups"][0]["review_only"])

    def test_repeated_low_confidence_text_is_not_auto_confirmed(self):
        result = build_plate_consensus([
            {"frame_idx": 1, "quality_score": 1, "text": "ABC123", "confidence": .2},
            {"frame_idx": 2, "quality_score": 1, "text": "ABC123", "confidence": .2},
        ])
        self.assertEqual(result["selected_plate"], "ABC123")
        self.assertEqual(result["state"], "uncertain")
        self.assertEqual(result["reason"], "repeated_reading_has_insufficient_ocr_support")
        self.assertTrue(result["requires_review"])

    def test_candidate_ranking_rejects_invalid_top_k(self):
        with self.assertRaises(ValueError):
            rank_plate_candidates([], top_k=0)


class PlateEvidenceTests(unittest.TestCase):
    def test_guarded_perspective_correction_rectifies_plate_quadrilateral(self):
        crop = np.zeros((90, 240, 3), np.uint8)
        polygon = np.array([[25, 24], [215, 12], [205, 68], [35, 78]], np.int32)
        cv2.polylines(crop, [polygon], True, (255, 255, 255), 3)
        rectified, applied = rectify_plate_crop(crop)
        self.assertTrue(applied)
        self.assertGreater(rectified.shape[1], rectified.shape[0] * 2)

    def test_enhancement_is_a_separate_image_and_derivatives_are_lossless(self):
        frame = np.full((100, 240, 3), 110, np.uint8)
        cv2.putText(frame, "ABC123", (45, 60), cv2.FONT_HERSHEY_SIMPLEX, 1, (240, 240, 240), 2)
        crop = frame[20:80, 30:210]
        original = crop.copy()
        enhanced = enhance_plate_crop(crop)
        np.testing.assert_array_equal(crop, original)
        self.assertGreaterEqual(enhanced.shape[1], crop.shape[1])
        metrics = quality_metrics(crop)
        self.assertTrue(0 <= metrics["quality_score"] <= 1)
        with tempfile.TemporaryDirectory() as root:
            saved = save_plate_derivatives(frame, [30, 20, 210, 80], Path(root), "plate_1")
            raw = cv2.imread(saved["raw_path"])
            self.assertIsNotNone(raw)
            np.testing.assert_array_equal(raw, crop)
            self.assertNotEqual(saved["raw_path"], saved["enhanced_path"])


if __name__ == "__main__":
    unittest.main()
