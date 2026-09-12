import os
import json
import uuid
import asyncio
from typing import List, Optional
from fastapi import APIRouter, UploadFile, File, Form, HTTPException, BackgroundTasks, Query
from fastapi.responses import FileResponse, StreamingResponse
from app.database import get_db_connection, init_db
from app.models.schemas import (
    TargetConfiguration, SessionStatus, TrackResult, HumanFeedbackInput,
    SARReport, AgentLogEntry, VideoMetadata, AttributeDetail, GPSPoint
)
from app.services.video_service import VideoService
from app.services.telemetry_service import TelemetryService
from app.services.agentic_loop import AgenticLoopManager, DATA_DIR

router = APIRouter(prefix="/api")

@router.post("/sessions", response_model=SessionStatus)
async def create_session(target_config: Optional[TargetConfiguration] = None):
    init_db()
    session_id = f"flight_{uuid.uuid4().hex[:8]}"

    if not target_config:
        target_config = TargetConfiguration(
            free_text_description="Locate a person wearing a red hoodie, dark pants, and blue backpack."
        )

    conn = get_db_connection()
    conn.execute(
        "INSERT INTO sessions (session_id, status, progress_percent, current_stage, target_config) VALUES (?, ?, ?, ?, ?)",
        (session_id, "created", 0.0, "created", json.dumps(target_config.dict()))
    )
    conn.commit()
    conn.close()

    AgenticLoopManager.log_agent_event(session_id, "INIT", f"Created analysis session {session_id}.", "info")

    return SessionStatus(
        session_id=session_id,
        status="created",
        progress_percent=0.0,
        current_stage="created",
        agent_logs=[AgentLogEntry(timestamp="00:00:00", step="INIT", message=f"Session {session_id} created.", level="info")]
    )

@router.post("/sessions/{session_id}/video")
async def upload_video(session_id: str, file: UploadFile = File(...)):
    if not file.filename.lower().endswith(('.mp4', '.mov', '.mkv')):
        raise HTTPException(status_code=400, detail="Unsupported video format. Allowed: MP4, MOV, MKV.")

    uploads_dir = os.path.join(DATA_DIR, "uploads", session_id)
    os.makedirs(uploads_dir, exist_ok=True)
    file_path = os.path.join(uploads_dir, file.filename)

    with open(file_path, "wb") as f:
        content = await file.read()
        f.write(content)

    video_meta = VideoService.inspect_video(file_path)

    conn = get_db_connection()
    conn.execute(
        "UPDATE sessions SET status=?, video_metadata=? WHERE session_id=?",
        ("uploaded", json.dumps(video_meta.dict()), session_id)
    )
    conn.commit()
    conn.close()

    AgenticLoopManager.log_agent_event(
        session_id,
        "UPLOAD",
        f"Ingested video '{video_meta.filename}' ({video_meta.duration_seconds}s, {video_meta.width}x{video_meta.height} @ {video_meta.fps} FPS).",
        "info"
    )

    return {"status": "uploaded", "video_metadata": video_meta}

@router.post("/sessions/{session_id}/telemetry")
async def upload_telemetry(session_id: str, file: UploadFile = File(...)):
    if not file.filename.lower().endswith(('.srt', '.txt', '.csv', '.json')):
        raise HTTPException(status_code=400, detail="Unsupported telemetry format. Allowed: SRT, CSV, JSON.")

    uploads_dir = os.path.join(DATA_DIR, "uploads", session_id)
    os.makedirs(uploads_dir, exist_ok=True)
    file_path = os.path.join(uploads_dir, file.filename)

    with open(file_path, "wb") as f:
        content = await file.read()
        f.write(content)

    gps_points = TelemetryService.parse_srt_telemetry(file_path)

    conn = get_db_connection()
    conn.execute("DELETE FROM telemetry WHERE session_id=?", (session_id,))
    for pt in gps_points:
        conn.execute(
            "INSERT OR REPLACE INTO telemetry (session_id, timestamp_seconds, latitude, longitude, altitude_m, relative_altitude_m) VALUES (?, ?, ?, ?, ?, ?)",
            (session_id, pt.timestamp_seconds, pt.latitude, pt.longitude, pt.altitude_m, pt.relative_altitude_m)
        )
    conn.execute("UPDATE sessions SET has_telemetry=1 WHERE session_id=?", (session_id,))
    conn.commit()
    conn.close()

    AgenticLoopManager.log_agent_event(
        session_id,
        "TELEMETRY",
        f"Uploaded telemetry log '{file.filename}'. Parsed {len(gps_points)} timestamped GPS coordinates.",
        "info"
    )

    return {"status": "telemetry_uploaded", "gps_points_count": len(gps_points)}

@router.post("/sessions/{session_id}/analyze")
async def start_analysis(session_id: str, background_tasks: BackgroundTasks, target_config: Optional[TargetConfiguration] = None):
    conn = get_db_connection()
    row = conn.execute("SELECT * FROM sessions WHERE session_id=?", (session_id,)).fetchone()
    if not row:
        conn.close()
        raise HTTPException(status_code=404, detail="Session not found.")

    if not row["video_metadata"]:
        conn.close()
        raise HTTPException(status_code=400, detail="Please upload drone video before initiating analysis.")

    # Use provided config or fetch existing from DB
    if not target_config:
        target_dict = json.loads(row["target_config"]) if row["target_config"] else {}
        target_config = TargetConfiguration(**target_dict)
    conn.close()

    background_tasks.add_task(AgenticLoopManager.execute_analysis, session_id, target_config)

    return {"status": "analysis_started", "session_id": session_id}

@router.post("/sessions/{session_id}/pause")
async def pause_analysis(session_id: str):
    AgenticLoopManager.update_session_status(session_id, "paused", 0.0, "paused")
    AgenticLoopManager.log_agent_event(session_id, "PAUSE", "Analysis session paused by operator.", "warning")
    return {"status": "paused"}

@router.post("/sessions/{session_id}/resume")
async def resume_analysis(session_id: str, background_tasks: BackgroundTasks):
    conn = get_db_connection()
    row = conn.execute("SELECT * FROM sessions WHERE session_id=?", (session_id,)).fetchone()
    conn.close()
    if not row:
        raise HTTPException(status_code=404, detail="Session not found.")

    target_config = TargetConfiguration(**json.loads(row["target_config"]))
    background_tasks.add_task(AgenticLoopManager.execute_analysis, session_id, target_config)
    AgenticLoopManager.log_agent_event(session_id, "RESUME", "Analysis session resumed by operator.", "info")
    return {"status": "resumed"}

@router.get("/sessions/{session_id}/status", response_model=SessionStatus)
async def get_session_status(session_id: str):
    conn = get_db_connection()
    row = conn.execute("SELECT * FROM sessions WHERE session_id=?", (session_id,)).fetchone()
    if not row:
        conn.close()
        raise HTTPException(status_code=404, detail="Session not found.")

    logs_rows = conn.execute("SELECT timestamp, step, message, level FROM agent_logs WHERE session_id=? ORDER BY id ASC", (session_id,)).fetchall()
    agent_logs = [AgentLogEntry(timestamp=l["timestamp"], step=l["step"], message=l["message"], level=l["level"]) for l in logs_rows]

    search_plan = None
    if row["search_plan"]:
        search_plan = json.loads(row["search_plan"])

    tracks_count = conn.execute("SELECT COUNT(*) as cnt FROM tracks WHERE session_id=?", (session_id,)).fetchone()["cnt"]
    dets_count = conn.execute("SELECT COUNT(*) as cnt FROM detections WHERE session_id=?", (session_id,)).fetchone()["cnt"]

    video_meta = None
    if row["video_metadata"]:
        video_meta = json.loads(row["video_metadata"])

    conn.close()

    return SessionStatus(
        session_id=session_id,
        status=row["status"],
        progress_percent=row["progress_percent"],
        current_stage=row["current_stage"],
        total_duration_seconds=video_meta["duration_seconds"] if video_meta else 0.0,
        people_detected_count=dets_count,
        unique_tracks_count=tracks_count,
        search_plan=search_plan,
        agent_logs=agent_logs
    )

@router.get("/sessions/{session_id}/tracks", response_model=List[TrackResult])
async def get_tracks(session_id: str):
    conn = get_db_connection()
    rows = conn.execute("SELECT * FROM tracks WHERE session_id=? ORDER BY final_ranking_score DESC", (session_id,)).fetchall()
    conn.close()

    results = []
    for row in rows:
        attrs_raw = json.loads(row["attributes"])
        attributes = {k: AttributeDetail(**v) for k, v in attrs_raw.items()}
        gps_raw = json.loads(row["gps_location"]) if row["gps_location"] else None

        results.append(TrackResult(
            session_id=session_id,
            track_id=row["track_id"],
            first_seen_seconds=row["first_seen_seconds"],
            last_seen_seconds=row["last_seen_seconds"],
            best_timestamp_seconds=row["best_timestamp_seconds"],
            classification=row["classification"],
            person_detection_confidence=row["person_detection_confidence"],
            appearance_similarity=row["appearance_similarity"],
            evidence_quality=row["evidence_quality"],
            final_ranking_score=row["final_ranking_score"],
            observations_analyzed=row["observations_analyzed"],
            attributes=attributes,
            matching_evidence=json.loads(row["matching_evidence"]),
            conflicting_evidence=json.loads(row["conflicting_evidence"]),
            unknown_attributes=json.loads(row["unknown_attributes"]),
            requires_human_review=bool(row["requires_human_review"]),
            explanation=row["explanation"],
            best_frame_path=row["best_frame_path"],
            cropped_samples=json.loads(row["cropped_samples"]),
            human_feedback=row["human_feedback"],
            human_notes=row["human_notes"],
            gps_location=GPSPoint(**gps_raw) if gps_raw else None
        ))
    return results

@router.get("/sessions/{session_id}/tracks/{track_id}", response_model=TrackResult)
async def get_track_detail(session_id: str, track_id: int):
    tracks = await get_tracks(session_id)
    for t in tracks:
        if t.track_id == track_id:
            return t
    raise HTTPException(status_code=404, detail="Track not found.")

@router.post("/sessions/{session_id}/tracks/{track_id}/feedback", response_model=TrackResult)
async def submit_human_feedback(session_id: str, track_id: int, feedback: HumanFeedbackInput):
    return AgenticLoopManager.apply_human_feedback(session_id, track_id, feedback)

@router.get("/sessions/{session_id}/events")
async def stream_session_events(session_id: str):
    """
    Server-Sent Events (SSE) stream delivering real-time agent updates to frontend.
    """
    async def event_generator():
        last_log_id = 0
        while True:
            conn = get_db_connection()
            sess_row = conn.execute("SELECT status, progress_percent, current_stage FROM sessions WHERE session_id=?", (session_id,)).fetchone()
            log_rows = conn.execute("SELECT id, timestamp, step, message, level FROM agent_logs WHERE session_id=? AND id > ? ORDER BY id ASC", (session_id, last_log_id)).fetchall()
            conn.close()

            if log_rows:
                for l in log_rows:
                    last_log_id = l["id"]
                    event_data = {
                        "type": "log",
                        "log": {
                            "timestamp": l["timestamp"],
                            "step": l["step"],
                            "message": l["message"],
                            "level": l["level"]
                        }
                    }
                    yield f"data: {json.dumps(event_data)}\n\n"

            if sess_row:
                status_data = {
                    "type": "status",
                    "status": sess_row["status"],
                    "progress_percent": sess_row["progress_percent"],
                    "current_stage": sess_row["current_stage"]
                }
                yield f"data: {json.dumps(status_data)}\n\n"

                if sess_row["status"] in ["completed", "error"]:
                    break

            await asyncio.sleep(0.8)

    return StreamingResponse(event_generator(), media_type="text/event-stream")
