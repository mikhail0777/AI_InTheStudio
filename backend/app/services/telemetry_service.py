"""Parse aircraft telemetry without inventing subject coordinates or altitude."""

import math
import os
import re
from typing import List, Optional

from app.models.schemas import GPSPoint


_NUMBER = r"[+-]?(?:\d+(?:\.\d*)?|\.\d+)"
_TIME = r"(\d{2,}):([0-5]\d):([0-5]\d)(?:[.,](\d{1,6}))?"
_CUE = re.compile(r"^\s*" + _TIME + r"\s*-->\s*" + _TIME + r"[^\r\n]*$", re.MULTILINE)


def _seconds(groups) -> float:
    hours, minutes, seconds, fraction = groups
    return int(hours) * 3600 + int(minutes) * 60 + int(seconds) + float("0." + (fraction or "0"))


def _field(block: str, *names: str) -> Optional[float]:
    match = re.search(r"\b(?:" + "|".join(names) + r")\s*[:=]\s*(" + _NUMBER + r")(?![\w.])", block, re.IGNORECASE)
    return float(match.group(1)) if match else None


class TelemetryService:
    @staticmethod
    def parse_srt_telemetry(srt_path: str) -> List[GPSPoint]:
        if not os.path.isfile(srt_path):
            return []
        with open(srt_path, "r", encoding="utf-8-sig", errors="replace") as source:
            content = source.read()

        # Cue boundaries also support DJI debug output, optional cue numbers,
        # and extra newlines inside a telemetry payload.
        cues = list(_CUE.finditer(content))
        points = {}
        for index, cue in enumerate(cues):
            start = _seconds(cue.groups()[:4])
            end = _seconds(cue.groups()[4:])
            if end < start:
                continue
            block_end = cues[index + 1].start() if index + 1 < len(cues) else len(content)
            block = content[cue.end():block_end]
            latitude = _field(block, "latitude", "lat")
            longitude = _field(block, "longitude", "lon", "lng")
            altitude = _field(block, "abs_alt", "absolute_altitude")
            relative_altitude = _field(block, "rel_alt", "relative_altitude")
            if latitude is None or longitude is None:
                # Legacy DJI GPS tuples are longitude, latitude, altitude.
                legacy = re.search(r"\bGPS\s*\(\s*(" + _NUMBER + r")\s*,\s*(" + _NUMBER + r")\s*(?:,\s*(" + _NUMBER + r")\s*)?\)", block, re.IGNORECASE)
                if legacy:
                    longitude, latitude = float(legacy.group(1)), float(legacy.group(2))
                    if altitude is None and legacy.group(3) is not None:
                        altitude = float(legacy.group(3))
            if latitude is None or longitude is None:
                continue
            if not (-90 <= latitude <= 90 and -180 <= longitude <= 180):
                continue
            if any(value is not None and not math.isfinite(value) for value in (latitude, longitude, altitude, relative_altitude)):
                continue
            # Keep the first valid cue for a timestamp; retain original precision.
            points.setdefault(start, GPSPoint(
                timestamp_seconds=start,
                latitude=latitude,
                longitude=longitude,
                altitude_m=altitude,
                relative_altitude_m=relative_altitude,
                source="srt_aircraft",
            ))
        return [points[timestamp] for timestamp in sorted(points)]

    @staticmethod
    def get_gps_for_timestamp(
        gps_points: List[GPSPoint],
        timestamp_seconds: float,
        max_gap_seconds: float = 1.0,
        telemetry_offset_seconds: float = 0.0,
    ) -> Optional[GPSPoint]:
        """Return the nearest recorded aircraft position, never a subject location.

        A positive offset places an SRT cue later on the video timeline. The
        returned timestamp remains the original SRT timestamp; match offset is
        the absolute alignment error after applying the configured offset.
        """
        if not all(math.isfinite(value) for value in (timestamp_seconds, max_gap_seconds, telemetry_offset_seconds)) or max_gap_seconds < 0:
            raise ValueError("Telemetry lookup requires finite times and a nonnegative maximum gap.")
        if not gps_points or timestamp_seconds < 0:
            return None
        desired = timestamp_seconds - telemetry_offset_seconds
        closest = min(gps_points, key=lambda point: (abs(point.timestamp_seconds - desired), point.timestamp_seconds))
        gap = abs(closest.timestamp_seconds - desired)
        if gap > max_gap_seconds + 1e-9:
            return None
        return closest.model_copy(update={"telemetry_match_offset_seconds": round(gap, 6), "source": "srt_aircraft"})
