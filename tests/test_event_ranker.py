import unittest

from app.models.open_vocabulary import EntityDetection, ModelProvenance
from app.services.event_ranker import build_event_results
from app.services.query_parser import StructuredQueryParser


PROVENANCE = ModelProvenance(provider="test", model_name="test", model_version="1")


def detections(label, boxes, colors=None):
    return [EntityDetection(
        detection_id=f"{label}-{index}", frame_id=f"f{index}", frame_idx=index,
        timestamp_seconds=float(index), label=label, bbox=box, confidence=.9,
        visibility=.8, attributes={"semantic_similarity": .4, "colors": colors or {}}, provenance=PROVENANCE,
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

    def test_quantity_requires_distinct_tracks(self):
        query = StructuredQueryParser().parse("two people near a car")
        person_a = detections("person", [[0, 0, 20, 40], [2, 0, 22, 40]])
        car = detections("car", [[20, 0, 70, 40], [22, 0, 72, 40]])
        self.assertEqual(build_event_results(query, "search", 10, [person_a, car]), [])
        person_b = detections("person", [[5, 0, 25, 40], [7, 0, 27, 40]])
        results = build_event_results(query, "search", 10, [person_a, person_b, car])
        self.assertEqual(len(results[0].entities), 3)
        self.assertEqual(results[0].classification, "strong_match")

    def test_single_observation_quantity_is_only_possible(self):
        query = StructuredQueryParser().parse("two people")
        first = detections("person", [[0, 0, 20, 40]])
        second = detections("person", [[30, 0, 50, 40]])
        results = build_event_results(query, "search", 10, [first, second])
        self.assertEqual(results[0].classification, "possible_match")

    def test_secondary_entity_color_is_required(self):
        query = StructuredQueryParser().parse("person near a blue car")
        person = detections("person", [[0, 0, 20, 40], [2, 0, 22, 40]])
        blue_car = detections("car", [[20, 0, 70, 40], [22, 0, 72, 40]], {"blue": .35})
        red_car = detections("car", [[20, 0, 70, 40], [22, 0, 72, 40]], {"red": .35})
        self.assertEqual(build_event_results(query, "search", 10, [person, blue_car])[0].classification,
                         "strong_match")
        self.assertEqual(build_event_results(query, "search", 10, [person, red_car])[0].classification,
                         "unlikely_match")

    def test_excluded_associated_entity_blocks_match(self):
        query = StructuredQueryParser().parse("a car without a dog")
        car = detections("car", [[0, 0, 60, 40], [10, 0, 70, 40]])
        dog = detections("dog", [[5, 10, 25, 35], [15, 10, 35, 35]])
        self.assertEqual(build_event_results(query, "search", 10, [car])[0].classification, "strong_match")
        self.assertEqual(build_event_results(query, "search", 10, [car, dog])[0].classification,
                         "unlikely_match")


if __name__ == "__main__":
    unittest.main()
