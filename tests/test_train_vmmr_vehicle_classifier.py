from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

import torch
from torchvision import models

from scripts.train_vmmr_vehicle_classifier import initialize_from_export


class TrainVmmrVehicleClassifierTests(unittest.TestCase):
    def test_expands_export_and_preserves_leading_classifier_rows(self):
        with TemporaryDirectory() as directory:
            source = models.efficientnet_b0(weights=None)
            source.classifier[-1] = torch.nn.Linear(source.classifier[-1].in_features, 2)
            with torch.no_grad():
                source.classifier[-1].weight.fill_(0.25)
                source.classifier[-1].bias.fill_(0.5)
            export = torch.export.export(source.eval(), (torch.zeros(1, 3, 224, 224),))
            path = Path(directory) / "source.pt2"
            torch.export.save(export, str(path))
            target = models.efficientnet_b0(weights=None)
            target.classifier[-1] = torch.nn.Linear(target.classifier[-1].in_features, 3)
            count = initialize_from_export(target, path)
            self.assertEqual(count, 2)
            self.assertTrue(torch.all(target.classifier[-1].weight[:2] == 0.25))
            self.assertTrue(torch.all(target.classifier[-1].bias[:2] == 0.5))


if __name__ == "__main__":
    unittest.main()
