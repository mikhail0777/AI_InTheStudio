import asyncio
import json
import os
import shutil
import uuid
import hashlib
from pathlib import Path
from typing import List, Optional
from fastapi import APIRouter, UploadFile, File, HTTPException, Request, Response
from pydantic import BaseModel, Field
from fastapi.responses import FileResponse, StreamingResponse
from starlette.concurrency import run_in_threadpool
from app.database import get_db_connection
from app.models.schemas import TargetConfiguration, SessionStatus, TrackResult, HumanFeedbackInput, SightingReviewInput, AgentLogEntry, GPSPoint
from app.models.open_vocabulary import SearchResult
from app.services.video_service import VideoService
from app.services.telemetry_service import TelemetryService
from app.services.agentic_loop import AgenticLoopManager, DATA_DIR, load_tracks
from app.services.analysis_worker import queue_analysis, queue_proxy, control_analysis
from app.services.generic_search import OpenVocabularySearchManager, load_search_results
from app.services.vehicle_sightings import list_sightings
from app.services import governance, vehicle_records, vehicle_events
from app.services import condition_incidents

router = APIRouter(prefix="/api")
MAX_VIDEO_BYTES = int(os.environ.get("AIEYE_MAX_VIDEO_BYTES", 4 * 1024**3))
MAX_TELEMETRY_BYTES = int(os.environ.get("AIEYE_MAX_TELEMETRY_BYTES", 10 * 1024**2))

class BootstrapInput(BaseModel):
    dealership_name: str = Field(min_length=1,max_length=200)
    email: str = Field(min_length=3,max_length=320)
    display_name: str = Field(min_length=1,max_length=120)
    password: str = Field(min_length=12,max_length=256)
class LoginInput(BaseModel):
    email: str
    password: str
class VehicleInput(BaseModel):
    plate: str|None=None; vin: str|None=None; stock_number: str|None=None; make: str|None=None; model: str|None=None
    year: int|None=None; color: str|None=None; body_type: str|None=None; status: str="active"; notes: str|None=None; reason: str|None=None
class AliasInput(BaseModel):
    plate: str; valid_from: str|None=None; valid_to: str|None=None; reason: str|None=None
class LinkInput(BaseModel):
    vehicle_id: str; reason: str
class ReasonInput(BaseModel):
    reason: str
class CameraInput(BaseModel):
    name: str; role: str="unknown"; location: str|None=None; timezone: str="UTC"
class BoundaryInput(BaseModel):
    name: str = Field(min_length=1,max_length=120)
    boundary_type: str; x1: float; y1: float; x2: float; y2: float; travel_direction: str
    min_vehicle_width: float=.08; min_vehicle_height: float=.08; min_visible_fraction: float=.65
class TrackObservationInput(BaseModel):
    timestamp_seconds: float = Field(ge=0); center_x: float; center_y: float; width: float; height: float
    visible_fraction: float=1; frame_reference: str|None=None
    vehicle_crop_reference: str|None=None; plate_crop_reference: str|None=None
class CrossingEventInput(BaseModel):
    boundary_id: str; track_id: str; recorded_start_at: str; session_id: str|None=None
    recording_reference: str|None=None; consensus_plate: str|None=None
    plate_match_state: str="uncertain"; observations: list[TrackObservationInput]
    best_vehicle_crop: str|None=None; best_plate_crop: str|None=None
    ocr_candidates: list[dict]=Field(default_factory=list)
    evidence: dict=Field(default_factory=dict); model_manifest: dict=Field(default_factory=dict)
class RetentionInput(BaseModel):
    source_video_days: int; derived_media_days: int; sightings_days: int; audit_days: int; inspections_days:int=1095; incidents_days:int=2555
class UserInput(BaseModel):
    email: str; display_name: str; role: str; password: str = Field(min_length=12,max_length=256)
class InspectionInput(BaseModel):
    vehicle_id:str; inspection_type:str; camera_id:str|None=None; device_label:str|None=None; captured_at:str|None=None; notes:str|None=None
class AnnotationInput(BaseModel):
    x:float; y:float; width:float; height:float; damage_type:str; severity:str; assessment:str; notes:str|None=None
class IncidentInput(BaseModel):
    vehicle_id:str|None=None; title:str=Field(min_length=1,max_length=200); summary:str|None=None; priority:str="normal"
class EvidenceInput(BaseModel):
    evidence_type:str; entity_id:str; note:str|None=None
class NoteInput(BaseModel): note:str
class DecisionInput(BaseModel): action:str; reason:str
class HoldInput(BaseModel): reason:str

def _user(request:Request):
    user=getattr(request.state,"user",None)
    if not user: raise HTTPException(401,"Authentication required.")
    return user

def _optional_user(request:Request):
    return getattr(request.state,"user",None)

def _session_cookie(response,token):
    response.set_cookie("lottrace_session",token,max_age=43200,httponly=True,samesite="strict",secure=os.environ.get("AIEYE_SECURE_COOKIES")=="1",path="/")

@router.get("/auth/status")
def auth_status(request:Request):
    return {"configured":governance.configured(),"user":governance.authenticate(request.cookies.get("lottrace_session"))}

@router.post("/auth/bootstrap")
def auth_bootstrap(values:BootstrapInput,response:Response):
    try: token,user=governance.bootstrap(**values.model_dump())
    except (ValueError,RuntimeError) as error: raise HTTPException(409 if isinstance(error,RuntimeError) else 400,str(error)) from error
    _session_cookie(response,token); return {"user":user}

@router.post("/auth/login")
def auth_login(values:LoginInput,response:Response):
    try: token,user=governance.create_session(values.email,values.password)
    except ValueError as error: raise HTTPException(401,str(error)) from error
    _session_cookie(response,token); return {"user":user}

@router.post("/auth/logout")
def auth_logout(request:Request,response:Response):
    governance.logout(request.cookies.get("lottrace_session")); response.delete_cookie("lottrace_session",path="/"); return {"status":"logged_out"}


def get_session(session_id):
    with get_db_connection() as conn:
        row = conn.execute("SELECT * FROM sessions WHERE session_id=?", (session_id,)).fetchone()
    if not row:
        raise HTTPException(404, "Session not found.")
    return row


def _remove_session_path(path: Path):
    root = Path(DATA_DIR).resolve()
    target = path.resolve()
    if target == root or root not in target.parents:
        raise RuntimeError("Refusing to remove a path outside the application data directory.")
    if target.is_dir():
        shutil.rmtree(target)
    elif target.exists():
        target.unlink()


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
def create_session(request:Request,target_config: Optional[TargetConfiguration] = None):
    session_id = f"case_{uuid.uuid4().hex}"
    # Preserve the legacy API default for existing automation; the dealership UI always
    # supplies an explicit vehicle query.
    if target_config is None:
        target_config = TargetConfiguration(free_text_description="Locate a person.")
    elif not target_config.free_text_description.strip():
        target_config = target_config.model_copy(update={"free_text_description": "Locate a person."})
    with get_db_connection() as conn:
        user=_optional_user(request)
        conn.execute("INSERT INTO sessions(session_id,status,progress_percent,current_stage,target_config,dealership_id) VALUES (?,?,?,?,?,?)",
                     (session_id,"created",0.0,"created",json.dumps(target_config.model_dump(mode="json")),user["dealership_id"] if user else None))
    AgenticLoopManager.log_agent_event(session_id,"INIT","Created a local dealership video investigation.")
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
        original_url = f"/uploads/{session_id}/{path.name}"
        playback_url = original_url
        proxy_generated = False
        if not VideoService.is_browser_compatible(str(path), metadata.codec):
            proxy_path = path.parent / "playback_h264.mp4"
            playback_url = None
            proxy_generated = True
        with get_db_connection() as conn:
            conn.execute("UPDATE sessions SET status='uploaded',video_metadata=?,playback_url=?,proxy_status=?,proxy_error=NULL WHERE session_id=? AND status='uploading'",
                         (json.dumps(metadata.model_dump(mode="json")),playback_url,
                          "queued" if proxy_generated else "ready",session_id))
        if proxy_generated:
            queue_proxy(session_id, str(path), str(proxy_path))
        AgenticLoopManager.log_agent_event(session_id,"UPLOAD",f"Video ready: {original_name} ({metadata.duration_seconds:.2f} seconds).")
        return {"status":"uploaded","video_metadata":metadata,"video_url":playback_url,
                "playback_url":playback_url,"original_video_url":original_url,
                "proxy_generated":proxy_generated}
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
    target = json.loads(row["target_config"] or "{}")
    with get_db_connection() as conn:
        logs = conn.execute("SELECT timestamp,step,message,level FROM agent_logs WHERE session_id=? ORDER BY id",(session_id,)).fetchall()
        tracks = conn.execute("SELECT COUNT(*) FROM tracks WHERE session_id=?",(session_id,)).fetchone()[0]
        results_count = conn.execute("SELECT COUNT(*) FROM search_results WHERE search_id=?", (row["search_id"],)).fetchone()[0] if row["search_id"] else 0
        search = conn.execute("SELECT processing_mode,metrics_json FROM searches WHERE search_id=?", (row["search_id"],)).fetchone() if row["search_id"] else None
        detections = conn.execute("SELECT COUNT(*) FROM detections WHERE session_id=? AND (run_id=? OR (? IS NULL AND run_id IS NULL))",(session_id,row["run_id"],row["run_id"])).fetchone()[0]
        samples = conn.execute("SELECT COUNT(*) planned,SUM(status='sampled') sampled,MAX(CASE WHEN status='sampled' THEN timestamp_seconds END) latest FROM frame_samples WHERE run_id=?",(row["run_id"],)).fetchone()
    video = json.loads(row["video_metadata"]) if row["video_metadata"] else {}
    return SessionStatus(session_id=session_id,status=row["status"],progress_percent=row["progress_percent"],
        current_stage=row["current_stage"],total_duration_seconds=video.get("duration_seconds",0),
        current_timestamp_seconds=samples["latest"] or 0,people_detected_count=detections,unique_tracks_count=tracks,
        search_plan=json.loads(row["search_plan"]) if row["search_plan"] else None,
        search_query=json.loads(row["search_query"]) if row["search_query"] else None,
        processing_mode=search["processing_mode"] if search else target.get("processing_mode"),
        stage_timings=(json.loads(search["metrics_json"]).get("stage_timings", {})
                       if search and search["metrics_json"] else {}),
        results_count=results_count,
        agent_logs=[AgentLogEntry(**dict(item)) for item in logs],run_id=row["run_id"],
        frames_sampled=samples["sampled"] or 0,frames_planned=samples["planned"] or 0,
        error_message=row["error_message"],playback_url=row["playback_url"],
        proxy_status=row["proxy_status"],proxy_error=row["proxy_error"])


@router.delete("/sessions/{session_id}")
def delete_session(session_id: str):
    row = get_session(session_id)
    if row["status"] in ("queued", "analyzing", "paused", "uploading"):
        raise HTTPException(409, "Pause or cancel the active investigation before deleting it.")
    with get_db_connection() as conn:
        conn.execute("BEGIN IMMEDIATE")
        conn.execute("DELETE FROM proxy_jobs WHERE session_id=?", (session_id,))
        conn.execute("DELETE FROM sighting_revisions WHERE sighting_id IN (SELECT sighting_id FROM vehicle_sightings WHERE session_id=?)", (session_id,))
        conn.execute("DELETE FROM vehicle_sightings WHERE session_id=?", (session_id,))
        search_ids = [item[0] for item in conn.execute(
            "SELECT search_id FROM searches WHERE session_id=?", (session_id,),
        ).fetchall()]
        run_ids = [item[0] for item in conn.execute(
            "SELECT run_id FROM analysis_runs WHERE session_id=?", (session_id,),
        ).fetchall()]
        for search_id in search_ids:
            conn.execute("DELETE FROM search_candidates WHERE search_id=?", (search_id,))
            conn.execute("DELETE FROM search_results WHERE search_id=?", (search_id,))
        if search_ids:
            conn.execute("DELETE FROM searches WHERE session_id=?", (session_id,))
        for run_id in run_ids:
            conn.execute("DELETE FROM frame_samples WHERE run_id=?", (run_id,))
        conn.execute("DELETE FROM analysis_runs WHERE session_id=?", (session_id,))
        for table in ("tracks", "detections", "telemetry", "agent_logs"):
            conn.execute(f"DELETE FROM {table} WHERE session_id=?", (session_id,))
        conn.execute("DELETE FROM sessions WHERE session_id=?", (session_id,))
    data_root = Path(DATA_DIR)
    for folder in ("uploads", "crops", "evidence"):
        _remove_session_path(data_root / folder / session_id)
    _remove_session_path(data_root / "reports" / f"report_{session_id}.html")
    return {"status": "deleted", "session_id": session_id}


@router.get("/sessions/{session_id}/tracks",response_model=List[TrackResult])
def get_tracks(session_id: str):
    get_session(session_id)
    return load_tracks(session_id)


@router.get("/sessions/{session_id}/results",response_model=List[SearchResult])
def get_results(session_id: str):
    get_session(session_id)
    return load_search_results(session_id)


@router.post("/sessions/{session_id}/results/{result_id}/feedback",response_model=SearchResult)
def submit_result_feedback(session_id: str,result_id: str,feedback: HumanFeedbackInput):
    try:
        result = OpenVocabularySearchManager.apply_feedback(session_id,result_id,feedback)
        from app.services.vehicle_sightings import review_sighting
        action = {"confirmed": "confirm", "rejected": "reject", "needs_research": "reopen"}[feedback.status]
        try:
            review_sighting(result_id, SightingReviewInput(action=action))
            if feedback.notes:
                review_sighting(result_id, SightingReviewInput(action="note", note=feedback.notes))
        except LookupError:
            pass  # Legacy person-search results do not have dealership sighting rows.
        return result
    except (LookupError,RuntimeError,ValueError) as error:
        _translate_queue_error(error)


@router.get("/vehicle-sightings")
def get_vehicle_sightings(request:Request,plate: Optional[str] = None, make: Optional[str] = None,
                          model: Optional[str] = None, year: Optional[int] = None,
                          color: Optional[str] = None, body_type: Optional[str] = None,
                          camera: Optional[str] = None, date_from: Optional[str] = None,
                          date_to: Optional[str] = None, after_hours_only: bool = False,
                          limit: int = 200):
    """Search the persistent dealership sighting ledger across recordings."""
    return list_sightings(
        plate=plate, make=make, model=model, year=year, color=color,
        body_type=body_type, camera=camera, date_from=date_from, date_to=date_to,
        after_hours_only=after_hours_only, limit=limit,
        dealership_id=(_optional_user(request) or {}).get("dealership_id"),
    )


@router.post("/vehicle-sightings/{sighting_id}/review")
def review_vehicle_sighting(sighting_id: str, review: SightingReviewInput,request:Request):
    from app.services.vehicle_sightings import review_sighting
    try:
        return review_sighting(sighting_id, review,_optional_user(request))
    except LookupError as error:
        raise HTTPException(404, str(error)) from error
    except ValueError as error:
        raise HTTPException(400, str(error)) from error


@router.get("/vehicle-sightings/{sighting_id}/revisions")
def get_sighting_revisions(sighting_id: str):
    from app.services.vehicle_sightings import list_revisions
    try:
        return list_revisions(sighting_id)
    except LookupError as error:
        raise HTTPException(404, str(error)) from error

@router.get("/vehicles")
def vehicles(request:Request): return vehicle_records.list_vehicles(_user(request))

@router.post("/vehicles")
def create_vehicle(values:VehicleInput,request:Request):
    try:return vehicle_records.save_vehicle(_user(request),values.model_dump())
    except ValueError as error:raise HTTPException(400,str(error)) from error

@router.get("/vehicles/{vehicle_id}")
def vehicle(vehicle_id:str,request:Request):
    try:return vehicle_records.get_vehicle(_user(request),vehicle_id)
    except LookupError as error:raise HTTPException(404,str(error)) from error

@router.patch("/vehicles/{vehicle_id}")
def update_vehicle(vehicle_id:str,values:VehicleInput,request:Request):
    try:return vehicle_records.save_vehicle(_user(request),values.model_dump(exclude_unset=True),vehicle_id)
    except LookupError as error:raise HTTPException(404,str(error)) from error
    except ValueError as error:raise HTTPException(400,str(error)) from error

@router.post("/vehicles/{vehicle_id}/plate-aliases")
def create_plate_alias(vehicle_id:str,values:AliasInput,request:Request):
    try:return vehicle_records.add_alias(_user(request),vehicle_id,values.model_dump())
    except LookupError as error:raise HTTPException(404,str(error)) from error
    except ValueError as error:raise HTTPException(400,str(error)) from error

@router.get("/vehicles/{vehicle_id}/timeline")
def vehicle_timeline(vehicle_id:str,request:Request):
    try:return vehicle_records.timeline(_user(request),vehicle_id)
    except LookupError as error:raise HTTPException(404,str(error)) from error

@router.post("/vehicle-sightings/{sighting_id}/link")
def link_vehicle_sighting(sighting_id:str,values:LinkInput,request:Request):
    try:return vehicle_records.link_sighting(_user(request),sighting_id,values.vehicle_id,values.reason)
    except LookupError as error:raise HTTPException(404,str(error)) from error
    except ValueError as error:raise HTTPException(400,str(error)) from error

@router.delete("/vehicle-sightings/{sighting_id}/link")
def unlink_vehicle_sighting(sighting_id:str,values:ReasonInput,request:Request):
    try:vehicle_records.unlink_sighting(_user(request),sighting_id,values.reason);return {"status":"unlinked"}
    except LookupError as error:raise HTTPException(404,str(error)) from error
    except ValueError as error:raise HTTPException(400,str(error)) from error

@router.get("/cameras")
def cameras(request:Request):return vehicle_records.list_cameras(_user(request))

@router.post("/cameras")
def create_camera(values:CameraInput,request:Request):return vehicle_records.create_camera(_user(request),values.model_dump())

@router.get("/camera-boundaries")
def camera_boundaries(request:Request,camera_id:str|None=None):
    return vehicle_events.list_boundaries(_user(request),camera_id)

@router.post("/cameras/{camera_id}/boundaries")
def create_camera_boundary(camera_id:str,values:BoundaryInput,request:Request):
    try:return vehicle_events.create_boundary(_user(request),camera_id,values.model_dump())
    except LookupError as error:raise HTTPException(404,str(error)) from error
    except ValueError as error:raise HTTPException(400,str(error)) from error

@router.get("/vehicle-events")
def vehicle_event_ledger(request:Request,review_state:str|None=None,vehicle_id:str|None=None,limit:int=200):
    return vehicle_events.list_events(_user(request),review_state,vehicle_id,limit)

@router.get("/vehicle-events/{event_id}")
def vehicle_event(event_id:str,request:Request):
    try:return vehicle_events.get_event(_user(request),event_id)
    except LookupError as error:raise HTTPException(404,str(error)) from error

@router.post("/vehicle-events/from-track")
def create_vehicle_event(values:CrossingEventInput,request:Request):
    try:return vehicle_events.create_crossing_event(_user(request),values.model_dump())
    except LookupError as error:raise HTTPException(404,str(error)) from error
    except ValueError as error:raise HTTPException(400,str(error)) from error

@router.get("/retention")
def retention(request:Request):return vehicle_records.get_retention(_user(request))

@router.put("/retention")
def update_retention(values:RetentionInput,request:Request):
    try:return vehicle_records.update_retention(_user(request),values.model_dump())
    except ValueError as error:raise HTTPException(400,str(error)) from error

@router.post("/retention/apply")
def apply_retention(request:Request):
    try:return condition_incidents.apply_retention(_user(request),DATA_DIR)
    except (LookupError,PermissionError) as error:_condition_error(error)

@router.get("/audit-events")
def audit_events(request:Request,limit:int=200):return vehicle_records.list_audit(_user(request),limit)

@router.get("/users")
def users(request:Request):return governance.list_users(_user(request))

@router.post("/users")
def create_user(values:UserInput,request:Request):
    user=_user(request)
    if user["role"]!="administrator":raise HTTPException(403,"Administrator role required.")
    try:return governance.create_user(user,**values.model_dump())
    except ValueError as error:raise HTTPException(400,str(error)) from error

def _condition_error(error):
    if isinstance(error,LookupError): raise HTTPException(404,str(error)) from error
    if isinstance(error,PermissionError): raise HTTPException(403,str(error)) from error
    raise HTTPException(400,str(error)) from error

def _public_inspection(value):
    result=dict(value)
    for media in result.get("media",[]):
        path=Path(media.pop("storage_path")); root=(Path(DATA_DIR)/"evidence").resolve()
        try: relative=path.resolve().relative_to(root)
        except ValueError: media["evidence_url"]=None
        else: media["evidence_url"]="/evidence/"+relative.as_posix()
    return result

@router.get("/inspections")
def inspections(request:Request,vehicle_id:str|None=None):return condition_incidents.list_inspections(_user(request),vehicle_id)

@router.post("/inspections")
def create_inspection(values:InspectionInput,request:Request):
    try:return condition_incidents.create_inspection(_user(request),values.model_dump())
    except (LookupError,ValueError) as error:_condition_error(error)

@router.get("/inspections/{inspection_id}")
def inspection(inspection_id:str,request:Request):
    try:return _public_inspection(condition_incidents.get_inspection(_user(request),inspection_id))
    except LookupError as error:_condition_error(error)

@router.post("/inspections/{inspection_id}/media")
async def upload_inspection_media(inspection_id:str,request:Request,viewpoint:str,file:UploadFile=File(...)):
    extension=Path((file.filename or "").replace("\\","/")).suffix.lower()
    if extension not in (".jpg",".jpeg",".png",".webp"):raise HTTPException(400,"Inspection media must be JPG, PNG, or WebP.")
    folder=Path(DATA_DIR)/"evidence"/"inspections"/inspection_id;folder.mkdir(parents=True,exist_ok=True);path=folder/(uuid.uuid4().hex+extension);size=0;digest=hashlib.sha256()
    try:
        with path.open("xb") as output:
            while chunk:=await file.read(1024*1024):
                size+=len(chunk)
                if size>25*1024*1024:raise HTTPException(413,"Inspection image exceeds 25 MB.")
                digest.update(chunk);output.write(chunk)
        import cv2
        image=await run_in_threadpool(cv2.imread,str(path))
        if image is None:raise HTTPException(400,"The uploaded file is not a readable image.")
        height,width=image.shape[:2]
        result=condition_incidents.register_media(_user(request),inspection_id,{"viewpoint":viewpoint,"source_filename":Path(file.filename or "image").name,"storage_path":str(path.resolve()),"mime_type":file.content_type or "application/octet-stream","sha256":digest.hexdigest(),"width":width,"height":height})
        return _public_inspection({"media":[result]})["media"][0]
    except BaseException:
        path.unlink(missing_ok=True);raise
    finally:await file.close()

@router.post("/inspections/{inspection_id}/complete")
def complete_inspection(inspection_id:str,request:Request):
    try:return _public_inspection(condition_incidents.complete_inspection(_user(request),inspection_id))
    except (LookupError,ValueError) as error:_condition_error(error)

@router.post("/inspection-media/{media_id}/annotations")
def create_annotation(media_id:str,values:AnnotationInput,request:Request):
    try:return condition_incidents.annotate(_user(request),media_id,values.model_dump())
    except (LookupError,ValueError) as error:_condition_error(error)

@router.get("/incidents")
def incidents(request:Request):return condition_incidents.list_incidents(_user(request))

@router.post("/incidents")
def create_incident(values:IncidentInput,request:Request):
    try:return condition_incidents.create_incident(_user(request),values.model_dump())
    except (LookupError,ValueError) as error:_condition_error(error)

@router.get("/incidents/{incident_id}")
def incident(incident_id:str,request:Request):
    try:return condition_incidents.get_incident(_user(request),incident_id)
    except LookupError as error:_condition_error(error)

@router.post("/incidents/{incident_id}/evidence")
def add_incident_evidence(incident_id:str,values:EvidenceInput,request:Request):
    try:return condition_incidents.add_evidence(_user(request),incident_id,values.model_dump())
    except (LookupError,ValueError) as error:_condition_error(error)

@router.post("/incidents/{incident_id}/notes")
def add_incident_note(incident_id:str,values:NoteInput,request:Request):
    try:return condition_incidents.add_note(_user(request),incident_id,values.note)
    except (LookupError,ValueError) as error:_condition_error(error)

@router.post("/incidents/{incident_id}/decision")
def decide_incident(incident_id:str,values:DecisionInput,request:Request):
    try:return condition_incidents.decision(_user(request),incident_id,values.action,values.reason)
    except (LookupError,ValueError,PermissionError) as error:_condition_error(error)

@router.post("/incidents/{incident_id}/holds")
def hold_incident(incident_id:str,values:HoldInput,request:Request):
    try:return condition_incidents.place_hold(_user(request),incident_id,values.reason)
    except (LookupError,ValueError,PermissionError) as error:_condition_error(error)

@router.post("/incidents/{incident_id}/attachments")
async def upload_incident_attachment(incident_id:str,request:Request,file:UploadFile=File(...)):
    filename=Path((file.filename or "").replace("\\","/")).name;extension=Path(filename).suffix.lower()
    if extension not in (".jpg",".jpeg",".png",".webp",".pdf",".mp4",".mov",".txt"):raise HTTPException(400,"Unsupported attachment type.")
    folder=Path(DATA_DIR)/"evidence"/"incidents"/incident_id;folder.mkdir(parents=True,exist_ok=True);path=folder/(uuid.uuid4().hex+extension);size=0;digest=hashlib.sha256()
    try:
        with path.open("xb") as output:
            while chunk:=await file.read(1024*1024):
                size+=len(chunk)
                if size>100*1024*1024:raise HTTPException(413,"Attachment exceeds 100 MB.")
                digest.update(chunk);output.write(chunk)
        if not size:raise HTTPException(400,"Attachment is empty.")
        return condition_incidents.register_attachment(_user(request),incident_id,{"source_filename":filename,"storage_path":str(path.resolve()),"mime_type":file.content_type or "application/octet-stream","sha256":digest.hexdigest(),"size_bytes":size})
    except BaseException:path.unlink(missing_ok=True);raise
    finally:await file.close()

@router.post("/incidents/{incident_id}/exports")
def export_incident(incident_id:str,request:Request):
    try:result=condition_incidents.export_incident(_user(request),incident_id,DATA_DIR)
    except (LookupError,ValueError) as error:_condition_error(error)
    return FileResponse(result["path"],media_type="application/zip",filename=f"lottrace-{incident_id}.zip",headers={"X-Manifest-SHA256":result["manifest_sha256"],"X-Archive-SHA256":result["archive_sha256"],"Cache-Control":"no-store"})


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
    with get_db_connection() as conn:
        has_legacy_tracks = bool(conn.execute("SELECT 1 FROM tracks WHERE session_id=? LIMIT 1", (session_id,)).fetchone())
    if row["search_id"] and not has_legacy_tracks:
        from app.services.generic_report import generate_generic_report
        generate_generic_report(session_id)
    else:
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
