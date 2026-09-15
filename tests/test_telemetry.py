import tempfile
import unittest
from pathlib import Path

from app.models.schemas import GPSPoint
from app.services.telemetry_service import TelemetryService


class TelemetryTests(unittest.TestCase):
    def parse(self, content):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "telemetry.srt"
            path.write_bytes(content.encode("utf-8-sig"))
            return TelemetryService.parse_srt_telemetry(str(path))

    def test_retains_milliseconds_and_missing_altitude(self):
        points = self.parse("1\r\n00:00:08,733 --> 00:00:08,766\r\n[latitude: 45.4282011] [longitude: -75.69511]\r\n\r\n2\r\n00:00:08,766 --> 00:00:08,799\r\n[latitude: 45] [longitude: -75] [rel_alt: 54 abs_alt: 102.12]\r\n")
        self.assertEqual([8.733, 8.766], [point.timestamp_seconds for point in points])
        self.assertAlmostEqual(points[0].latitude, 45.4282011)
        self.assertIsNone(points[0].altitude_m)
        self.assertIsNone(points[0].relative_altitude_m)
        self.assertEqual(points[1].relative_altitude_m, 54)
        self.assertEqual(points[1].altitude_m, 102.12)
        self.assertEqual(points[0].source, "srt_aircraft")

    def test_legacy_format_optional_cue_numbers_and_embedded_blank_lines(self):
        points = self.parse("00:01:02.125 --> 00:01:02.5\n\n<font>gps(-75,45,-2.5)</font>\n00:01:03 --> 00:01:04\n[lat = 0] [lon = 0]\n")
        self.assertEqual(len(points), 2)
        self.assertEqual(points[0].timestamp_seconds, 62.125)
        self.assertEqual(points[0].latitude, 45)
        self.assertEqual(points[0].longitude, -75)
        self.assertEqual(points[0].altitude_m, -2.5)
        self.assertEqual(points[1].latitude, 0)

    def test_invalid_coordinates_and_reversed_time_are_rejected(self):
        points = self.parse("1\n00:00:01,000 --> 00:00:02,000\n[latitude: 91] [longitude: -75]\n\n2\n00:00:02,000 --> 00:00:03,000\n[latitude: 45] [longitude: -181]\n\n3\n00:00:05,000 --> 00:00:04,000\n[latitude: 45] [longitude: -75]\n\n4\n00:00:07,000 --> 00:00:08,000\n[latitude: NaN] [longitude: -75]\n")
        self.assertEqual(points, [])

    def test_sorts_and_deduplicates_cues_and_ignores_wall_clock(self):
        points = self.parse("2026-09-11 15:21:08.769\n[latitude: 20] [longitude: 30]\n\n00:00:02,000 --> 00:00:03,000\n[latitude: 45] [longitude: -75]\n\n00:00:01,000 --> 00:00:02,000\n[latitude: 46] [longitude: -75]\n\n00:00:01,000 --> 00:00:02,000\n[latitude: 47] [longitude: -75]\n")
        self.assertEqual([point.timestamp_seconds for point in points], [1, 2])
        self.assertEqual(points[0].latitude, 46)

    def test_lookup_reports_alignment_and_does_not_mutate_source(self):
        source = GPSPoint(timestamp_seconds=8.733, latitude=45, longitude=-75)
        result = TelemetryService.get_gps_for_timestamp([source], 8.75)
        self.assertAlmostEqual(result.telemetry_match_offset_seconds, .017)
        self.assertEqual(result.timestamp_seconds, 8.733)
        self.assertIsNone(source.telemetry_match_offset_seconds)
        self.assertIsNone(TelemetryService.get_gps_for_timestamp([source], 11.0))
        offset = TelemetryService.get_gps_for_timestamp([source], 10.733, telemetry_offset_seconds=2)
        self.assertEqual(offset.telemetry_match_offset_seconds, 0)

    def test_empty_and_invalid_lookup(self):
        self.assertIsNone(TelemetryService.get_gps_for_timestamp([], 1))
        self.assertIsNone(TelemetryService.parse_srt_telemetry("file-that-does-not-exist.srt") or None)
        with self.assertRaises(ValueError):
            TelemetryService.get_gps_for_timestamp([], float("nan"))
        with self.assertRaises(ValueError):
            TelemetryService.get_gps_for_timestamp([], 1, max_gap_seconds=-1)


if __name__ == "__main__":
    unittest.main()
