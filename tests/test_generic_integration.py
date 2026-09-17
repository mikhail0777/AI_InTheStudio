"""API and persistence coverage for the generic search result path."""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app import database
from app.api import endpoints
from app.models.open_vocabulary import SearchResult
from app.services import agentic_loop
from app.services.query_parser import StructuredQueryParser


class GenericIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        root = self.temp.name
        for module, name, value in (
            (database, "DB_DIR", root),
            (database, "DB_PATH", str(Path(root) / "test.db")),
            (agentic_loop, "DATA_DIR", root),
            (endpoints, "DATA_DIR", root),
        ):
            patcher = patch.object(module, name, value)
            patcher.start()
            self.addCleanup(patcher.stop)
        database.init_db()
        app = FastAPI()
        app.include_router(endpoints.router)
        self.client = TestClient(app)
        self.addCleanup(self.client.close)

    def test_results_feedback_status_and_escaped_report(self):
        session_id, search_id = "generic-session", "generic-search"
        query = StructuredQueryParser().parse("yellow car <script>alert(1)</script>")
        result = SearchResult(
            result_id="result-1", search_id=search_id, start_seconds=1,
            end_seconds=3, best_timestamp_seconds=2,
            classification="possible_match", overall_score=.72,
            explanation="Possible yellow car <unsafe>",
            best_frame_path="/evidence/generic-session/frame.jpg",
            clip_path="/evidence/generic-session/clip.mp4",
        )
        with database.get_db_connection() as conn:
            conn.execute(
                "INSERT INTO sessions(session_id,status,search_id,search_query,video_metadata) VALUES (?,?,?,?,?)",
                (session_id, "completed", search_id, query.model_dump_json(),
                 '{"filename":"flight.mp4"}'),
            )
            conn.execute(
                "INSERT INTO searches(search_id,session_id,status,processing_mode,query_json,metrics_json) VALUES (?,?,?,?,?,?)",
                (search_id, session_id, "completed", "balanced", query.model_dump_json(),
                 '{"stage_timings":{"indexing":0.25,"total":1.5}}'),
            )
            conn.execute(
                "INSERT INTO search_results(search_id,result_id,start_seconds,end_seconds,classification,overall_score,payload) VALUES (?,?,?,?,?,?,?)",
                (search_id, result.result_id, 1, 3, result.classification,
                 result.overall_score, result.model_dump_json()),
            )

        base = f"/api/sessions/{session_id}"
        status = self.client.get(base + "/status")
        self.assertEqual(status.status_code, 200, status.text)
        self.assertEqual(status.json()["results_count"], 1)
        self.assertEqual(status.json()["processing_mode"], "balanced")
        self.assertEqual(status.json()["stage_timings"]["total"], 1.5)
        self.assertEqual(status.json()["search_query"]["entities"][0]["entity_type"], "car")
        results = self.client.get(base + "/results")
        self.assertEqual(results.status_code, 200, results.text)
        self.assertEqual(results.json()[0]["classification"], "possible_match")
        feedback = self.client.post(
            base + "/results/result-1/feedback",
            json={"status": "confirmed", "notes": "Reviewed in original footage"},
        )
        self.assertEqual(feedback.status_code, 200, feedback.text)
        self.assertEqual(feedback.json()["human_feedback"], "confirmed")
        report = self.client.get(base + "/report")
        self.assertEqual(report.status_code, 200, report.text)
        self.assertNotIn("<script>", report.text)
        self.assertIn("&lt;script&gt;", report.text)
        self.assertIn("/evidence/generic-session/clip.mp4", report.text)
        self.assertIn("Balanced", report.text)
        self.assertIn("1.500 seconds", report.text)


if __name__ == "__main__":
    unittest.main()
