import unittest

from app.models.open_vocabulary import EntityDetection, ModelProvenance
from app.services.vehicle_recognizer import VehicleRecognizer, _contains_plate, _dominant_color


PROVENANCE = ModelProvenance(provider="test", model_name="vehicle", model_version="1")


class FakeProvider:
    def detect(self, frames, vocabulary, session_id, min_confidence=.25):
        return [EntityDetection(
            detection_id="car-1", frame_idx=12, timestamp_seconds=1.2,
            label="car", bbox=[10, 10, 210, 150], confidence=.91, visibility=.8,
            crop_path="/evidence/case/car.jpg", mask_path="/evidence/case/car.png",
            attributes={
                "colors": {"red": .72, "black": .18, "grey": .10},
                "vehicle_make_model_candidates": [
                    {"make": "Tesla", "model": "Model 3", "year_start": 2020,
                     "year_end": 2023, "confidence": .71},
                ],
            },
            provenance=PROVENANCE,
        )]


class VehicleRecognizerTests(unittest.TestCase):
    def test_plate_centre_must_belong_to_vehicle(self):
        self.assertTrue(_contains_plate([10, 10, 210, 150], [80, 100, 140, 125]))
        self.assertFalse(_contains_plate([10, 10, 210, 150], [260, 100, 320, 125]))

    def test_ambiguous_color_is_not_claimed(self):
        self.assertEqual(_dominant_color({"grey": .24, "black": .23}), (None, .24))

    def test_recognizes_vehicle_and_mask_based_color(self):
        observation = VehicleRecognizer("unused", provider=FakeProvider()).recognize(
            image_path="frame.jpg", plate_bbox=[80, 100, 140, 125],
            session_id="case", frame_idx=12, timestamp_seconds=1.2,
        )
        self.assertIsNotNone(observation)
        self.assertEqual(observation.category, "car")
        self.assertEqual(observation.color, "red")
        self.assertEqual(observation.bbox, [10, 10, 210, 150])
        self.assertEqual(observation.make_model_candidates[0]["model"], "Model 3")

    def test_recognize_all_returns_unassociated_vehicles(self):
        observations = VehicleRecognizer("unused", provider=FakeProvider()).recognize_all(
            image_path="frame.jpg", session_id="case", frame_idx=12, timestamp_seconds=1.2,
        )
        self.assertEqual([(item.category, item.color) for item in observations], [("car", "red")])

    def test_unassociated_plate_does_not_inherit_vehicle_attributes(self):
        observation = VehicleRecognizer("unused", provider=FakeProvider()).recognize(
            image_path="frame.jpg", plate_bbox=[260, 100, 320, 125],
            session_id="case", frame_idx=12, timestamp_seconds=1.2,
        )
        self.assertIsNone(observation)


if __name__ == "__main__":
    unittest.main()
