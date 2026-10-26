"""Gate-crossing events and idempotent vehicle inventory transitions."""
from __future__ import annotations

import hashlib
import json
import re
import uuid
from datetime import datetime, timedelta

from app.database import get_db_connection
from app.services.governance import audit
from app.services.plate_track_consensus import build_track_plate_consensus, plate_observation_score


def _plate(value: str | None) -> str | None:
    normalized = re.sub(r"[^A-Z0-9]", "", (value or "").upper())
    return normalized or None


def _row(row):
    if not row:
        return None
    value = dict(row)
    for key in ("ocr_candidates_json", "evidence_json", "model_manifest_json"):
        if key in value:
            value[key.removesuffix("_json")] = json.loads(value.pop(key) or ("[]" if key == "ocr_candidates_json" else "{}"))
    return value


def _validate_unit(value, label):
    value = float(value)
    if not 0 <= value <= 1:
        raise ValueError(f"{label} must be between 0 and 1.")
    return value


def create_boundary(user, camera_id, values):
    boundary_type = values.get("boundary_type")
    travel_direction = values.get("travel_direction")
    if boundary_type not in ("entrance", "exit"):
        raise ValueError("Boundary type must be entrance or exit.")
    if travel_direction not in ("negative_to_positive", "positive_to_negative"):
        raise ValueError("Travel direction must identify one side-to-side crossing direction.")
    coordinates = tuple(_validate_unit(values[key], key) for key in ("x1", "y1", "x2", "y2"))
    if coordinates[:2] == coordinates[2:]:
        raise ValueError("Boundary endpoints must be different.")
    thresholds = tuple(_validate_unit(values.get(key, default), key) for key, default in (
        ("min_vehicle_width", .08), ("min_vehicle_height", .08), ("min_visible_fraction", .65)
    ))
    name = values["name"].strip()
    if not name:
        raise ValueError("Boundary name is required.")
    boundary_id = "boundary_" + uuid.uuid4().hex
    with get_db_connection() as conn:
        camera = conn.execute(
            "SELECT * FROM cameras WHERE camera_id=? AND dealership_id=?",
            (camera_id, user["dealership_id"]),
        ).fetchone()
        if not camera:
            raise LookupError("Camera not found.")
        conn.execute(
            """INSERT INTO camera_boundaries(
               boundary_id,camera_id,name,boundary_type,x1,y1,x2,y2,travel_direction,
               min_vehicle_width,min_vehicle_height,min_visible_fraction)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
            (boundary_id, camera_id, name, boundary_type, *coordinates,
             travel_direction, *thresholds),
        )
        row = conn.execute("SELECT * FROM camera_boundaries WHERE boundary_id=?", (boundary_id,)).fetchone()
        audit(conn, user, "camera_boundary.created", "camera_boundary", boundary_id,
              new=dict(row), sources={"camera_id": camera_id})
    return dict(row)


def list_boundaries(user, camera_id=None):
    query = """SELECT b.* FROM camera_boundaries b JOIN cameras c ON c.camera_id=b.camera_id
               WHERE c.dealership_id=?"""
    params = [user["dealership_id"]]
    if camera_id:
        query += " AND b.camera_id=?"
        params.append(camera_id)
    query += " ORDER BY c.name,b.name"
    with get_db_connection() as conn:
        return [dict(row) for row in conn.execute(query, params).fetchall()]


def _side(boundary, observation):
    return ((boundary["x2"] - boundary["x1"]) * (observation["center_y"] - boundary["y1"])
            - (boundary["y2"] - boundary["y1"]) * (observation["center_x"] - boundary["x1"]))


def _segments_intersect(a, b, c, d):
    def orient(p, q, r):
        return (q[0] - p[0]) * (r[1] - p[1]) - (q[1] - p[1]) * (r[0] - p[0])
    first, second = orient(a, b, c), orient(a, b, d)
    third, fourth = orient(c, d, a), orient(c, d, b)
    return first * second <= 0 and third * fourth <= 0


def find_crossing(boundary, observations, epsilon=1e-6):
    """Return the bracketing observations for one eligible directed crossing."""
    ordered = sorted(observations, key=lambda item: item["timestamp_seconds"])
    eligible = [item for item in ordered
                if item["width"] >= boundary["min_vehicle_width"]
                and item["height"] >= boundary["min_vehicle_height"]
                and item.get("visible_fraction", 1) >= boundary["min_visible_fraction"]]
    for previous, current in zip(eligible, eligible[1:]):
        before, after = _side(boundary, previous), _side(boundary, current)
        if abs(before) <= epsilon or abs(after) <= epsilon:
            continue
        directed = (before < 0 < after if boundary["travel_direction"] == "negative_to_positive"
                    else before > 0 > after)
        if not directed:
            continue
        if _segments_intersect(
            (previous["center_x"], previous["center_y"]),
            (current["center_x"], current["center_y"]),
            (boundary["x1"], boundary["y1"]), (boundary["x2"], boundary["y2"]),
        ):
            ratio = abs(before) / (abs(before) + abs(after))
            timestamp = previous["timestamp_seconds"] + ratio * (
                current["timestamp_seconds"] - previous["timestamp_seconds"])
            return previous, current, timestamp
    return None


def _absolute_time(recorded_start_at, offset_seconds):
    if recorded_start_at:
        try:
            return (datetime.fromisoformat(recorded_start_at) + timedelta(seconds=offset_seconds)).isoformat()
        except ValueError as error:
            raise ValueError("Recording start time must be ISO-8601.") from error
    raise ValueError("A recording start time is required for an immutable event timestamp.")


def _match_vehicle(conn, dealership_id, normalized_plate):
    if not normalized_plate:
        return None, "plate_unavailable"
    rows = conn.execute(
        """SELECT DISTINCT v.* FROM vehicles v LEFT JOIN plate_aliases a ON a.vehicle_id=v.vehicle_id
           WHERE v.dealership_id=? AND (v.normalized_plate=? OR a.normalized_plate=?)""",
        (dealership_id, normalized_plate, normalized_plate),
    ).fetchall()
    if len(rows) == 1:
        return rows[0], None
    return None, "plate_not_registered" if not rows else "ambiguous_plate_match"


def create_crossing_event(user, values):
    values = dict(values)
    plate_observations = list(values.get("plate_observations") or [])
    if plate_observations:
        consensus, selection = build_track_plate_consensus(plate_observations)
        values["consensus_plate"] = consensus.get("selected_plate")
        values["plate_match_state"] = consensus["state"]
        # Preserve every raw observation while explicitly marking the subset
        # that contributed to the decision.
        selected_indices = set(selection.selected_frame_indices)
        values["ocr_candidates"] = [
            {**item, "selected_for_consensus": int(item.get("frame_idx", -1)) in selected_indices}
            for item in plate_observations
        ]
        evidence = dict(values.get("evidence") or {})
        evidence["plate_consensus"] = consensus
        values["evidence"] = evidence
        manifest = dict(values.get("model_manifest") or {})
        manifest["multi_frame_ocr"] = consensus["frame_selection"]["policy"]
        values["model_manifest"] = manifest
        if not values.get("best_plate_crop") and selection.observations:
            best = max(selection.observations, key=plate_observation_score)
            values["best_plate_crop"] = (
                best.get("raw_plate_crop_reference") or best.get("plate_crop_reference")
            )
    observations = values.get("observations") or []
    if len(observations) < 2:
        raise ValueError("At least two tracked observations are required.")
    for item in observations:
        for key in ("center_x", "center_y", "width", "height", "visible_fraction"):
            _validate_unit(item.get(key, 1 if key == "visible_fraction" else -1), key)
    with get_db_connection() as conn:
        conn.execute("BEGIN IMMEDIATE")
        boundary = conn.execute(
            """SELECT b.*,c.dealership_id,c.timezone,c.name camera_name FROM camera_boundaries b
               JOIN cameras c ON c.camera_id=b.camera_id
               WHERE b.boundary_id=? AND b.active=1 AND c.active=1 AND c.dealership_id=?""",
            (values["boundary_id"], user["dealership_id"]),
        ).fetchone()
        if not boundary:
            raise LookupError("Active camera boundary not found.")
        if values.get("session_id"):
            session = conn.execute("SELECT dealership_id FROM sessions WHERE session_id=?", (values["session_id"],)).fetchone()
            if not session or session["dealership_id"] != user["dealership_id"]:
                raise LookupError("Recording session not found.")
        crossing = find_crossing(boundary, observations)
        if not crossing:
            return {"created": False, "reason": "no_eligible_directed_crossing", "event": None}
        _, _, crossing_seconds = crossing
        event_type = "arrival" if boundary["boundary_type"] == "entrance" else "departure"
        idempotency_source = "|".join((user["dealership_id"], boundary["camera_id"], boundary["boundary_id"],
                                      values.get("session_id") or values.get("recording_reference") or "recording",
                                      str(values["track_id"]), event_type))
        idempotency_key = hashlib.sha256(idempotency_source.encode()).hexdigest()
        existing = conn.execute("SELECT * FROM vehicle_events WHERE idempotency_key=?", (idempotency_key,)).fetchone()
        if existing:
            return {"created": False, "reason": "duplicate", "event": _row(existing)}

        match_state = values.get("plate_match_state", "uncertain")
        if match_state not in ("exact_consensus", "reviewed", "uncertain", "conflicting"):
            raise ValueError("Unknown plate match state.")
        consensus_plate = _plate(values.get("consensus_plate"))
        vehicle = None
        review_reason = None
        if match_state in ("exact_consensus", "reviewed"):
            vehicle, review_reason = _match_vehicle(conn, user["dealership_id"], consensus_plate)
        else:
            review_reason = "ocr_candidates_conflict" if match_state == "conflicting" else "plate_requires_review"

        desired_status = "on_lot" if event_type == "arrival" else "off_lot"
        transition = None
        if vehicle:
            if vehicle["status"] not in ("on_lot", "off_lot"):
                review_reason = "inventory_state_unknown"
            elif vehicle["status"] == desired_status:
                review_reason = "conflicting_inventory_state"
            else:
                transition = (vehicle["status"], desired_status)
        review_state = "confirmed" if transition else "requires_review"
        event_id = "event_" + uuid.uuid4().hex
        occurred_at = _absolute_time(values.get("recorded_start_at"), crossing_seconds)
        # Suppress track fragmentation retries only when the same normalized plate
        # crosses the same boundary in the same source within three seconds.
        if consensus_plate and match_state in ("exact_consensus", "reviewed"):
            nearby = conn.execute(
                """SELECT * FROM vehicle_events WHERE dealership_id=? AND boundary_id=?
                   AND COALESCE(session_id,recording_reference)=COALESCE(?,?)
                   AND consensus_plate=? ORDER BY occurred_at DESC LIMIT 10""",
                (user["dealership_id"], boundary["boundary_id"], values.get("session_id"),
                 values.get("recording_reference"), consensus_plate),
            ).fetchall()
            current_time = datetime.fromisoformat(occurred_at)
            for prior in nearby:
                try: delta = abs((current_time - datetime.fromisoformat(prior["occurred_at"])).total_seconds())
                except ValueError: continue
                if delta <= 3:
                    return {"created": False, "reason": "duplicate_fragment", "event": _row(prior)}
        evidence = values.get("evidence") or {}
        conn.execute(
            """INSERT INTO vehicle_events(
               event_id,dealership_id,camera_id,boundary_id,session_id,track_id,event_type,
               occurred_at,timezone,direction_of_travel,consensus_plate,plate_match_state,
               matched_vehicle_id,review_state,review_reason,recording_reference,best_vehicle_crop,
               best_plate_crop,ocr_candidates_json,evidence_json,model_manifest_json,idempotency_key)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (event_id, user["dealership_id"], boundary["camera_id"], boundary["boundary_id"],
             values.get("session_id"), str(values["track_id"]), event_type, occurred_at,
             boundary["timezone"], boundary["travel_direction"], consensus_plate, match_state,
             vehicle["vehicle_id"] if vehicle else None, review_state, review_reason,
             values.get("recording_reference"), values.get("best_vehicle_crop"), values.get("best_plate_crop"),
             json.dumps(values.get("ocr_candidates") or []), json.dumps(evidence),
             json.dumps(values.get("model_manifest") or {}), idempotency_key),
        )
        for index, item in enumerate(sorted(observations, key=lambda row: row["timestamp_seconds"])):
            conn.execute(
                """INSERT INTO vehicle_event_observations(
                   event_id,observation_index,timestamp_seconds,center_x,center_y,width,height,visible_fraction,
                   frame_reference,vehicle_crop_reference,plate_crop_reference) VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
                (event_id, index, item["timestamp_seconds"], item["center_x"], item["center_y"],
                 item["width"], item["height"], item.get("visible_fraction", 1), item.get("frame_reference"),
                 item.get("vehicle_crop_reference"), item.get("plate_crop_reference")),
            )
        if transition:
            transition_id = "transition_" + uuid.uuid4().hex
            conn.execute(
                """INSERT INTO vehicle_status_transitions(
                   transition_id,vehicle_id,event_id,previous_status,new_status,occurred_at,evidence_json)
                   VALUES (?,?,?,?,?,?,?)""",
                (transition_id, vehicle["vehicle_id"], event_id, transition[0], transition[1], occurred_at,
                 json.dumps({"event_id": event_id, **evidence})),
            )
            conn.execute("UPDATE vehicles SET status=?,updated_at=CURRENT_TIMESTAMP WHERE vehicle_id=?",
                         (transition[1], vehicle["vehicle_id"]))
            audit(conn, user, "vehicle.status_transition", "vehicle", vehicle["vehicle_id"],
                  {"status": transition[0]}, {"status": transition[1]},
                  sources={"event_id": event_id, "transition_id": transition_id})
        event = conn.execute("SELECT * FROM vehicle_events WHERE event_id=?", (event_id,)).fetchone()
        audit(conn, user, "vehicle_event.created", "vehicle_event", event_id, new=_row(event),
              sources={"camera_id": boundary["camera_id"], "boundary_id": boundary["boundary_id"]})
        return {"created": True, "reason": None, "event": _row(event)}


def list_events(user, review_state=None, vehicle_id=None, limit=200):
    query = """SELECT e.*,c.name camera_name,b.name boundary_name,t.previous_status,t.new_status
               FROM vehicle_events e JOIN cameras c ON c.camera_id=e.camera_id
               JOIN camera_boundaries b ON b.boundary_id=e.boundary_id
               LEFT JOIN vehicle_status_transitions t ON t.event_id=e.event_id
               WHERE e.dealership_id=?"""
    params = [user["dealership_id"]]
    if review_state:
        query += " AND e.review_state=?"
        params.append(review_state)
    if vehicle_id:
        query += " AND e.matched_vehicle_id=?"
        params.append(vehicle_id)
    query += " ORDER BY e.occurred_at DESC LIMIT ?"
    params.append(min(max(int(limit), 1), 1000))
    with get_db_connection() as conn:
        return [_row(row) for row in conn.execute(query, params).fetchall()]


def get_event(user, event_id):
    with get_db_connection() as conn:
        event = conn.execute("SELECT * FROM vehicle_events WHERE event_id=? AND dealership_id=?",
                             (event_id, user["dealership_id"])).fetchone()
        if not event:
            raise LookupError("Vehicle event not found.")
        observations = [dict(row) for row in conn.execute(
            "SELECT * FROM vehicle_event_observations WHERE event_id=? ORDER BY observation_index", (event_id,)
        ).fetchall()]
        transition = conn.execute("SELECT * FROM vehicle_status_transitions WHERE event_id=?", (event_id,)).fetchone()
    result = _row(event)
    result["observations"] = observations
    result["status_transition"] = dict(transition) if transition else None
    return result
