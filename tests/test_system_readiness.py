import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from app import database
from app.services import system_readiness


class SystemReadinessTests(unittest.TestCase):
    def test_readiness_separates_runtime_health_from_release_certification(self):
        with tempfile.TemporaryDirectory() as root, patch.object(database, "DB_DIR", root), patch.object(
            database, "DB_PATH", str(Path(root) / "lottrace.db")
        ):
            database.init_db()
            result = system_readiness.runtime_readiness()

        self.assertEqual(result["runtime_status"], "healthy")
        self.assertFalse(result["production_certified"])
        self.assertTrue(result["capabilities"]["recorded_video_upload"])
        self.assertTrue(result["capabilities"]["desktop_application_shell"])
        self.assertTrue(result["capabilities"]["live_camera_ingestion"])
        self.assertFalse(result["capabilities"]["automatic_track_to_crossing_event"])
        self.assertGreaterEqual(len(result["release_blockers"]), 3)
        self.assertIn("not model accuracy", result["accuracy_note"])

    def test_database_failure_degrades_health_without_hiding_capabilities(self):
        with patch.object(system_readiness, "_database_health", return_value={"ok": False, "error": "offline"}), patch.object(
            system_readiness, "_storage_health", return_value={"ok": True}
        ):
            result = system_readiness.runtime_readiness()
        self.assertEqual(result["runtime_status"], "degraded")
        self.assertFalse(result["production_certified"])

    def test_api_responses_include_desktop_security_headers(self):
        from fastapi.testclient import TestClient
        from app.main import app

        response = TestClient(app, base_url="http://localhost").get("/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers["x-content-type-options"], "nosniff")
        self.assertEqual(response.headers["x-frame-options"], "DENY")
        self.assertIn("default-src 'self'", response.headers["content-security-policy"])


if __name__ == "__main__":
    unittest.main()
