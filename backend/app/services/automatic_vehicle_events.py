"""Bridge tracked vehicle observations into immutable dealership crossing events."""
from __future__ import annotations

from pathlib import Path

from app.database import get_db_connection
from app.services import vehicle_events


def _system_user(dealership_id: str) -> dict | None:
    with get_db_connection() as conn:
        row = conn.execute(
            """SELECT * FROM users WHERE dealership_id=? AND active=1
               ORDER BY CASE role WHEN 'administrator' THEN 0 WHEN 'manager' THEN 1 ELSE 2 END,created_at LIMIT 1""",
            (dealership_id,),
        ).fetchone()
    return dict(row) if row else None


def _visible_fraction(bbox, width, height):
    x1, y1, x2, y2 = map(float, bbox)
    area = max(1.0, (x2 - x1) * (y2 - y1))
    clipped = max(0.0, min(width, x2) - max(0.0, x1)) * max(0.0, min(height, y2) - max(0.0, y1))
    return min(1.0, clipped / area)


def submit_recording_track(*, session_id, target, video, track_id, track_items,
                           plate_observations, consensus, best_vehicle_crop,
                           best_plate_crop, model_manifest):
    """Submit a track to every boundary on its configured camera.

    Returns structured skip/results so callers can retain an honest operational log.
    """
    if not target.camera_name:
        return {"submitted": 0, "skip_reason": "camera_not_configured", "results": []}
    if not target.recorded_start_at:
        return {"submitted": 0, "skip_reason": "recording_start_time_missing", "results": []}
    with get_db_connection() as conn:
        session = conn.execute("SELECT dealership_id FROM sessions WHERE session_id=?", (session_id,)).fetchone()
        if not session or not session["dealership_id"]:
            return {"submitted": 0, "skip_reason": "dealership_not_configured", "results": []}
        cameras = conn.execute(
            "SELECT * FROM cameras WHERE dealership_id=? AND name=? AND active=1",
            (session["dealership_id"], target.camera_name),
        ).fetchall()
        if len(cameras) != 1:
            return {"submitted": 0, "skip_reason": "camera_ambiguous_or_missing", "results": []}
        boundaries = conn.execute(
            "SELECT * FROM camera_boundaries WHERE camera_id=? AND active=1 ORDER BY boundary_id",
            (cameras[0]["camera_id"],),
        ).fetchall()
    if not boundaries:
        return {"submitted": 0, "skip_reason": "boundary_not_configured", "results": []}
    user = _system_user(session["dealership_id"])
    if not user:
        return {"submitted": 0, "skip_reason": "audit_actor_unavailable", "results": []}
    observations = []
    for item in track_items:
        bbox = item["vehicle"].bbox
        x1, y1, x2, y2 = map(float, bbox)
        observations.append({
            "timestamp_seconds": item["timestamp_seconds"],
            "center_x": min(1.0, max(0.0, (x1 + x2) / 2 / video.width)),
            "center_y": min(1.0, max(0.0, (y1 + y2) / 2 / video.height)),
            "width": min(1.0, max(0.0, (x2 - x1) / video.width)),
            "height": min(1.0, max(0.0, (y2 - y1) / video.height)),
            "visible_fraction": _visible_fraction(bbox, video.width, video.height),
            "frame_reference": f"/evidence/{session_id}/{Path(item['frame_path']).name}",
            "vehicle_crop_reference": item["vehicle"].crop_path,
            "plate_crop_reference": next((p.get("raw_plate_crop_reference") for p in item.get("plate_observations", []) if p.get("raw_plate_crop_reference")), None),
        })
    results = []
    for boundary in boundaries:
        result = vehicle_events.create_crossing_event(user, {
            "boundary_id": boundary["boundary_id"], "track_id": str(track_id),
            "recorded_start_at": target.recorded_start_at, "session_id": session_id,
            "recording_reference": video.filepath, "consensus_plate": consensus.get("selected_plate"),
            "plate_match_state": consensus.get("state", "uncertain"), "observations": observations,
            "best_vehicle_crop": best_vehicle_crop, "best_plate_crop": best_plate_crop,
            "plate_observations": plate_observations,
            "evidence": {"source_recording": video.filename, "track_observation_count": len(observations)},
            "model_manifest": model_manifest,
        })
        results.append({"boundary_id": boundary["boundary_id"], **result})
    return {"submitted": len(boundaries), "skip_reason": None, "results": results}
