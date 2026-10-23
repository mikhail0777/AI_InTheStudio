import tempfile
import unittest
from pathlib import Path
from zipfile import ZipFile

from scripts.audit_vmmr_archive import audit_archive, parse_class_label


class AuditVmmrArchiveTests(unittest.TestCase):
    def test_parses_multiword_make_and_year(self):
        label = parse_class_label("land_rover_range_rover_2016")
        self.assertEqual(label["make"], "Land Rover")
        self.assertEqual(label["model"], "range rover")
        self.assertEqual(label["year_start"], 2016)

    def test_audit_counts_zip_without_extracting(self):
        with tempfile.TemporaryDirectory() as root:
            archive = Path(root) / "sample.zip"
            with ZipFile(archive, "w") as output:
                output.writestr("kia_forte_2015/a.jpg", b"a")
                output.writestr("kia_forte_2015/b.jpg", b"b")
                output.writestr("honda_civic_2014/a.jpg", b"c")
                output.writestr("README.txt", b"text")
            report = audit_archive(archive, include_sha256=True)
            self.assertEqual(report["inventory"]["images"], 3)
            self.assertEqual(report["inventory"]["classes"], 2)
            self.assertEqual(report["inventory"]["classes_with_fewer_than_2_images"], 1)
            self.assertEqual(len(report["archive"]["sha256"]), 64)
            self.assertFalse(report["source"]["commercial_use_cleared"])
            self.assertFalse(report["split_readiness"]["frozen"])


if __name__ == "__main__":
    unittest.main()
