import unittest

from scripts.freeze_commons_vehicle_benchmark import conservative_capture_group, freeze


def sample(sample_id, class_id, role="supported", artist="A", date="2025-01-01 10:00"):
    return {
        "sample_id": sample_id, "class_id": class_id, "role": role,
        "crop_path": f"/{sample_id}.jpg",
        "source": {"artist": artist, "date_time_original": date, "title": f"File:{sample_id}.jpg"},
    }


class FreezeCommonsVehicleBenchmarkTests(unittest.TestCase):
    def test_groups_same_author_day_and_keeps_unknown_out_of_classes(self):
        values = [
            sample("a", 0), sample("b", 0, date="2025-01-01 11:00"),
            sample("c", 0, artist="B", date="2025-02-02"),
            sample("u1", 1, role="unknown", artist="C"),
            sample("u2", 1, role="unknown", artist="D"),
        ]
        intake = {
            "classes": [
                {"class_id": 0, "make": "Known", "model": "One", "year_start": 2020, "year_end": 2026},
                {"class_id": 1, "make": "Unknown", "model": "One", "year_start": 2020, "year_end": 2026, "role": "unknown"},
            ],
            "samples": values,
        }
        review = {"samples": {item["sample_id"]: {"accepted": True, "notes": ""} for item in values}}
        result = freeze(intake, review, "seed")
        self.assertEqual(len(result["classes"]), 1)
        known = [item for item in result["samples"] if item["class_id"] is not None]
        self.assertEqual(known[0]["split"], known[1]["split"])
        self.assertTrue(all(item["split"].startswith("unknown_") for item in result["samples"] if item["class_id"] is None))

    def test_refuses_incomplete_review(self):
        intake = {"classes": [], "samples": [sample("a", 0)]}
        with self.assertRaisesRegex(ValueError, "requires review"):
            freeze(intake, {"samples": {}}, "seed")


if __name__ == "__main__":
    unittest.main()
