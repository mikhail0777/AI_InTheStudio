"""Persistence and filtering for dealership vehicle sightings."""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any
import json
import re
import uuid

from app import database
from app.models.schemas import SightingReviewInput, TargetConfiguration, VideoMetadata


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
                  match_kind: str, vehicle=None, plate_analysis: dict[str, Any] | None = None,
                  vehicle_attributes: dict[str, Any] | None = None) -> None:
    absolute_time = captured_at(target.recorded_start_at, observation["timestamp_seconds"])
    vehicle_attributes = vehicle_attributes or {
        "state": "unknown", "selected": None, "ranked_candidates": [],
        "requires_review": True, "reason": "not_evaluated",
    }
    with database.get_db_connection() as conn:
        conn.execute(
            """INSERT OR REPLACE INTO vehicle_sightings(
               sighting_id,session_id,search_id,requested_plate,observed_plate,plate_match_mode,
               match_kind,ocr_confidence,similarity,first_seen_seconds,last_seen_seconds,
               best_timestamp_seconds,captured_at,after_hours,camera_name,camera_role,event_type,
               vehicle_make,vehicle_model,vehicle_year,vehicle_color,vehicle_body_type,
               vehicle_detection_confidence,vehicle_color_confidence,
               requested_vehicle_make,requested_vehicle_model,requested_vehicle_year,
               requested_vehicle_color,requested_vehicle_body_type,
               vehicle_attribute_state,vehicle_attribute_candidates_json,
               source_filename,evidence_frame,evidence_clip)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (result_id, session_id, search_id, target.plate_number or "", observation["text"],
             target.plate_match_mode, match_kind, observation["confidence"], observation["similarity"],
             first_seen, last_seen, observation["timestamp_seconds"],
             absolute_time, after_hours(absolute_time, target.business_open_time, target.business_close_time),
             target.camera_name, target.camera_role, EVENT_BY_CAMERA_ROLE[target.camera_role],
             None, None, None,
             vehicle.color if vehicle else None, vehicle.category if vehicle else None,
             vehicle.confidence if vehicle else None, vehicle.color_confidence if vehicle else None,
             target.vehicle_make, target.vehicle_model, target.vehicle_year,
             target.vehicle_color, target.vehicle_body_type,
             vehicle_attributes.get("state"), json.dumps(vehicle_attributes),
             video.filename, frame_path, clip_path),
        )
        conn.execute("UPDATE vehicle_sightings SET dealership_id=(SELECT dealership_id FROM sessions WHERE session_id=?) WHERE sighting_id=?",(session_id,result_id))
        if plate_analysis:
            consensus = plate_analysis.get("consensus") or {}
            best = plate_analysis.get("best_observation") or {}
            conn.execute(
                """UPDATE vehicle_sightings SET consensus_plate=?,consensus_state=?,
                   consensus_details_json=?,best_plate_crop=?,enhanced_plate_crop=?
                   WHERE sighting_id=?""",
                (consensus.get("selected_plate"), consensus.get("state"),
                 json.dumps(consensus), best.get("raw_plate_crop_reference"),
                 best.get("enhanced_plate_crop_reference"), result_id),
            )
            for item in plate_analysis.get("observations") or []:
                conn.execute(
                    """INSERT INTO plate_ocr_observations(
                       observation_id,sighting_id,frame_idx,timestamp_seconds,
                       source_frame_reference,detected_bbox_json,raw_plate_crop_reference,
                       enhanced_plate_crop_reference,quality_metrics_json,
                       ocr_candidates_json,model_manifest_json)
                       VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
                    ("plate_observation_" + uuid.uuid4().hex, result_id, item["frame_idx"],
                     item["timestamp_seconds"], item["source_frame_reference"],
                     json.dumps(item.get("bbox") or []), item.get("raw_plate_crop_reference"),
                     item.get("enhanced_plate_crop_reference"),
                     json.dumps(item.get("quality_metrics") or {}),
                     json.dumps(item.get("candidates") or []),
                     json.dumps(item.get("model_manifest") or {})),
                )


def list_sightings(*, plate: str | None = None, make: str | None = None,
                   model: str | None = None, year: int | None = None, color: str | None = None,
                   body_type: str | None = None, camera: str | None = None,
                   date_from: str | None = None, date_to: str | None = None,
                   after_hours_only: bool = False, limit: int = 200,
                   dealership_id: str | None = None) -> list[dict[str, Any]]:
    clauses, values = [], []
    if dealership_id:
        clauses.append("vehicle_sightings.dealership_id=?")
        values.append(dealership_id)
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
            "SELECT vehicle_sightings.*, sessions.playback_url AS source_video_url FROM vehicle_sightings "
            "JOIN sessions ON sessions.session_id=vehicle_sightings.session_id" + where
            + " ORDER BY COALESCE(captured_at, vehicle_sightings.created_at) DESC, best_timestamp_seconds DESC LIMIT ?",
            values,
        ).fetchall()
    results = []
    for row in rows:
        item = dict(row)
        item["vehicle_attribute_candidates"] = json.loads(
            item.pop("vehicle_attribute_candidates_json", None) or "{}"
        )
        results.append(item)
    return results


def _public_sighting(conn, sighting_id: str) -> dict[str, Any]:
    row = conn.execute(
        "SELECT vehicle_sightings.*, sessions.playback_url AS source_video_url FROM vehicle_sightings "
        "JOIN sessions ON sessions.session_id=vehicle_sightings.session_id WHERE sighting_id=?",
        (sighting_id,),
    ).fetchone()
    if not row:
        raise LookupError("Sighting not found.")
    return dict(row)


def review_sighting(sighting_id: str, review: SightingReviewInput, actor: dict[str,Any] | None = None) -> dict[str, Any]:
    with database.get_db_connection() as conn:
        conn.execute("BEGIN IMMEDIATE")
        previous = _public_sighting(conn, sighting_id)
        updates: dict[str, Any] = {}
        reason = (review.reason or "").strip() or None
        note = (review.note or "").strip() or None
        if review.action == "confirm":
            updates["review_status"] = "confirmed"
        elif review.action == "reject":
            updates["review_status"] = "rejected"
        elif review.action == "reopen":
            updates["review_status"] = "needs_research"
        elif review.action == "correct":
            corrected = re.sub(r"[^A-Z0-9]", "", (review.corrected_plate or "").upper())
            if not 3 <= len(corrected) <= 10 or not reason:
                raise ValueError("A 3-10 character plate and correction reason are required.")
            updates.update(corrected_plate=corrected, review_status="needs_research")
        elif review.action == "note":
            if not note:
                raise ValueError("A note is required.")
            updates["review_notes"] = note
        assignments = ",".join(f"{column}=?" for column in updates)
        conn.execute(f"UPDATE vehicle_sightings SET {assignments} WHERE sighting_id=?",
                     (*updates.values(), sighting_id))
        current = _public_sighting(conn, sighting_id)
        conn.execute(
            "INSERT INTO sighting_revisions(revision_id,sighting_id,action,previous_value,new_value,reason) VALUES (?,?,?,?,?,?)",
            (uuid.uuid4().hex, sighting_id, review.action, json.dumps(previous), json.dumps(current), reason or note),
        )
        if actor:
            from app.services.governance import audit
            audit(conn,actor,"sighting."+review.action,"sighting",sighting_id,previous,current,reason or note)
        feedback = {"confirm": "confirmed", "reject": "rejected", "reopen": "needs_research"}.get(review.action)
        if feedback:
            result = conn.execute("SELECT payload FROM search_results WHERE result_id=?", (sighting_id,)).fetchone()
            if result:
                payload = json.loads(result["payload"])
                payload["human_feedback"] = feedback
                payload["human_notes"] = current.get("review_notes")
                conn.execute("UPDATE search_results SET human_feedback=?,human_notes=?,payload=? WHERE result_id=?",
                             (feedback, current.get("review_notes"), json.dumps(payload), sighting_id))
        return current


def list_revisions(sighting_id: str) -> list[dict[str, Any]]:
    with database.get_db_connection() as conn:
        _public_sighting(conn, sighting_id)
        rows = conn.execute(
            "SELECT revision_id,action,actor,reason,created_at FROM sighting_revisions WHERE sighting_id=? ORDER BY created_at, rowid",
            (sighting_id,),
        ).fetchall()
    return [dict(row) for row in rows]


def get_plate_analysis(sighting_id: str, dealership_id: str) -> dict[str, Any]:
    """Return immutable raw OCR evidence and its separately stored consensus."""
    with database.get_db_connection() as conn:
        sighting = conn.execute(
            """SELECT sighting_id,observed_plate,consensus_plate,consensus_state,
               consensus_details_json,best_plate_crop,enhanced_plate_crop
               FROM vehicle_sightings WHERE sighting_id=? AND dealership_id=?""",
            (sighting_id, dealership_id),
        ).fetchone()
        if not sighting:
            raise LookupError("Sighting not found.")
        observations = conn.execute(
            """SELECT * FROM plate_ocr_observations WHERE sighting_id=?
               ORDER BY timestamp_seconds,frame_idx,observation_id""",
            (sighting_id,),
        ).fetchall()
    result = dict(sighting)
    result["consensus"] = json.loads(result.pop("consensus_details_json") or "{}")
    result["observations"] = []
    for row in observations:
        item = dict(row)
        for key, default in (
            ("detected_bbox_json", []), ("quality_metrics_json", {}),
            ("ocr_candidates_json", []), ("model_manifest_json", {}),
        ):
            item[key.removesuffix("_json")] = json.loads(item.pop(key) or json.dumps(default))
        result["observations"].append(item)
    return result
