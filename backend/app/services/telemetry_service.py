import re
import os
from typing import List, Optional
from app.models.schemas import GPSPoint

class TelemetryService:
    @staticmethod
    def parse_srt_telemetry(srt_path: str) -> List[GPSPoint]:
        if not os.path.exists(srt_path):
            return []

        gps_points: List[GPSPoint] = []
        with open(srt_path, "r", encoding="utf-8", errors="ignore") as f:
            content = f.read()

        # Split into SRT blocks
        blocks = re.split(r'\n\s*\n', content)

        for block in blocks:
            lines = [l.strip() for l in block.split('\n') if l.strip()]
            if len(lines) < 2:
                continue

            # Parse timestamp line: e.g. 00:01:23,000 --> 00:01:24,000
            time_match = re.search(r'(\d{2}):(\d{2}):(\d{2})[.,](\d{3})', lines[1] if len(lines) > 1 else lines[0])
            if not time_match:
                time_match = re.search(r'(\d{2}):(\d{2}):(\d{2})', block)
            
            if not time_match:
                continue

            hrs, mins, secs = map(int, time_match.groups()[:3])
            t_sec = float(hrs * 3600 + mins * 60 + secs)

            # Extract latitude, longitude, altitude
            lat = None
            lon = None
            alt = 0.0
            rel_alt = 0.0

            # Regex patterns for various DJI formats
            lat_match = re.search(r'\[?latitude\s*[:=]\s*([+-]?\d+\.\d+)\]?', block, re.IGNORECASE)
            lon_match = re.search(r'\[?longitude\s*[:=]\s*([+-]?\d+\.\d+)\]?', block, re.IGNORECASE)
            alt_match = re.search(r'\[?abs_alt\s*[:=]\s*([+-]?\d+\.\d+)\]?', block, re.IGNORECASE)
            rel_match = re.search(r'\[?rel_alt\s*[:=]\s*([+-]?\d+\.\d+)\]?', block, re.IGNORECASE)

            if not lat_match or not lon_match:
                # Try GPS (lon, lat, alt) format
                gps_fmt = re.search(r'GPS\s*\(\s*([+-]?\d+\.\d+)\s*,\s*([+-]?\d+\.\d+)\s*(?:,\s*([+-]?\d+\.\d+))?\s*\)', block)
                if gps_fmt:
                    lon = float(gps_fmt.group(1))
                    lat = float(gps_fmt.group(2))
                    if gps_fmt.group(3):
                        alt = float(gps_fmt.group(3))
            else:
                lat = float(lat_match.group(1))
                lon = float(lon_match.group(1))

            if alt_match:
                alt = float(alt_match.group(1))
            if rel_match:
                rel_alt = float(rel_match.group(1))

            if lat is not None and lon is not None:
                gps_points.append(GPSPoint(
                    timestamp_seconds=round(t_sec, 2),
                    latitude=round(lat, 6),
                    longitude=round(lon, 6),
                    altitude_m=round(alt, 1),
                    relative_altitude_m=round(rel_alt, 1)
                ))

        return gps_points

    @staticmethod
    def get_gps_for_timestamp(gps_points: List[GPSPoint], timestamp_seconds: float) -> Optional[GPSPoint]:
        if not gps_points:
            return None
        # Find closest telemetry point within 5 seconds
        closest = min(gps_points, key=lambda pt: abs(pt.timestamp_seconds - timestamp_seconds))
        if abs(closest.timestamp_seconds - timestamp_seconds) <= 5.0:
            return closest
        return None
