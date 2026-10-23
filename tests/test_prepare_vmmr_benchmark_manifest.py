import tempfile
import unittest
from pathlib import Path
from zipfile import ZipFile

from scripts.prepare_vmmr_benchmark_manifest import prepare_benchmark_manifest


class PrepareVmmrBenchmarkManifestTests(unittest.TestCase):
    def test_freezes_three_disjoint_splits_with_year_ranges(self):
        with tempfile.TemporaryDirectory() as root:
            archive = Path(root) / "sample.zip"
            with ZipFile(archive, "w") as output:
                for make, model, year in (("kia", "forte", 2020), ("honda", "civic", 2021)):
                    for index in range(80):
                        output.writestr(f"{make}_{model}_{year}/{index:03d}.jpg", b"image")
            manifest = prepare_benchmark_manifest(
                archive, archive_sha256="abc", minimum_images=45,
                maximum_classes=2, maximum_images_per_class=70,
            )
            self.assertEqual(manifest["purpose"], "frozen_research_benchmark")
            self.assertEqual(set(item["split"] for item in manifest["samples"]), {"train", "development", "test"})
            self.assertTrue(manifest["split_policy"]["test_is_frozen_before_training"])
            self.assertFalse(manifest["dataset"]["commercial_use_cleared"])
            self.assertEqual(manifest["classes"][0]["year_end"] - manifest["classes"][0]["year_start"], 2)


if __name__ == "__main__":
    unittest.main()
