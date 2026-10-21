import hashlib
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import cv2
import numpy as np

from app import database
from app.models.schemas import SightingReviewInput
from app.services.vehicle_sightings import list_revisions, list_sightings, review_sighting
from app.services.video_service import VideoService
from app.services.analysis_worker import AnalysisWorker, queue_proxy


class ReliableInvestigationTests(unittest.TestCase):
    def test_h264_proxy_preserves_incompatible_original(self):
        with tempfile.TemporaryDirectory() as root:
            source = Path(root) / "source.mov"
            writer = cv2.VideoWriter(str(source), cv2.VideoWriter_fourcc(*"mp4v"), 10, (160, 90))
            for frame in range(10):
                image = np.full((90, 160, 3), frame * 15, np.uint8)
                writer.write(image)
            writer.release()
            before = hashlib.sha256(source.read_bytes()).hexdigest()
            metadata = VideoService.inspect_video(str(source))
            self.assertFalse(VideoService.is_browser_compatible(str(source), metadata.codec))
            proxy = Path(root) / "playback_h264.mp4"
            VideoService.create_browser_proxy(str(source), str(proxy))
            proxy_metadata = VideoService.inspect_video(str(proxy))
            self.assertTrue(VideoService.is_browser_compatible(str(proxy), proxy_metadata.codec))
            self.assertEqual(hashlib.sha256(source.read_bytes()).hexdigest(), before)

    def test_review_revisions_preserve_original_ocr_and_survive_new_connection(self):
        with tempfile.TemporaryDirectory() as root:
            db_path = str(Path(root) / "test.db")
            with patch.object(database, "DB_DIR", root), patch.object(database, "DB_PATH", db_path):
                database.init_db()
                with database.get_db_connection() as conn:
                    conn.execute("INSERT INTO sessions(session_id,status,playback_url) VALUES (?,?,?)",
                                 ("case", "completed", "/uploads/case/playback_h264.mp4"))
                    conn.execute("INSERT INTO searches(search_id,session_id,status,query_json) VALUES (?,?,?,?)",
                                 ("search", "case", "completed", "{}"))
                    conn.execute(
                        """INSERT INTO vehicle_sightings(
                           sighting_id,session_id,search_id,requested_plate,observed_plate,
                           plate_match_mode,match_kind,ocr_confidence,similarity,first_seen_seconds,
                           last_seen_seconds,best_timestamp_seconds,camera_role,event_type)
                           VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                        ("s1", "case", "search", "ABC123", "ABC12B", "exact",
                         "review_candidate", .8, .8, 1, 2, 1.5, "unknown", "observed"),
                    )
                corrected = review_sighting("s1", SightingReviewInput(
                    action="correct", corrected_plate="ABC123",
                    reason="Verified against the enlarged source frame",
                ))
                self.assertEqual(corrected["observed_plate"], "ABC12B")
                self.assertEqual(corrected["corrected_plate"], "ABC123")
                self.assertEqual(corrected["review_status"], "needs_research")
                confirmed = review_sighting("s1", SightingReviewInput(action="confirm"))
                self.assertEqual(confirmed["review_status"], "confirmed")
                review_sighting("s1", SightingReviewInput(action="reopen"))
                review_sighting("s1", SightingReviewInput(action="note", note="Second operator review required."))
                rows = list_sightings(plate="ABC12B")
                self.assertEqual(rows[0]["observed_plate"], "ABC12B")
                self.assertEqual(rows[0]["corrected_plate"], "ABC123")
                self.assertEqual(rows[0]["source_video_url"], "/uploads/case/playback_h264.mp4")
                self.assertEqual(len(list_revisions("s1")), 4)

    def test_proxy_job_is_durable_and_recovers_after_restart(self):
        with tempfile.TemporaryDirectory() as root:
            db_path = str(Path(root) / "test.db")
            source = Path(root) / "source.mov"
            destination = Path(root) / "uploads" / "case" / "playback_h264.mp4"
            destination.parent.mkdir(parents=True)
            writer = cv2.VideoWriter(str(source), cv2.VideoWriter_fourcc(*"mp4v"), 10, (160, 90))
            for _ in range(5): writer.write(np.zeros((90, 160, 3), np.uint8))
            writer.release()
            with patch.object(database, "DB_DIR", root), patch.object(database, "DB_PATH", db_path):
                database.init_db()
                with database.get_db_connection() as conn:
                    conn.execute("INSERT INTO sessions(session_id,status) VALUES (?,?)", ("case", "uploaded"))
                queue_proxy("case", str(source), str(destination))
                with database.get_db_connection() as conn:
                    conn.execute("UPDATE proxy_jobs SET status='processing' WHERE session_id='case'")
                AnalysisWorker.recover_interrupted()
                with database.get_db_connection() as conn:
                    self.assertEqual(conn.execute("SELECT status FROM proxy_jobs WHERE session_id='case'").fetchone()[0], "queued")
                self.assertTrue(AnalysisWorker().run_proxy_once())
                with database.get_db_connection() as conn:
                    session = conn.execute("SELECT playback_url,proxy_status FROM sessions WHERE session_id='case'").fetchone()
                self.assertEqual(session["proxy_status"], "ready")
                self.assertEqual(session["playback_url"], "/uploads/case/playback_h264.mp4")


if __name__ == "__main__":
    unittest.main()
