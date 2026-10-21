import unittest

from scripts.evaluate_plate_event_benchmark import evaluate, validate_manifest


def manifest():
    return {
        "dataset": {
            "name": "test", "version": "1", "licence": "internal-test",
            "source": "unit test", "sha256": "abc", "permitted_usage": "testing",
        },
        "events": [
            {"event_id": "day", "split": "final_test", "eligible": True,
             "plate": "ABC123", "duration_seconds": 5, "conditions": ["day"]},
            {"event_id": "night", "split": "final_test", "eligible": True,
             "plate": "XYZ900", "duration_seconds": 5, "conditions": ["night"]},
            {"event_id": "negative", "split": "final_test", "eligible": False,
             "plate": None, "duration_seconds": 3600, "conditions": ["negative_footage"]},
        ],
    }


class PlateEventBenchmarkTests(unittest.TestCase):
    def test_reports_denominators_errors_conditions_and_negative_rate(self):
        report = evaluate(manifest(), [
            {"event_id": "day", "candidates": ["ABC123"]},
            {"event_id": "night", "candidates": ["XYZ9OO", "XYZ900"]},
            {"event_id": "negative", "candidates": ["FALSE1"]},
        ])
        self.assertEqual(report["decision"], "fail")
        self.assertEqual(report["denominators"]["eligible_fully_transcribed_events"], 2)
        self.assertEqual(report["metrics"]["event_exact_full_plate_accuracy"], .5)
        self.assertEqual(report["metrics"]["top_5_exact_full_plate_accuracy"], 1)
        self.assertEqual(report["metrics"]["false_sightings_per_negative_video_hour"], 1)
        self.assertEqual(report["conditions"]["night"]["exact_full_plate_accuracy"], 0)
        self.assertEqual(report["ocr_confusions"]["0->O"], 2)

    def test_rejects_non_final_and_incompletely_documented_data(self):
        value = manifest()
        value["events"][0]["split"] = "train"
        with self.assertRaisesRegex(ValueError, "final_test"):
            validate_manifest(value)
        value = manifest()
        value["dataset"]["licence"] = ""
        with self.assertRaisesRegex(ValueError, "licence"):
            validate_manifest(value)

    def test_rejects_predictions_for_unknown_events(self):
        with self.assertRaisesRegex(ValueError, "unknown events"):
            evaluate(manifest(), [{"event_id": "invented", "candidates": []}])


if __name__ == "__main__":
    unittest.main()
