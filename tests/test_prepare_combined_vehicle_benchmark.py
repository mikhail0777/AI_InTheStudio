import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from scripts.prepare_combined_vehicle_benchmark import combine_manifests


class CombinedVehicleBenchmarkTests(unittest.TestCase):
    def test_preserves_splits_and_remaps_modern_class(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            images = root / "images"
            images.mkdir()
            (images / "old.jpg").write_bytes(b"x")
            base = {
                "purpose": "frozen_research_benchmark",
                "dataset": {"name": "old"},
                "archive": {"path": "old.zip"},
                "classes": [{"class_id": 0, "make": "A", "model": "B", "year_start": 2000, "year_end": 2002}],
                "samples": [{"member": "old.jpg", "class_id": 0, "split": "test"}],
            }
            modern = {
                "purpose": "frozen_research_benchmark",
                "dataset": {"name": "new"},
                "archive": {"path": "new.zip"},
                "classes": [{"class_id": 0, "make": "C", "model": "D", "year_start": 2016, "year_end": 2018}],
                "samples": [{"path": str(root / "new.jpg"), "class_id": 0, "split": "train"}],
            }
            old_path, new_path = root / "old.json", root / "new.json"
            old_path.write_text(json.dumps(base)); new_path.write_text(json.dumps(modern))
            result = combine_manifests(old_path, images, new_path)
            self.assertEqual(len(result["classes"]), 2)
            self.assertEqual(result["samples"][0]["split"], "test")
            self.assertEqual(result["samples"][1]["class_id"], 1)
            self.assertEqual(result["counts"], {"train": 1, "development": 0, "test": 1})


if __name__ == "__main__":
    unittest.main()
