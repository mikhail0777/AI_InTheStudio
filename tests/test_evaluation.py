import unittest

from pydantic import ValidationError

from app.models.open_vocabulary import EntityDetection, EntityTrack, ModelProvenance, SearchResult
from app.services.evaluation import GroundTruthEvent, LabeledBox, evaluate_results


PROVENANCE = ModelProvenance(provider="test", model_name="fixture", model_version="1", device="cpu")


def result(result_id, start, end, score, bbox, classification="strong_match"):
    detection = EntityDetection(
        detection_id=result_id + "-d", frame_idx=1, timestamp_seconds=(start + end) / 2,
        label="car", bbox=bbox, confidence=.9, provenance=PROVENANCE,
    )
    track = EntityTrack(
        track_id=result_id + "-t", label="car", start_seconds=start, end_seconds=end,
        detections=[detection],
    )
    return SearchResult(
        result_id=result_id, search_id="search", start_seconds=start, end_seconds=end,
        best_timestamp_seconds=(start + end) / 2, classification=classification,
        overall_score=score, entities=[track], explanation="fixture", model_provenance=[PROVENANCE],
    )


class EvaluationTests(unittest.TestCase):
    def test_reports_explicit_denominators_and_condition_slices(self):
        events = [
            GroundTruthEvent(
                event_id="near", start_seconds=0, end_seconds=2,
                required_labels=["car"],
                conditions=["low_light", "partial_occlusion", "high_angle", "small_object"],
                boxes=[LabeledBox(timestamp_seconds=1, label="car", bbox=[0, 0, 20, 20])],
            ),
            GroundTruthEvent(
                event_id="far", start_seconds=8, end_seconds=10,
                required_labels=["car"], conditions=["long_distance"],
            ),
        ]
        predictions = [
            result("true", 0, 2, .9, [1, 1, 21, 21]),
            result("false", 20, 22, .8, [0, 0, 20, 20]),
        ]
        report = evaluate_results(events, predictions, [1.0])
        self.assertEqual(report.counts.ground_truth_events, 2)
        self.assertEqual(report.counts.matched_events, 1)
        self.assertEqual(report.metrics.candidate_retrieval_recall, .5)
        self.assertEqual(report.metrics.event_recall, .5)
        self.assertEqual(report.metrics.promoted_false_positive_rate, .5)
        self.assertGreater(report.metrics.mean_box_iou, .8)
        self.assertEqual(report.metrics.condition_recall["low_light"], 1)
        self.assertEqual(report.metrics.condition_recall["long_distance"], 0)

    def test_unlabeled_or_unpromoted_metrics_are_not_invented(self):
        report = evaluate_results([], [], [])
        self.assertIsNone(report.metrics.event_recall)
        self.assertIsNone(report.metrics.promoted_false_positive_rate)
        self.assertIsNone(report.metrics.mean_box_iou)
        self.assertGreaterEqual(len(report.notes), 3)

    def test_unlikely_result_is_not_counted_as_a_promoted_false_positive(self):
        event = GroundTruthEvent(event_id="event", start_seconds=0, end_seconds=1)
        report = evaluate_results(
            [event], [result("negative", 10, 11, .9, [0, 0, 20, 20], "unlikely_match")], [],
        )
        self.assertEqual(report.counts.promoted_results, 0)
        self.assertIsNone(report.metrics.promoted_false_positive_rate)

    def test_required_labels_prevent_temporal_false_matches(self):
        event = GroundTruthEvent(
            event_id="person-event", start_seconds=0, end_seconds=2, required_labels=["person"],
        )
        report = evaluate_results([event], [result("car", 0, 2, .9, [0, 0, 20, 20])], [1])
        self.assertEqual(report.counts.matched_events, 0)
        self.assertEqual(report.counts.false_positive_results, 1)

    def test_rejects_invalid_label_geometry_and_intervals(self):
        with self.assertRaises(ValidationError):
            LabeledBox(timestamp_seconds=1, label="car", bbox=[10, 10, 5, 20])
        with self.assertRaises(ValidationError):
            LabeledBox(timestamp_seconds=1, label="car", bbox=[0, 0, float("inf"), 20])
        with self.assertRaises(ValidationError):
            GroundTruthEvent(event_id="bad", start_seconds=2, end_seconds=1)


if __name__ == "__main__":
    unittest.main()
