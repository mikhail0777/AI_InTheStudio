import unittest

from app.services.vehicle_attribute_consensus import build_vehicle_attribute_consensus


def frame(index, candidates, quality=.8):
    return {"frame_idx": index, "quality_score": quality, "candidates": candidates}


class VehicleAttributeConsensusTests(unittest.TestCase):
    def test_no_candidates_returns_unknown(self):
        result = build_vehicle_attribute_consensus([frame(1, [])])
        self.assertEqual(result["state"], "unknown")
        self.assertIsNone(result["selected"])

    def test_independent_frames_create_ranked_candidate_consensus(self):
        result = build_vehicle_attribute_consensus([
            frame(1, [{"make": "Kia", "model": "Forte", "year_start": 2021,
                       "year_end": 2023, "confidence": .82}]),
            frame(5, [{"make": "Kia", "model": "Forte", "year_start": 2022,
                       "year_end": 2024, "confidence": .76}]),
        ])
        self.assertEqual(result["state"], "candidate_consensus")
        self.assertEqual(result["selected"]["make"], "Kia")
        self.assertEqual(result["selected"]["year_start"], 2021)
        self.assertEqual(result["selected"]["year_end"], 2024)

    def test_variants_from_one_frame_do_not_create_temporal_support(self):
        result = build_vehicle_attribute_consensus([
            frame(1, [
                {"make": "Audi", "model": "Q5", "confidence": .8},
                {"make": "Audi", "model": "Q5", "confidence": .9},
            ])
        ])
        self.assertEqual(result["state"], "unknown")
        self.assertEqual(result["ranked_candidates"][0]["distinct_frames"], 1)

    def test_close_competing_models_require_review(self):
        result = build_vehicle_attribute_consensus([
            frame(1, [{"make": "Honda", "model": "Civic", "confidence": .8}]),
            frame(2, [{"make": "Toyota", "model": "Corolla", "confidence": .8}]),
        ])
        self.assertEqual(result["state"], "conflicting")
        self.assertTrue(result["requires_review"])


if __name__ == "__main__":
    unittest.main()
