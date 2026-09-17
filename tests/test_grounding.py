import tempfile
import unittest
from pathlib import Path

import cv2
import numpy as np
import torch

from app.services.generic_detector import CandidateFrame
from app.services.grounding import Owlv2GroundingProvider


class FakeProcessor:
    def __call__(self, **kwargs):
        self.phrases = kwargs["text"][0]
        return {"pixel_values": torch.zeros((1, 3, 8, 8)), "input_ids": torch.ones((1, 2), dtype=torch.long)}

    def post_process_grounded_object_detection(self, predictions, target_sizes, threshold):
        return [{
            "boxes": torch.tensor([[10.0, 8.0, 60.0, 55.0]]),
            "scores": torch.tensor([.82]),
            "labels": torch.tensor([0]),
            "text_labels": [self.phrases[0]],
        }]


class DuplicateProcessor(FakeProcessor):
    def post_process_grounded_object_detection(self, predictions, target_sizes, threshold):
        return [{
            "boxes": torch.tensor([[10.0, 8.0, 60.0, 55.0], [12.0, 9.0, 59.0, 54.0]]),
            "scores": torch.tensor([.82, .7]),
            "labels": torch.tensor([0, 0]),
            "text_labels": [self.phrases[0], self.phrases[0]],
        }]


class FakeModel:
    def __call__(self, **kwargs):
        return object()


class GroundingTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.image = self.root / "frame.jpg"
        pixels = np.zeros((64, 96, 3), dtype=np.uint8)
        pixels[8:55, 10:60] = (0, 255, 255)
        cv2.imwrite(str(self.image), pixels)
        self.provider = Owlv2GroundingProvider(
            str(self.root / "evidence"), processor=FakeProcessor(), model=FakeModel(), device="cpu",
        )
        self.frame = CandidateFrame("f1", 1, 1.0, str(self.image), .4)

    def test_phrase_grounding_produces_auditable_box_evidence(self):
        detections = self.provider.ground([self.frame], ["stroller"], "session")
        self.assertEqual(len(detections), 1)
        self.assertEqual(detections[0].label, "stroller")
        self.assertEqual(detections[0].attributes["localization_kind"], "bounding_box")
        self.assertGreater(detections[0].attributes["colors"]["yellow"], .8)
        self.assertTrue((self.root / "evidence" / "session" / Path(detections[0].crop_path).name).is_file())
        self.assertEqual(detections[0].provenance.metadata["task"], "open-vocabulary-grounding")

    def test_session_path_traversal_is_rejected(self):
        with self.assertRaises(ValueError):
            self.provider.ground([self.frame], ["stroller"], "../outside")

    def test_overlapping_phrase_boxes_are_suppressed(self):
        provider = Owlv2GroundingProvider(
            str(self.root / "nms"), processor=DuplicateProcessor(), model=FakeModel(), device="cpu",
        )
        self.assertEqual(len(provider.ground([self.frame], ["stroller"], "session")), 1)


if __name__ == "__main__":
    unittest.main()
