import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import cv2
import numpy as np
import torch

from app.services.generic_detector import CandidateFrame, YoloDetectionProvider


class FakeBox:
    def __init__(self):
        self.cls = np.array([2])
        self.conf = np.array([.9])
        self.xyxy = torch.tensor([[10, 10, 50, 50]])


class FakeResult:
    boxes = [FakeBox()]
    masks = None


class FakeModel:
    names = {0: "person", 2: "car", 7: "truck"}
    task = "segment"

    def predict(self, images, **kwargs):
        return [FakeResult() for _ in images]


class GenericDetectorTests(unittest.TestCase):
    def test_localizes_requested_class_and_extracts_masked_color(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            model_path = root / "model.pt"
            model_path.write_bytes(b"test")
            image_path = root / "frame.jpg"
            image = np.zeros((64, 64, 3), dtype=np.uint8)
            image[10:50, 10:50] = (0, 255, 255)
            cv2.imwrite(str(image_path), image)
            with patch.object(YoloDetectionProvider, "_load"):
                provider = YoloDetectionProvider(str(root / "evidence"), model_path)
            provider.model = FakeModel()
            provider.names = FakeModel.names
            provider.class_ids = {value: key for key, value in provider.names.items()}
            provider.weight_hash = "test"
            detections = provider.detect([
                CandidateFrame("frame_1", 1, .5, str(image_path), .7)
            ], ["car"], "session")
            self.assertEqual(len(detections), 1)
            self.assertEqual(detections[0].label, "car")
            self.assertGreater(detections[0].attributes["colors"]["yellow"], .9)
            self.assertTrue((root / "evidence" / "session").is_dir())

    def test_unknown_vocabulary_is_not_mapped_to_a_coco_class(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            model_path = root / "model.pt"
            model_path.write_bytes(b"test")
            with patch.object(YoloDetectionProvider, "_load"):
                provider = YoloDetectionProvider(str(root / "evidence"), model_path)
            provider.names = FakeModel.names
            provider.class_ids = {value: key for key, value in provider.names.items()}
            self.assertEqual(provider.supported_labels(["stroller"]), [])


if __name__ == "__main__":
    unittest.main()
