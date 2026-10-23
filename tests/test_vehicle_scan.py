import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import cv2
import numpy as np

from app import database
from app.models.schemas import TargetConfiguration
from app.models.schemas import VideoMetadata
from app.models.open_vocabulary import ModelProvenance
from app.services.vehicle_recognizer import VehicleObservation
from app.services.vehicle_scan import VehicleScanManager, _category_matches, _group_tracks, _requested_color, is_vehicle_profile_search


PROVENANCE = ModelProvenance(provider="test", model_name="vehicle", model_version="1")


def item(frame, timestamp, bbox, category="car"):
    return {"frame_idx": frame, "timestamp_seconds": timestamp, "vehicle": VehicleObservation(
        bbox=bbox, category=category, confidence=.9, color="red", color_confidence=.7,
        colors={"red": .7}, crop_path=None, mask_path=None, provenance=PROVENANCE,
    )}


class VehicleScanTests(unittest.TestCase):
    def test_vehicle_profile_without_plate_uses_dense_scan(self):
        self.assertTrue(is_vehicle_profile_search(TargetConfiguration(vehicle_color="red")))
        self.assertFalse(is_vehicle_profile_search(TargetConfiguration(plate_number="ABC123", vehicle_color="red")))

    def test_adjacent_overlapping_detections_form_one_track(self):
        tracks = _group_tracks([
            item(1, 1.0, [10, 10, 100, 80]), item(2, 2.0, [15, 10, 105, 80]),
            item(2, 2.0, [200, 10, 290, 80]),
        ])
        self.assertEqual(sorted(len(track) for track in tracks), [1, 2])

    def test_coarse_categories_do_not_claim_fine_body_style(self):
        self.assertTrue(_category_matches("SUV / Crossover", "car"))
        self.assertFalse(_category_matches("Motorcycle", "car"))
        self.assertTrue(_category_matches("Pickup truck", "truck"))

    def test_dealership_color_aliases_map_to_detector_palette(self):
        self.assertEqual(_requested_color("Silver"), "grey")
        self.assertEqual(_requested_color("Burgundy / Maroon"), "red")

    def test_dense_vehicle_scan_persists_observed_and_requested_fields_separately(self):
        with tempfile.TemporaryDirectory() as root:
            db_path = str(Path(root) / "test.db")
            with patch.object(database, "DB_DIR", root), patch.object(database, "DB_PATH", db_path):
                database.init_db()
                video_path = str(Path(root) / "vehicle.mp4")
                writer = cv2.VideoWriter(video_path, cv2.VideoWriter_fourcc(*"mp4v"), 10, (320, 180))
                for _ in range(20):
                    writer.write(np.zeros((180, 320, 3), np.uint8))
                writer.release()
                metadata = VideoMetadata(
                    filename="vehicle.mp4", filepath=video_path, duration_seconds=2,
                    frame_count=20, fps=10, width=320, height=180, codec="mp4v",
                    file_size_mb=.1, creation_timestamp="",
                )
                target = TargetConfiguration(
                    free_text_description="red Tesla vehicle", processing_mode="balanced",
                    vehicle_color="red", vehicle_make="Tesla", camera_role="lot_entry",
                )
                with database.get_db_connection() as conn:
                    conn.execute(
                        "INSERT INTO sessions(session_id,status,video_metadata,target_config,run_id) VALUES (?,?,?,?,?)",
                        ("case", "analyzing", metadata.model_dump_json(), target.model_dump_json(), "run"),
                    )
                    conn.execute("INSERT INTO analysis_runs(run_id,session_id,status) VALUES (?,?,?)",
                                 ("run", "case", "analyzing"))

                class FakeRecognizer:
                    calls = 0

                    def __init__(self, evidence_root):
                        pass

                    def recognize_all(self, **kwargs):
                        self.calls += 1
                        if self.calls <= 2:
                            return [VehicleObservation(
                                bbox=[20, 20, 250, 160], category="car", confidence=.9,
                                color="red", color_confidence=.7, colors={"red": .7, "black": .3},
                                crop_path=None, mask_path=None, provenance=PROVENANCE,
                                make_model_candidates=({
                                    "make": "Tesla", "model": "Model 3", "year_start": 2020,
                                    "year_end": 2023, "confidence": .8,
                                },),
                            )]
                        return []

                def fake_clip(source, start, end, destination):
                    Path(destination).write_bytes(b"clip")

                with patch("app.services.vehicle_scan.VehicleRecognizer", FakeRecognizer), \
                     patch("app.services.vehicle_scan._extract_clip", fake_clip):
                    results = VehicleScanManager.execute_analysis(
                        "case", target, run_id="run", checkpoint=lambda: None,
                    )
                self.assertEqual(len(results), 1)
                self.assertEqual(results[0].classification, "strong_match")
                with database.get_db_connection() as conn:
                    sighting = conn.execute("SELECT * FROM vehicle_sightings").fetchone()
                self.assertEqual(sighting["observed_plate"], "")
                self.assertEqual(sighting["vehicle_color"], "red")
                self.assertIsNone(sighting["vehicle_make"])
                self.assertEqual(sighting["requested_vehicle_make"], "Tesla")
                self.assertEqual(sighting["vehicle_attribute_state"], "candidate_consensus")
                attributes = __import__("json").loads(sighting["vehicle_attribute_candidates_json"])
                self.assertEqual(attributes["selected"]["model"], "Model 3")


if __name__ == "__main__":
    unittest.main()
