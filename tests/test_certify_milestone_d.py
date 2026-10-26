import unittest

from scripts.certify_milestone_d import build_report, markdown


class MilestoneDCertificationTests(unittest.TestCase):
    def test_report_refuses_certification_when_video_gates_are_missing(self):
        report = build_report()
        gates = {item["name"]: item for item in report["release_gates"]}

        self.assertFalse(report["production_certified"])
        self.assertEqual(report["decision"], "not_ready_for_production")
        self.assertEqual(gates["Eligible vehicle crossing event recall"]["status"], "unmeasured")
        self.assertAlmostEqual(gates["OCR character accuracy"]["measured_value"], 0.9779385171790235)
        self.assertAlmostEqual(gates["Make + model top-1"]["measured_value"], 0.9210110584518167)
        self.assertFalse(report["capabilities"]["automatic_worker_to_crossing_event_wiring"])
        self.assertFalse(report["capabilities"]["live_camera_ingestion"])

    def test_markdown_keeps_measured_and_unmeasured_results_distinct(self):
        text = markdown(build_report())
        self.assertIn("**Decision: NOT READY FOR PRODUCTION.**", text)
        self.assertIn("97.79%", text)
        self.assertIn("92.10%", text)
        self.assertIn("Not measured", text)


if __name__ == "__main__":
    unittest.main()
