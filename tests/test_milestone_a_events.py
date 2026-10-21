import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app import database
from app.services import governance, vehicle_events, vehicle_records
from fastapi.testclient import TestClient


class MilestoneAEventTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.patch_dir = patch.object(database, "DB_DIR", self.temp.name)
        self.patch_path = patch.object(database, "DB_PATH", str(Path(self.temp.name) / "test.db"))
        self.patch_dir.start(); self.patch_path.start()
        self.addCleanup(self.patch_dir.stop); self.addCleanup(self.patch_path.stop)
        database.init_db()
        _, self.user = governance.bootstrap(
            "Northside Motors", "admin@example.com", "Admin User", "correct horse battery staple"
        )
        self.camera = vehicle_records.create_camera(self.user, {
            "name": "Main gate", "role": "lot_entry", "timezone": "America/Toronto"
        })
        self.boundary = vehicle_events.create_boundary(self.user, self.camera["camera_id"], {
            "name": "Main entrance", "boundary_type": "entrance",
            "x1": .2, "y1": .5, "x2": .8, "y2": .5,
            "travel_direction": "negative_to_positive",
            "min_vehicle_width": .1, "min_vehicle_height": .1, "min_visible_fraction": .7,
        })

    def payload(self, **changes):
        value = {
            "boundary_id": self.boundary["boundary_id"], "track_id": "track-17",
            "recorded_start_at": "2026-10-21T08:17:00-04:00", "recording_reference": "recording-1.mp4",
            "consensus_plate": "CVTV 604", "plate_match_state": "exact_consensus",
            "observations": [
                {"timestamp_seconds": 3, "center_x": .5, "center_y": .35, "width": .3, "height": .25,
                 "visible_fraction": .9, "frame_reference": "frame-30.jpg"},
                {"timestamp_seconds": 5, "center_x": .5, "center_y": .65, "width": .32, "height": .26,
                 "visible_fraction": .95, "frame_reference": "frame-50.jpg"},
            ],
            "ocr_candidates": [{"frame": "frame-30.jpg", "candidates": ["CVTV604", "CVTVG04"]}],
            "model_manifest": {"vehicle_tracker": {"name": "test-tracker", "version": "1"}},
            "evidence": {"source_sha256": "abc123"},
        }
        value.update(changes)
        return value

    def test_crossing_creates_one_immutable_arrival_and_status_transition(self):
        vehicle = vehicle_records.save_vehicle(self.user, {
            "plate": "CVTV604", "make": "Kia", "model": "Forte", "status": "off_lot"
        })
        result = vehicle_events.create_crossing_event(self.user, self.payload())
        self.assertTrue(result["created"])
        event = result["event"]
        self.assertEqual(event["event_type"], "arrival")
        self.assertEqual(event["timezone"], "America/Toronto")
        self.assertEqual(event["matched_vehicle_id"], vehicle["vehicle_id"])
        self.assertEqual(event["review_state"], "confirmed")
        detail = vehicle_events.get_event(self.user, event["event_id"])
        self.assertEqual(len(detail["observations"]), 2)
        self.assertEqual(detail["status_transition"]["previous_status"], "off_lot")
        self.assertEqual(detail["status_transition"]["new_status"], "on_lot")
        self.assertEqual(vehicle_records.get_vehicle(self.user, vehicle["vehicle_id"])["status"], "on_lot")
        with database.get_db_connection() as conn:
            with self.assertRaises(sqlite3.IntegrityError):
                conn.execute("UPDATE vehicle_events SET review_state='requires_review' WHERE event_id=?", (event["event_id"],))

    def test_retry_is_idempotent_and_cannot_repeat_transition(self):
        vehicle = vehicle_records.save_vehicle(self.user, {"plate": "CVTV604", "status": "off_lot"})
        first = vehicle_events.create_crossing_event(self.user, self.payload())
        second = vehicle_events.create_crossing_event(self.user, self.payload())
        self.assertTrue(first["created"])
        self.assertFalse(second["created"])
        self.assertEqual(second["reason"], "duplicate")
        self.assertEqual(first["event"]["event_id"], second["event"]["event_id"])
        with database.get_db_connection() as conn:
            self.assertEqual(conn.execute("SELECT count(*) FROM vehicle_events").fetchone()[0], 1)
            self.assertEqual(conn.execute("SELECT count(*) FROM vehicle_status_transitions WHERE vehicle_id=?", (vehicle["vehicle_id"],)).fetchone()[0], 1)

    def test_wrong_direction_and_ineligible_tracks_do_not_create_events(self):
        points = self.payload()["observations"]
        reverse = self.payload(observations=[
            {**points[1], "timestamp_seconds": 3}, {**points[0], "timestamp_seconds": 5}
        ])
        self.assertEqual(vehicle_events.create_crossing_event(self.user, reverse)["reason"], "no_eligible_directed_crossing")
        tiny = self.payload(track_id="tiny", observations=[
            {**item, "width": .02, "height": .02} for item in self.payload()["observations"]
        ])
        self.assertEqual(vehicle_events.create_crossing_event(self.user, tiny)["reason"], "no_eligible_directed_crossing")

    def test_uncertain_or_conflicting_inventory_state_routes_to_review(self):
        vehicle = vehicle_records.save_vehicle(self.user, {"plate": "CVTV604", "status": "on_lot"})
        conflict = vehicle_events.create_crossing_event(self.user, self.payload())
        self.assertEqual(conflict["event"]["review_state"], "requires_review")
        self.assertEqual(conflict["event"]["review_reason"], "conflicting_inventory_state")
        self.assertEqual(vehicle_records.get_vehicle(self.user, vehicle["vehicle_id"])["status"], "on_lot")
        uncertain = vehicle_events.create_crossing_event(self.user, self.payload(
            track_id="track-18", plate_match_state="conflicting", consensus_plate="CVTV604"
        ))
        self.assertEqual(uncertain["event"]["review_reason"], "ocr_candidates_conflict")
        self.assertIsNone(uncertain["event"]["matched_vehicle_id"])

    def test_crossing_outside_finite_gate_segment_is_rejected(self):
        outside = self.payload(track_id="outside", observations=[
            {**self.payload()["observations"][0], "center_x": .95},
            {**self.payload()["observations"][1], "center_x": .95},
        ])
        self.assertEqual(vehicle_events.create_crossing_event(self.user, outside)["reason"], "no_eligible_directed_crossing")

    def test_authenticated_event_api_exposes_configuration_and_ledger(self):
        from app.main import app
        vehicle_records.save_vehicle(self.user, {"plate": "CVTV604", "status": "off_lot"})
        client = TestClient(app, base_url="http://localhost")
        self.addCleanup(client.close)
        login = client.post("/api/auth/login", json={
            "email": "admin@example.com", "password": "correct horse battery staple"
        })
        self.assertEqual(login.status_code, 200, login.text)
        boundaries = client.get("/api/camera-boundaries")
        self.assertEqual(boundaries.status_code, 200, boundaries.text)
        self.assertEqual(boundaries.json()[0]["boundary_id"], self.boundary["boundary_id"])
        created = client.post("/api/vehicle-events/from-track", json=self.payload(track_id="api-track"))
        self.assertEqual(created.status_code, 200, created.text)
        event_id = created.json()["event"]["event_id"]
        ledger = client.get("/api/vehicle-events")
        self.assertEqual(ledger.status_code, 200, ledger.text)
        self.assertEqual(ledger.json()[0]["event_id"], event_id)
        detail = client.get(f"/api/vehicle-events/{event_id}")
        self.assertEqual(detail.status_code, 200, detail.text)
        self.assertEqual(len(detail.json()["observations"]), 2)
        self.assertFalse(governance.permitted("reviewer", "POST", "/api/vehicle-events/from-track"))


if __name__ == "__main__":
    unittest.main()
