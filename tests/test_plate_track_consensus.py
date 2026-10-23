import unittest

from app.services.plate_track_consensus import (
    adaptive_frame_budget, build_track_plate_consensus,
    plate_observation_score, select_plate_track_frames,
)


def observation(frame, timestamp, text="ABC123", quality=.8, confidence=.8, width=160, height=40):
    return {
        "frame_idx": frame,
        "timestamp_seconds": timestamp,
        "text": text,
        "confidence": confidence,
        "quality_score": quality,
        "quality_metrics": {"width": width, "height": height},
        "candidates": [{"text": text, "confidence": confidence}],
    }


class PlateTrackConsensusTests(unittest.TestCase):
    def test_budget_adapts_to_available_frames_and_track_duration(self):
        self.assertEqual(adaptive_frame_budget(2, .1), 2)
        self.assertEqual(adaptive_frame_budget(30, 1.0), 3)
        self.assertEqual(adaptive_frame_budget(30, 4.0), 9)
        self.assertEqual(adaptive_frame_budget(200, 30.0), 10)

    def test_selection_uses_one_detection_per_frame(self):
        weaker = observation(10, 1.0, quality=.2)
        stronger = observation(10, 1.0, quality=.9)
        selected = select_plate_track_frames([weaker, stronger])
        self.assertEqual(selected.distinct_input_frames, 1)
        self.assertEqual(selected.input_observations, 2)
        self.assertIs(selected.observations[0], stronger)

    def test_selection_is_not_influenced_by_expected_text(self):
        clear = observation(1, 0.0, text="WRONG1", quality=.95, confidence=.7)
        blurry = observation(2, .1, text="ABC123", quality=.1, confidence=.7)
        self.assertGreater(plate_observation_score(clear), plate_observation_score(blurry))
        selected = select_plate_track_frames([clear, blurry], minimum_frames=1, maximum_frames=1)
        self.assertEqual(selected.selected_frame_indices, (1,))
        self.assertFalse(selected.as_dict()["policy"]["expected_plate_text_used"])

    def test_long_burst_is_capped_and_spread_across_track(self):
        items = [observation(index, index / 30, quality=.7) for index in range(90)]
        selected = select_plate_track_frames(items, maximum_frames=8)
        self.assertEqual(len(selected.observations), 7)
        self.assertLess(min(selected.selected_frame_indices), 20)
        self.assertGreater(max(selected.selected_frame_indices), 70)

    def test_selected_independent_frames_feed_exact_consensus(self):
        items = [
            observation(1, 0.0, "ABC123", .9, .9),
            observation(2, .4, "ABC128", .3, .7),
            observation(3, .8, "ABC123", .85, .88),
        ]
        consensus, selection = build_track_plate_consensus(items)
        self.assertEqual(selection.selected_frame_indices, (1, 2, 3))
        self.assertEqual(consensus["selected_plate"], "ABC123")
        self.assertEqual(consensus["state"], "exact_consensus")
        self.assertEqual(consensus["frame_selection"]["selected_frames"], 3)


if __name__ == "__main__":
    unittest.main()
