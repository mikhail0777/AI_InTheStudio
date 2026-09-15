import tempfile
import unittest
from pathlib import Path

from app.models.schemas import AnalysisStrategy, AttributeDetail, GPSPoint, SearchPlan, TargetConfiguration, TrackResult, VideoMetadata
from app.services.report_generator import ReportGenerator


def make_track(**changes):
    fields = dict(
        session_id="flight_test", track_id=1, first_seen_seconds=8.733,
        last_seen_seconds=12.3, best_timestamp_seconds=9.233,
        classification="possible_match", person_detection_confidence=.69,
        appearance_similarity=.55, evidence_quality=.94, final_ranking_score=.63,
        observations_analyzed=6,
        attributes={"upper_clothing": AttributeDetail(expected="green top", observed="green; partly obscured", score=.8, visibility="partial")},
        matching_evidence=["Green visible clothing"], conflicting_evidence=[],
        unknown_attributes=["Hair obscured"], requires_human_review=True,
        explanation="Candidate requires review", best_frame_path="/crops/flight_test/person.jpg",
        gps_location=GPSPoint(timestamp_seconds=9.2, latitude=45.42, longitude=-75.69, telemetry_match_offset_seconds=.033),
    )
    fields.update(changes)
    return TrackResult(**fields)


class ReportTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.reports_dir = str(Path(self.temporary.name) / "reports")
        self.config = TargetConfiguration(free_text_description="Person with green top and black backpack")
        self.plan = SearchPlan(target_summary="Green clothing", high_value_attributes=["green top"], supporting_attributes=[], low_reliability_attributes=[], negative_attributes=[], analysis_strategy=AnalysisStrategy())
        self.video = VideoMetadata(filename="flight.mp4", filepath="/private/flight.mp4", duration_seconds=180, frame_count=5400, fps=30, width=1920, height=1080, codec="h264", file_size_mb=12, creation_timestamp="2026-09-14")

    def generate(self, tracks=None, **kwargs):
        return ReportGenerator.generate_report("flight_test", self.config, self.plan, self.video, kwargs.pop("frame_count", 3), tracks or [], True, self.reports_dir, **kwargs)

    def html(self):
        return (Path(self.reports_dir) / "report_flight_test.html").read_text(encoding="utf-8")

    def test_no_detections_do_not_fabricate_unsearched_intervals(self):
        report, url = self.generate(sampled_timestamps=[0, 90, 179], total_people_detected=0, run_id="run_one", failed_timestamps=[1.5])
        self.assertEqual(report.unsearched_intervals, [])
        self.assertEqual(report.analyzed_timestamps_seconds, [0, 90, 179])
        self.assertEqual(report.total_frames_sampled, 3)
        self.assertEqual(report.failed_sample_timestamps_seconds, [1.5])
        self.assertIn("not continuous coverage", report.coverage_summary)
        self.assertIn("does not establish that no person", self.html())
        self.assertIn("/api/sessions/flight_test/report?revision=", url)
        self.assertIn("Failed sample times", self.html())

    def test_review_evidence_and_aircraft_coordinates_without_score_panels(self):
        track = make_track()
        self.generate([track], sampled_timestamps=[8.733, 9.233, 12.3], total_people_detected=12)
        html = self.html()
        self.assertIn("Aircraft capture position", html)
        self.assertIn("telemetry alignment gap 0.033 s", html)
        self.assertNotIn("absolute altitude", html)
        self.assertIn("Awaiting human review", html)
        self.assertIn("green; partly obscured", html)
        for forbidden in ("63%", "69%", "55%", "94%", "Dispatch", "Re-fly", "30m", "/private/flight.mp4"):
            self.assertNotIn(forbidden, html)

    def test_feedback_replaces_report_with_new_revision(self):
        first, first_url = self.generate([make_track()])
        second, second_url = self.generate([make_track(human_feedback="rejected", human_notes="Tire, not a person", requires_human_review=False)])
        self.assertNotEqual(first.report_revision, second.report_revision)
        self.assertNotEqual(first_url, second_url)
        self.assertIn("Rejected by operator", self.html())
        self.assertIn("Tire, not a person", self.html())
        self.assertNotIn("Awaiting human review", self.html())
        self.assertEqual(len(list(Path(self.reports_dir).glob("*.html"))), 1)
        self.assertEqual(list(Path(self.reports_dir).glob("*.tmp")), [])

    def test_escapes_all_free_text_and_blocks_remote_evidence_urls(self):
        payload = '<script>alert("x")</script>'
        self.config.free_text_description = payload
        self.plan.target_summary = payload
        self.video.filename = payload
        track = make_track(explanation=payload, human_notes=payload, matching_evidence=[payload], unknown_attributes=[payload], best_frame_path='https://evil.example/pixel.jpg" onerror="alert(1)')
        track.attributes["upper_clothing"].observed = payload
        report, _ = self.generate([track], run_id=payload)
        html = self.html()
        self.assertNotIn("<script>", html)
        self.assertGreaterEqual(html.count("&lt;script&gt;"), 8)
        self.assertNotIn("evil.example", html)
        self.assertNotIn("onerror=", html)
        self.assertIn("Content-Security-Policy", html)
        # The model retains the literal evidence; only its HTML representation is escaped.
        self.assertEqual(report.ranked_sightings[0].human_notes, payload)

    def test_embeds_only_session_raster_evidence_and_rejects_traversal(self):
        crops = Path(self.temporary.name) / "crops"
        folder = crops / "flight_test"
        folder.mkdir(parents=True)
        (folder / "person.jpg").write_bytes(b"\xff\xd8\xffsample image bytes")
        self.generate([make_track()])
        self.assertIn("data:image/jpeg;base64,", self.html())
        for unsafe in ("/crops/flight_test/../other.jpg", "/crops/flight_other/person.jpg", "/crops/flight_test/%2e%2e/other.jpg"):
            self.assertEqual(ReportGenerator._thumbnail(make_track(best_frame_path=unsafe), crops), "")
        (folder / "fake.jpg").write_text("<svg onload='alert(1)'></svg>", encoding="utf-8")
        self.assertEqual(ReportGenerator._thumbnail(make_track(best_frame_path="/crops/flight_test/fake.jpg"), crops), "")

    def test_rejects_invalid_report_path_and_negative_count(self):
        with self.assertRaises(ValueError):
            ReportGenerator.generate_report("../outside", self.config, self.plan, self.video, 0, [], False, self.reports_dir)
        with self.assertRaises(ValueError):
            self.generate(frame_count=-1)

    def test_historical_counts_are_labeled_as_unavailable_coverage(self):
        report, _ = self.generate([make_track()])
        self.assertIn("sampling history is unavailable", report.coverage_summary)
        self.assertTrue(any("full detector totals are unavailable" in item for item in report.limitations))
        self.assertEqual(report.unsearched_intervals, [])


if __name__ == "__main__":
    unittest.main()
