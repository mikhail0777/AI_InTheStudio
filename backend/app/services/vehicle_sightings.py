"""Persistence and filtering for dealership vehicle sightings."""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

from app import database
from app.models.schemas import TargetConfiguration, VideoMetadata


EVENT_BY_CAMERA_ROLE = {
    "lot_entry": "entered_lot",
    "lot_exit": "left_lot",
    "service_entry": "entered_service",
    "service_exit": "left_service",
    "lot_area": "observed_on_lot",
    "unknown": "observed",
}


def captured_at(recorded_start_at: str | None, offset_seconds: float) -> str | None:
    if not recorded_start_at:
        return None
    try:
        return (datetime.fromisoformat(recorded_start_at) + timedelta(seconds=offset_seconds)).isoformat()
    except ValueError:
        return None


def after_hours(captured: str | None, opening: str | None, closing: str | None) -> int | None:
    if not captured or not opening or not closing:
        return None
    try:
        moment = datetime.fromisoformat(captured).time()
        opened = datetime.strptime(opening, "%H:%M").time()
        closed = datetime.strptime(closing, "%H:%M").time()
    except ValueError:
        return None
    inside = opened <= moment < closed if opened <= closed else (moment >= opened or moment < closed)
    return int(not inside)


def save_sighting(*, session_id: str, search_id: str, result_id: str,
                  target: TargetConfiguration, video: VideoMetadata, observation: dict[str, Any],
                  first_seen: float, last_seen: float, frame_path: str, clip_path: str,
                  match_kind: str) -> None:
    absolute_time = captured_at(target.recorded_start_at, observation["timestamp_seconds"])
    with database.get_db_connection() as conn:
        conn.execute(
            """INSERT OR REPLACE INTO vehicle_sightings(
               sighting_id,session_id,search_id,requested_plate,observed_plate,plate_match_mode,
               match_kind,ocr_confidence,similarity,first_seen_seconds,last_seen_seconds,
               best_timestamp_seconds,captured_at,after_hours,camera_name,camera_role,event_type,
               vehicle_make,vehicle_model,vehicle_year,vehicle_color,vehicle_body_type,
               source_filename,evidence_frame,evidence_clip)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (result_id, session_id, search_id, target.plate_number or "", observation["text"],
             target.plate_match_mode, match_kind, observation["confidence"], observation["similarity"],
             first_seen, last_seen, observation["timestamp_seconds"],
             absolute_time, after_hours(absolute_time, target.business_open_time, target.business_close_time),
             target.camera_name, target.camera_role, EVENT_BY_CAMERA_ROLE[target.camera_role],
             target.vehicle_make, target.vehicle_model, target.vehicle_year,
             target.vehicle_color, target.vehicle_body_type, video.filename, frame_path, clip_path),
        )


def list_sightings(*, plate: str | None = None, make: str | None = None,
                   model: str | None = None, year: int | None = None, color: str | None = None,
                   body_type: str | None = None, camera: str | None = None,
                   date_from: str | None = None, date_to: str | None = None,
                   after_hours_only: bool = False, limit: int = 200) -> list[dict[str, Any]]:
    clauses, values = [], []
    filters = {
        "vehicle_make": make, "vehicle_model": model, "vehicle_color": color,
        "vehicle_body_type": body_type, "camera_name": camera,
    }
    if plate:
        clauses.append("(observed_plate LIKE ? OR requested_plate LIKE ?)")
        token = f"%{plate.upper().replace(' ', '').replace('-', '')}%"
        values.extend([token, token])
    for column, value in filters.items():
        if value:
            clauses.append(f"LOWER({column}) LIKE LOWER(?)")
            values.append(f"%{value}%")
    if year is not None:
        clauses.append("vehicle_year=?")
        values.append(year)
    if date_from:
        clauses.append("captured_at>=?")
        values.append(date_from)
    if date_to:
        clauses.append("captured_at<=?")
        values.append(date_to)
    if after_hours_only:
        clauses.append("after_hours=1")
    where = " WHERE " + " AND ".join(clauses) if clauses else ""
    values.append(max(1, min(limit, 1000)))
    with database.get_db_connection() as conn:
        rows = conn.execute(
            "SELECT * FROM vehicle_sightings" + where
            + " ORDER BY COALESCE(captured_at, created_at) DESC, best_timestamp_seconds DESC LIMIT ?",
            values,
        ).fetchall()
    return [dict(row) for row in rows]
