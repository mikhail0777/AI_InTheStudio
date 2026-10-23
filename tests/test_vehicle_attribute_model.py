import json
import tempfile
import unittest
from pathlib import Path

import cv2
import numpy as np
import torch

from app.services.vehicle_attribute_model import LocalVehicleAttributeProvider


class FixedModel(torch.nn.Module):
    def forward(self, values):
        return torch.tensor([[1.0, 3.0]], device=values.device).repeat(values.shape[0], 1)


class VehicleAttributeModelTests(unittest.TestCase):
    def test_local_model_returns_ranked_candidates_and_provenance(self):
        with tempfile.TemporaryDirectory() as root:
            root = Path(root)
            image = root / "vehicle.jpg"
            cv2.imwrite(str(image), np.full((100, 180, 3), 120, np.uint8))
            manifest = root / "labels.json"
            manifest.write_text(json.dumps({
                "input_size": 96,
                "dataset": {"name": "fixture", "commercial_use_cleared": False},
                "classes": [
                    {"make": "Honda", "model": "Civic", "year_start": 2020, "year_end": 2022},
                    {"make": "Kia", "model": "Forte", "year_start": 2021, "year_end": 2023},
                ],
            }), encoding="utf-8")
            provider = LocalVehicleAttributeProvider(
                root / "unused.pt", manifest, device="cpu", model=FixedModel(),
            )
            candidates = provider.predict(image, top_k=2)
            self.assertEqual(candidates[0]["make"], "Kia")
            self.assertGreater(candidates[0]["confidence"], candidates[1]["confidence"])
            self.assertEqual(candidates[0]["confidence_kind"], "model_softmax")
            self.assertFalse(provider.provenance.metadata["dataset"]["commercial_use_cleared"])

    def test_output_dimension_must_match_manifest(self):
        with tempfile.TemporaryDirectory() as root:
            root = Path(root)
            image = root / "vehicle.jpg"
            cv2.imwrite(str(image), np.zeros((80, 120, 3), np.uint8))
            manifest = root / "labels.json"
            manifest.write_text(json.dumps({"classes": [{"make": "Only", "model": "One"}]}), encoding="utf-8")
            provider = LocalVehicleAttributeProvider(root / "unused.pt", manifest, model=FixedModel())
            with self.assertRaises(RuntimeError):
                provider.predict(image)


if __name__ == "__main__":
    unittest.main()
