import unittest

from app.models.open_vocabulary import EntityDetection, ModelProvenance
from app.services.event_ranker import build_event_results
from app.services.query_parser import StructuredQueryParser


PROVENANCE = ModelProvenance(provider="test", model_name="test", model_version="1")


def detections(label, boxes):
    return [EntityDetection(
        detection_id=f"{label}-{index}", frame_id=f"f{index}", frame_idx=index,
        timestamp_seconds=float(index), label=label, bbox=box, confidence=.9,
        visibility=.8, attributes={"semantic_similarity": .4}, provenance=PROVENANCE,
    ) for index, box in enumerate(boxes)]


class EventRankerTests(unittest.TestCase):
    def setUp(self):
        self.query = StructuredQueryParser().parse("a person pushing a stroller")

    def test_co_moving_person_and_stroller_form_one_strong_event(self):
        person = detections("person", [[0, 0, 20, 40], [10, 0, 30, 40], [20, 0, 40, 40]])
        stroller = detections("stroller", [[15, 15, 45, 40], [25, 15, 55, 40], [35, 15, 65, 40]])
        results = build_event_results(self.query, "search", 10, [person, stroller])
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].classification, "strong_match")
        self.assertEqual({track.label for track in results[0].entities}, {"person", "stroller"})
        self.assertEqual(results[0].evidence[-1].assessment, "supported")

    def test_unrelated_person_and_stroller_are_not_promoted(self):
        person = detections("person", [[0, 0, 20, 40], [10, 0, 30, 40], [20, 0, 40, 40]])
        stroller = detections("stroller", [[200, 0, 240, 40], [210, 0, 250, 40], [220, 0, 260, 40]])
        results = build_event_results(self.query, "search", 10, [person, stroller])
        self.assertEqual(results[0].classification, "unlikely_match")

    def test_missing_required_entity_yields_no_event(self):
        person = detections("person", [[0, 0, 20, 40], [10, 0, 30, 40]])
        self.assertEqual(build_event_results(self.query, "search", 10, [person]), [])

    def test_fragmented_stroller_tracks_do_not_duplicate_one_actor_event(self):
        person = detections("person", [[0, 0, 20, 40], [10, 0, 30, 40], [20, 0, 40, 40]])
        stroller_a = detections("stroller", [[15, 15, 45, 40], [25, 15, 55, 40], [35, 15, 65, 40]])
        stroller_b = detections("stroller", [[16, 15, 46, 40], [26, 15, 56, 40], [36, 15, 66, 40]])
        results = build_event_results(self.query, "search", 10, [person, stroller_a, stroller_b])
        self.assertEqual(len(results), 1)


if __name__ == "__main__":
    unittest.main()
