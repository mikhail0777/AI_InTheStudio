import tempfile
import unittest
from pathlib import Path
from zipfile import ZipFile

from scripts.prepare_vmmr_training_manifest import prepare_manifest


class PrepareVmmrTrainingManifestTests(unittest.TestCase):
    def test_groups_years_into_make_model_ranges_and_never_creates_final_split(self):
        with tempfile.TemporaryDirectory() as root:
            archive = Path(root) / "sample.zip"
            with ZipFile(archive, "w") as output:
                for year in (2020, 2021):
                    for index in range(6):
                        output.writestr(f"kia_forte_{year}/{year}_{index}.jpg", b"image")
                for index in range(12):
                    output.writestr(f"honda_civic_2020/{index}.jpg", b"image")
            manifest = prepare_manifest(
                archive, minimum_images=10, maximum_images_per_class=10,
                development_fraction=.2, archive_sha256="abc",
            )
            self.assertEqual(manifest["counts"]["classes"], 2)
            forte = next(item for item in manifest["classes"] if item["model"] == "forte")
            self.assertEqual((forte["year_start"], forte["year_end"]), (2020, 2021))
            self.assertEqual({item["split"] for item in manifest["samples"]}, {"train", "development"})
            self.assertFalse(manifest["split_policy"]["contains_final_split"])
            self.assertFalse(manifest["dataset"]["commercial_use_cleared"])
            self.assertEqual(manifest["counts"]["samples"], 20)


if __name__ == "__main__":
    unittest.main()
