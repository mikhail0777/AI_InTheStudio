import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import cv2
import numpy as np

from app import database
from app.models.open_vocabulary import ModelProvenance
from app.models.schemas import TargetConfiguration, VideoMetadata
from app.services.license_plate_reader import PlateReading
from app.services.vehicle_recognizer import VehicleObservation
from app.services.vehicle_investigation import VehicleInvestigationManager, _group_sightings, is_plate_investigation
from app.services.query_parser import StructuredQueryParser
from app.services.vehicle_sightings import after_hours


class VehicleInvestigationTests(unittest.TestCase):
    def test_after_hours_uses_configured_business_window(self):
        self.assertEqual(after_hours("2026-10-16T07:30:00", "08:00", "20:00"), 1)
        self.assertEqual(after_hours("2026-10-16T12:30:00", "08:00", "20:00"), 0)
        self.assertIsNone(after_hours(None, "08:00", "20:00"))

    def test_plate_query_routes_to_dense_investigation(self):
        query = StructuredQueryParser().parse("red vehicle with licence plate ABCD123")
        self.assertTrue(is_plate_investigation(query))

    def test_color_only_query_does_not_route_to_plate_scan(self):
        query = StructuredQueryParser().parse("red car")
        self.assertFalse(is_plate_investigation(query))

    def test_sightings_split_on_large_time_gap(self):
        observations = [
            {"timestamp_seconds": 1.0}, {"timestamp_seconds": 3.0},
            {"timestamp_seconds": 12.0}, {"timestamp_seconds": 13.0},
        ]
        groups = _group_sightings(observations, maximum_gap_seconds=6.0)
        self.assertEqual([len(group) for group in groups], [2, 2])

    def test_dense_scan_requires_repeat_or_high_confidence_for_strong_result(self):
        with tempfile.TemporaryDirectory() as root:
            db_path = str(Path(root) / "test.db")
            with patch.object(database, "DB_DIR", root), patch.object(database, "DB_PATH", db_path):
                database.init_db()
                video_path = str(Path(root) / "plate.mp4")
                writer = cv2.VideoWriter(video_path, cv2.VideoWriter_fourcc(*"mp4v"), 10, (320, 180))
                for _ in range(20):
                    writer.write(np.zeros((180, 320, 3), np.uint8))
                writer.release()
                metadata = VideoMetadata(
                    filename="plate.mp4", filepath=video_path, duration_seconds=2,
                    frame_count=20, fps=10, width=320, height=180, codec="mp4v",
                    file_size_mb=.1, creation_timestamp="",
                )
                target = TargetConfiguration(
                    free_text_description="vehicle with licence plate ABC123",
                    processing_mode="balanced",
                    plate_number="ABC123",
                    camera_name="Service lane 1",
                    camera_role="service_entry",
                    recorded_start_at="2026-10-16T08:30:00",
                    business_open_time="08:00",
                    business_close_time="20:00",
                    vehicle_make="Tesla",
                    vehicle_model="Model 3",
                )
                with database.get_db_connection() as conn:
                    conn.execute(
                        "INSERT INTO sessions(session_id,status,video_metadata,target_config,run_id) VALUES (?,?,?,?,?)",
                        ("case", "analyzing", metadata.model_dump_json(), target.model_dump_json(), "run"),
                    )
                    conn.execute(
                        "INSERT INTO analysis_runs(run_id,session_id,status) VALUES (?,?,?)",
                        ("run", "case", "analyzing"),
                    )

                class FakeReader:
                    provenance = ModelProvenance(provider="test", model_name="plate", model_version="1")
                    calls = 0

                    def read_frame(self, frame, tiled=True):
                        self.calls += 1
                        if self.calls in (1, 2):
                            return [PlateReading("ABC123", .6, [10, 20, 90, 45])]
                        return []

                class FakeVehicleRecognizer:
                    def __init__(self, evidence_root):
                        pass

                    def recognize(self, **kwargs):
                        return VehicleObservation(
                            bbox=[5, 5, 200, 160], category="car", confidence=.92,
                            color="red", color_confidence=.68,
                            colors={"red": .68, "black": .2, "grey": .12},
                            crop_path="/evidence/case/car.jpg",
                            mask_path="/evidence/case/car_mask.png",
                            provenance=ModelProvenance(
                                provider="test", model_name="vehicle", model_version="1"
                            ),
                        )

                def fake_clip(source, start, end, destination):
                    Path(destination).write_bytes(b"test")

                with patch("app.services.vehicle_investigation.LicensePlateReader", FakeReader), \
                     patch("app.services.vehicle_investigation.VehicleRecognizer", FakeVehicleRecognizer), \
                     patch("app.services.vehicle_investigation._extract_clip", fake_clip):
                    results = VehicleInvestigationManager.execute_analysis(
                        "case", target, run_id="run", checkpoint=lambda: None,
                    )
                self.assertEqual(len(results), 1)
                self.assertEqual(results[0].classification, "strong_match")
                self.assertIn("2 distinct", results[0].explanation)
                with database.get_db_connection() as conn:
                    sighting = conn.execute("SELECT * FROM vehicle_sightings").fetchone()
                self.assertEqual(sighting["observed_plate"], "ABC123")
                self.assertEqual(sighting["event_type"], "entered_service")
                self.assertEqual(sighting["camera_name"], "Service lane 1")
                self.assertIsNone(sighting["vehicle_make"])
                self.assertEqual(sighting["requested_vehicle_make"], "Tesla")
                self.assertEqual(sighting["vehicle_color"], "red")
                self.assertEqual(sighting["vehicle_body_type"], "car")
                self.assertEqual(sighting["vehicle_detection_confidence"], .92)
                self.assertEqual(sighting["after_hours"], 0)
                self.assertTrue(sighting["captured_at"].startswith("2026-10-16T08:30:"))

    def test_three_character_partial_plate_is_preserved(self):
        query = StructuredQueryParser().parse("vehicle with licence plate B12")
        constraint = next(attribute for entity in query.entities for attribute in entity.attributes
                          if attribute.name == "license_plate")
        self.assertEqual(constraint.value, "B12")


if __name__ == "__main__":
    unittest.main()
