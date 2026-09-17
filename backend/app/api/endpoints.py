import asyncio
import json
import os
import uuid
from pathlib import Path
from typing import List, Optional
from fastapi import APIRouter, UploadFile, File, HTTPException
from fastapi.responses import FileResponse, StreamingResponse
from starlette.concurrency import run_in_threadpool
from app.database import get_db_connection
from app.models.schemas import TargetConfiguration, SessionStatus, TrackResult, HumanFeedbackInput, AgentLogEntry, GPSPoint
from app.services.video_service import VideoService
from app.services.telemetry_service import TelemetryService
from app.services.agentic_loop import AgenticLoopManager, DATA_DIR, load_tracks
from app.services.analysis_worker import queue_analysis, control_analysis

router = APIRouter(prefix="/api")
MAX_VIDEO_BYTES = int(os.environ.get("AIEYE_MAX_VIDEO_BYTES", 4 * 1024**3))
MAX_TELEMETRY_BYTES = int(os.environ.get("AIEYE_MAX_TELEMETRY_BYTES", 10 * 1024**2))


def get_session(session_id):
    with get_db_connection() as conn:
        row = conn.execute("SELECT * FROM sessions WHERE session_id=?", (session_id,)).fetchone()
    if not row:
        raise HTTPException(404, "Session not found.")
    return row


def _reserve_upload(session_id):
    with get_db_connection() as conn:
        conn.execute("BEGIN IMMEDIATE")
        row = conn.execute("SELECT * FROM sessions WHERE session_id=?", (session_id,)).fetchone()
        if not row:
            raise HTTPException(404, "Session not found.")
        if row["status"] not in ("created", "uploaded"):
            raise HTTPException(409, "Uploads are allowed only before analysis. Create a new session to change its source footage.")
        conn.execute("UPDATE sessions SET status='uploading' WHERE session_id=?", (session_id,))
        return row["status"]


def _restore_upload(session_id, status):
    with get_db_connection() as conn:
        conn.execute("UPDATE sessions SET status=? WHERE session_id=? AND status='uploading'", (status,session_id))


async def _save_upload(session_id, upload, allowed_extensions, limit):
    # Client filenames are labels only; they never become filesystem paths.
    original_name = Path((upload.filename or "").replace("\\", "/")).name
    extension = Path(original_name).suffix.lower()
    if extension not in allowed_extensions:
        raise HTTPException(400, "Unsupported file format. Allowed: " + ", ".join(sorted(allowed_extensions)))
    folder = Path(DATA_DIR) / "uploads" / session_id
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / (uuid.uuid4().hex + extension)
    total = 0
    try:
        with path.open("xb") as output:
            while chunk := await upload.read(1024 * 1024):
                total += len(chunk)
                if total > limit:
                    raise HTTPException(413, f"File exceeds the configured {limit // (1024 * 1024)} MB limit.")
                output.write(chunk)
        if not total:
            raise HTTPException(400, "The uploaded file is empty.")
        return path, original_name
    except BaseException:
        path.unlink(missing_ok=True)
        raise
    finally:
        await upload.close()


@router.post("/sessions", response_model=SessionStatus)
def create_session(target_config: Optional[TargetConfiguration] = None):
    session_id = f"flight_{uuid.uuid4().hex}"
    target_config = target_config or TargetConfiguration(free_text_description="Locate a person.")
    with get_db_connection() as conn:
        conn.execute("INSERT INTO sessions(session_id,status,progress_percent,current_stage,target_config) VALUES (?,?,?,?,?)",
                     (session_id,"created",0.0,"created",json.dumps(target_config.model_dump(mode="json"))))
    AgenticLoopManager.log_agent_event(session_id,"INIT","Created a local analysis session.")
    return SessionStatus(session_id=session_id,status="created",current_stage="created")


@router.post("/sessions/{session_id}/video")
async def upload_video(session_id: str, file: UploadFile = File(...)):
    previous_status = _reserve_upload(session_id)
    path = None
    try:
        path, original_name = await _save_upload(session_id,file,{".mp4",".mov",".mkv"},MAX_VIDEO_BYTES)
        try:
            metadata = await run_in_threadpool(VideoService.inspect_video,str(path))
        except (ValueError, OSError) as error:
            raise HTTPException(400,str(error)) from error
        metadata.filename = original_name
        with get_db_connection() as conn:
            conn.execute("UPDATE sessions SET status='uploaded',video_metadata=? WHERE session_id=? AND status='uploading'",
                         (json.dumps(metadata.model_dump(mode="json")),session_id))
        AgenticLoopManager.log_agent_event(session_id,"UPLOAD",f"Video ready: {original_name} ({metadata.duration_seconds:.2f} seconds).")
        return {"status":"uploaded","video_metadata":metadata,"video_url":f"/uploads/{session_id}/{path.name}"}
    except BaseException:
        if path:
            path.unlink(missing_ok=True)
        _restore_upload(session_id,previous_status)
        raise


@router.post("/sessions/{session_id}/telemetry")
async def upload_telemetry(session_id: str, file: UploadFile = File(...)):
    previous_status = _reserve_upload(session_id)
    path = None
    try:
        path, original_name = await _save_upload(session_id,file,{".srt"},MAX_TELEMETRY_BYTES)
        try:
            points = await run_in_threadpool(TelemetryService.parse_srt_telemetry,str(path))
        except (ValueError,OSError,UnicodeError) as error:
            raise HTTPException(400,f"Invalid SRT telemetry: {error}") from error
        if not points:
            raise HTTPException(400,"SRT contains no supported timestamped GPS coordinates.")
        with get_db_connection() as conn:
            conn.execute("DELETE FROM telemetry WHERE session_id=?", (session_id,))
            conn.executemany("INSERT INTO telemetry(session_id,timestamp_seconds,latitude,longitude,altitude_m,relative_altitude_m) VALUES (?,?,?,?,?,?)",
                [(session_id,p.timestamp_seconds,p.latitude,p.longitude,p.altitude_m,p.relative_altitude_m) for p in points])
            conn.execute("UPDATE sessions SET has_telemetry=1,status=? WHERE session_id=? AND status='uploading'", (previous_status,session_id))
        AgenticLoopManager.log_agent_event(session_id,"TELEMETRY",f"Loaded {len(points)} drone position samples from {original_name}.")
        return {"status":"telemetry_uploaded","gps_points_count":len(points)}
    except BaseException:
        if path:
            path.unlink(missing_ok=True)
        _restore_upload(session_id,previous_status)
        raise


@router.get("/sessions/{session_id}/telemetry",response_model=List[GPSPoint])
def get_telemetry(session_id: str):
    get_session(session_id)
    with get_db_connection() as conn:
        rows = conn.execute("SELECT timestamp_seconds,latitude,longitude,altitude_m,relative_altitude_m FROM telemetry WHERE session_id=? ORDER BY timestamp_seconds",(session_id,)).fetchall()
    return [dict(row) for row in rows]


def _translate_queue_error(error):
    status = 404 if isinstance(error,LookupError) else (400 if isinstance(error,ValueError) else 409)
    raise HTTPException(status,str(error)) from error


@router.post("/sessions/{session_id}/analyze")
def start_analysis(session_id: str,target_config: Optional[TargetConfiguration] = None):
    try:
        run_id = queue_analysis(session_id,target_config)
    except (LookupError,ValueError,RuntimeError) as error:
        _translate_queue_error(error)
    return {"status":"queued","session_id":session_id,"run_id":run_id}


def _control(session_id,action):
    try:
        status = control_analysis(session_id,action)
    except (LookupError,RuntimeError) as error:
        _translate_queue_error(error)
    AgenticLoopManager.log_agent_event(session_id,action.upper(),f"Operator requested {action}. Processing checks this between frames and tracks.")
    return {"status":status}


@router.post("/sessions/{session_id}/pause")
def pause_analysis(session_id: str):
    return _control(session_id,"pause")


@router.post("/sessions/{session_id}/resume")
def resume_analysis(session_id: str):
    return _control(session_id,"resume")


@router.post("/sessions/{session_id}/cancel")
def cancel_analysis(session_id: str):
    return _control(session_id,"cancel")


@router.get("/sessions/{session_id}/status",response_model=SessionStatus)
def get_session_status(session_id: str):
    row = get_session(session_id)
    with get_db_connection() as conn:
        logs = conn.execute("SELECT timestamp,step,message,level FROM agent_logs WHERE session_id=? ORDER BY id",(session_id,)).fetchall()
        tracks = conn.execute("SELECT COUNT(*) FROM tracks WHERE session_id=?",(session_id,)).fetchone()[0]
        detections = conn.execute("SELECT COUNT(*) FROM detections WHERE session_id=? AND (run_id=? OR (? IS NULL AND run_id IS NULL))",(session_id,row["run_id"],row["run_id"])).fetchone()[0]
        samples = conn.execute("SELECT COUNT(*) planned,SUM(status='sampled') sampled,MAX(CASE WHEN status='sampled' THEN timestamp_seconds END) latest FROM frame_samples WHERE run_id=?",(row["run_id"],)).fetchone()
    video = json.loads(row["video_metadata"]) if row["video_metadata"] else {}
    return SessionStatus(session_id=session_id,status=row["status"],progress_percent=row["progress_percent"],
        current_stage=row["current_stage"],total_duration_seconds=video.get("duration_seconds",0),
        current_timestamp_seconds=samples["latest"] or 0,people_detected_count=detections,unique_tracks_count=tracks,
        search_plan=json.loads(row["search_plan"]) if row["search_plan"] else None,
        agent_logs=[AgentLogEntry(**dict(item)) for item in logs],run_id=row["run_id"],
        frames_sampled=samples["sampled"] or 0,frames_planned=samples["planned"] or 0,error_message=row["error_message"])


@router.get("/sessions/{session_id}/tracks",response_model=List[TrackResult])
def get_tracks(session_id: str):
    get_session(session_id)
    return load_tracks(session_id)


@router.get("/sessions/{session_id}/tracks/{track_id}",response_model=TrackResult)
def get_track_detail(session_id: str,track_id: int):
    for track in get_tracks(session_id):
        if track.track_id == track_id:
            return track
    raise HTTPException(404,"Track not found.")


@router.post("/sessions/{session_id}/tracks/{track_id}/feedback",response_model=TrackResult)
def submit_human_feedback(session_id: str,track_id: int,feedback: HumanFeedbackInput):
    try:
        return AgenticLoopManager.apply_human_feedback(session_id,track_id,feedback)
    except (LookupError,RuntimeError) as error:
        _translate_queue_error(error)


@router.get("/sessions/{session_id}/report")
def get_report(session_id: str):
    row = get_session(session_id)
    if row["status"] != "completed":
        raise HTTPException(409,"A completed analysis is required before exporting a report.")
    AgenticLoopManager.regenerate_report(session_id)
    return FileResponse(os.path.join(DATA_DIR,"reports",f"report_{session_id}.html"),media_type="text/html",
                        headers={"Cache-Control":"no-store"})


@router.get("/sessions/{session_id}/detections")
def get_detections(session_id: str):
    row = get_session(session_id)
    with get_db_connection() as conn:
        detections = conn.execute("SELECT * FROM detections WHERE session_id=? AND run_id IS ? ORDER BY frame_idx",(session_id,row["run_id"])).fetchall()
    return [json.loads(item["payload"]) if item["payload"] else {**dict(item),"bbox":json.loads(item["bbox"])} for item in detections]


@router.get("/sessions/{session_id}/coverage")
def get_coverage(session_id: str):
    row = get_session(session_id)
    with get_db_connection() as conn:
        samples = conn.execute("SELECT frame_idx,timestamp_seconds,stage,status FROM frame_samples WHERE run_id=? ORDER BY frame_idx",(row["run_id"],)).fetchall()
    return {"run_id":row["run_id"],"samples":[dict(item) for item in samples]}


@router.get("/sessions/{session_id}/events")
async def stream_session_events(session_id: str):
    get_session(session_id)
    async def event_generator():
        last_log_id = 0
        while True:
            with get_db_connection() as conn:
                session = conn.execute("SELECT status,progress_percent,current_stage,error_message FROM sessions WHERE session_id=?",(session_id,)).fetchone()
                logs = conn.execute("SELECT id,timestamp,step,message,level FROM agent_logs WHERE session_id=? AND id>? ORDER BY id",(session_id,last_log_id)).fetchall()
            for item in logs:
                last_log_id = item["id"]
                yield "data: " + json.dumps({"type":"log","log":{key:item[key] for key in ("timestamp","step","message","level")}}) + "\n\n"
            if not session:
                break
            yield "data: " + json.dumps({"type":"status",**dict(session)}) + "\n\n"
            if session["status"] in ("completed","error","cancelled"):
                break
            await asyncio.sleep(0.8)
    return StreamingResponse(event_generator(),media_type="text/event-stream",headers={"Cache-Control":"no-cache","X-Accel-Buffering":"no"})
