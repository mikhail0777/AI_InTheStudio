"""Deterministic, auditable video processing executed by the local worker."""
import json
import os
from datetime import datetime
from typing import Callable
import cv2
from app.database import DB_DIR, get_db_connection
from app.models.schemas import TargetConfiguration, TrackResult, VideoMetadata, GPSPoint
from app.services.video_service import VideoService
from app.services.search_agent import SearchPlanAgent
from app.services.detector import PersonDetector
from app.services.tracker import PersonTracker
from app.services.appearance_analyzer import AppearanceAnalyzer
from app.services.telemetry_service import TelemetryService
from app.services.report_generator import ReportGenerator

DATA_DIR = DB_DIR


def load_tracks(session_id):
    with get_db_connection() as conn:
        rows = conn.execute("SELECT * FROM tracks WHERE session_id=? ORDER BY final_ranking_score DESC", (session_id,)).fetchall()
    results = []
    json_fields = ("attributes", "matching_evidence", "conflicting_evidence", "unknown_attributes", "cropped_samples", "gps_location")
    for row in rows:
        # Payload preserves new provenance fields while columns retain compatibility.
        data = json.loads(row["payload"]) if row["payload"] else {}
        data.update({key: row[key] for key in row.keys() if key != "payload"})
        for key in json_fields:
            data[key] = json.loads(row[key]) if row[key] else (None if key == "gps_location" else ({} if key == "attributes" else []))
        data["requires_human_review"] = bool(row["requires_human_review"])
        results.append(TrackResult(**data))
    return results


class AgenticLoopManager:
    @staticmethod
    def log_agent_event(session_id, step, message, level="info"):
        with get_db_connection() as conn:
            conn.execute("INSERT INTO agent_logs(session_id,timestamp,step,message,level) VALUES (?,?,?,?,?)",
                         (session_id, datetime.now().strftime("%H:%M:%S"), step, message, level))

    @staticmethod
    def update_session_status(session_id, status, progress, stage, people_count=0, tracks_count=0):
        with get_db_connection() as conn:
            # Processing must never undo a pause or cancellation requested by HTTP.
            conn.execute("UPDATE sessions SET progress_percent=?,current_stage=? WHERE session_id=? AND status='analyzing'",
                         (round(progress, 1), stage, session_id))

    @staticmethod
    def _save_detections(session_id, run_id, frame_idx, detections):
        with get_db_connection() as conn:
            for det in detections:
                conn.execute("""INSERT INTO detections(detection_id,session_id,frame_idx,timestamp_seconds,bbox,
                    confidence,crop_path,quality_score,run_id,payload) VALUES (?,?,?,?,?,?,?,?,?,?)""",
                    (det.detection_id, session_id, det.frame_idx, det.timestamp_seconds, json.dumps(det.bbox),
                     det.confidence, det.crop_path, det.quality_score, run_id, json.dumps(det.dict())))
            conn.execute("UPDATE frame_samples SET status='sampled' WHERE run_id=? AND frame_idx=?", (run_id, frame_idx))

    @classmethod
    def _scan(cls, session_id, run_id, video_info, indices, stage, detector, min_confidence,
              checkpoint, all_detections, progress_start, progress_span):
        indices = sorted(set(indices))
        if not indices:
            return
        with get_db_connection() as conn:
            conn.executemany("INSERT OR IGNORE INTO frame_samples(run_id,frame_idx,timestamp_seconds,stage) VALUES (?,?,?,?)",
                             [(run_id, index, index / video_info.fps, stage) for index in indices])
        targets = set(indices)
        cap = cv2.VideoCapture(video_info.filepath)
        processed = set()
        try:
            if not cap.isOpened():
                raise ValueError("The uploaded video can no longer be opened.")
            index = 0
            while index <= indices[-1]:
                if index % 25 == 0 or index in targets:
                    checkpoint()
                if index in targets:
                    ret, frame = cap.read()
                    if not ret or frame is None or frame.size == 0:
                        raise ValueError(f"Video decode failed at frame {index}; analysis is incomplete.")
                    timestamp = index / video_info.fps
                    detections = detector.detect_in_frame(frame=frame, session_id=session_id, frame_idx=index,
                        timestamp_seconds=timestamp, min_confidence=min_confidence)
                    checkpoint()
                    cls._save_detections(session_id, run_id, index, detections)
                    all_detections[index] = detections
                    processed.add(index)
                    cls.update_session_status(session_id, "analyzing", progress_start + progress_span * len(processed) / len(indices), stage)
                elif not cap.grab():
                    raise ValueError(f"Video decode ended early at frame {index}; analysis is incomplete.")
                index += 1
        except ValueError:
            with get_db_connection() as conn:
                conn.executemany("UPDATE frame_samples SET status='decode_failed' WHERE run_id=? AND frame_idx=? AND status='planned'",
                                 [(run_id, index) for index in targets - processed])
            raise
        finally:
            cap.release()

    @classmethod
    def execute_analysis(cls, session_id, target_config: TargetConfiguration, progress_callback=None,
                         *, run_id: str, checkpoint: Callable):
        checkpoint()
        with get_db_connection() as conn:
            row = conn.execute("SELECT * FROM sessions WHERE session_id=?", (session_id,)).fetchone()
            if not row:
                raise ValueError("Session not found.")
            video_info = VideoMetadata(**json.loads(row["video_metadata"]))
            telemetry = [GPSPoint(**dict(point)) for point in conn.execute(
                "SELECT timestamp_seconds,latitude,longitude,altitude_m,relative_altitude_m FROM telemetry WHERE session_id=? ORDER BY timestamp_seconds", (session_id,))]
        target_config = SearchPlanAgent.normalize_target(target_config)
        search_plan = SearchPlanAgent.create_search_plan(target_config)
        with get_db_connection() as conn:
            conn.execute("UPDATE sessions SET target_config=?,search_plan=? WHERE session_id=?",
                         (json.dumps(target_config.dict()), json.dumps(search_plan.dict()), session_id))
        cls.log_agent_event(session_id, "SEARCH_PLAN", "Prepared a person search using the supplied visible attributes.", "info")
        cls.update_session_status(session_id, "analyzing", 5, "loading_detector")
        detector = PersonDetector(crop_dir=os.path.join(DATA_DIR, "crops"))
        checkpoint()
        strategy = search_plan.analysis_strategy
        broad_indices = VideoService.sample_frame_indices(video_info, strategy.broad_scan_fps)
        all_detections = {}
        cls.log_agent_event(session_id, "BROAD_SCAN", f"Sampling {len(broad_indices)} frames for person candidates.", "action")
        cls._scan(session_id, run_id, video_info, broad_indices, "broad_scan", detector,
                  strategy.minimum_person_confidence, checkpoint, all_detections, 10, 40)
        # Retain broad positives and never infer a sampled frame a second time.
        focused = set()
        for index, detections in all_detections.items():
            if detections:
                timestamp = index / video_info.fps
                focused.update(VideoService.sample_frame_indices(video_info, strategy.focused_scan_fps,
                    timestamp - strategy.focused_window_seconds, timestamp + strategy.focused_window_seconds))
        focused.difference_update(all_detections)
        cls.log_agent_event(session_id, "FOCUSED_SCAN", f"Inspecting {len(focused)} additional frames around candidates.", "action")
        cls._scan(session_id, run_id, video_info, focused, "focused_scan", detector,
                  strategy.minimum_person_confidence, checkpoint, all_detections, 50, 30)
        tracker = PersonTracker()
        for frame_idx, detections in sorted(all_detections.items()):
            checkpoint()
            tracker.process_detections(detections, timestamp_seconds=frame_idx / video_info.fps)
        cls.update_session_status(session_id, "analyzing", 85, "appearance_matching")
        track_results = []
        for state in tracker.finalize():
            checkpoint()
            # Single observations remain reviewable with insufficient evidence.
            result = AppearanceAnalyzer.evaluate_track(session_id=session_id, track_id=state.track_id,
                detections=state.detections, target_config=target_config, search_plan=search_plan, data_base_dir=DATA_DIR, detector=detector)
            if telemetry:
                result.gps_location = TelemetryService.get_gps_for_timestamp(telemetry, result.best_timestamp_seconds)
            track_results.append(result)
        checkpoint()
        with get_db_connection() as conn:
            conn.execute("BEGIN IMMEDIATE")
            current = conn.execute("SELECT status FROM sessions WHERE session_id=? AND run_id=?", (session_id,run_id)).fetchone()
            if not current or current["status"] not in ("analyzing", "paused"):
                raise RuntimeError("Processing stopped before results were saved.")
            track_columns = {item[1] for item in conn.execute("PRAGMA table_info(tracks)")}
            for track in track_results:
                data = track.dict()
                columns = [name for name in data if name in track_columns]
                values = [json.dumps(data[name]) if isinstance(data[name], (list,dict)) else data[name] for name in columns]
                columns.append("payload")
                values.append(json.dumps(data))
                conn.execute(f"INSERT INTO tracks ({','.join(columns)}) VALUES ({','.join('?' for _ in values)})", values)
        checkpoint()
        cls.update_session_status(session_id, "analyzing", 95, "report_generation")
        report = cls.regenerate_report(session_id)
        checkpoint()
        with get_db_connection() as conn:
            updated = conn.execute("UPDATE sessions SET status='completed',progress_percent=100,current_stage='completed' WHERE session_id=? AND run_id=? AND status='analyzing'", (session_id,run_id))
            if updated.rowcount != 1:
                raise RuntimeError("Processing stopped before completion.")
            conn.execute("UPDATE analysis_runs SET status='completed',finished_at=CURRENT_TIMESTAMP WHERE run_id=?", (run_id,))
        cls.log_agent_event(session_id, "COMPLETE", f"Analysis complete: {len(all_detections)} sampled frames and {len(track_results)} candidate tracks. Human review is required.")
        return report

    @staticmethod
    def regenerate_report(session_id):
        from app.models.schemas import SearchPlan
        with get_db_connection() as conn:
            row = conn.execute("SELECT * FROM sessions WHERE session_id=?", (session_id,)).fetchone()
            if not row or not row["video_metadata"] or not row["search_plan"]:
                raise ValueError("No completed report inputs exist for this session.")
            samples = conn.execute("SELECT timestamp_seconds,status FROM frame_samples WHERE run_id=?", (row["run_id"],)).fetchall()
            count = conn.execute("SELECT COUNT(*) FROM detections WHERE session_id=? AND (run_id=? OR (? IS NULL AND run_id IS NULL))", (session_id,row["run_id"],row["run_id"])).fetchone()[0]
        sampled = [item["timestamp_seconds"] for item in samples if item["status"] == "sampled"]
        failed = [item["timestamp_seconds"] for item in samples if item["status"] == "decode_failed"]
        report, _ = ReportGenerator.generate_report(session_id=session_id,
            target_config=TargetConfiguration(**json.loads(row["target_config"])),
            search_plan=SearchPlan(**json.loads(row["search_plan"])),
            video_info=VideoMetadata(**json.loads(row["video_metadata"])),
            total_sampled_frames=len(sampled), tracks=load_tracks(session_id), has_telemetry=bool(row["has_telemetry"]),
            reports_dir=os.path.join(DATA_DIR,"reports"), sampled_timestamps=sampled if row["run_id"] else None,
            total_people_detected=count if row["run_id"] else None, run_id=row["run_id"], failed_timestamps=failed)
        return report

    @classmethod
    def apply_human_feedback(cls, session_id, track_id, feedback):
        with get_db_connection() as conn:
            conn.execute("BEGIN IMMEDIATE")
            session = conn.execute("SELECT status FROM sessions WHERE session_id=?", (session_id,)).fetchone()
            if session and session["status"] in ("queued","analyzing","paused"):
                raise RuntimeError("Wait for analysis to finish before reviewing results.")
            row = conn.execute("SELECT * FROM tracks WHERE session_id=? AND track_id=?", (session_id,track_id)).fetchone()
            if not row:
                raise LookupError("Track not found.")
            # Store human judgment separately; keep automated scores for auditing.
            conn.execute("UPDATE tracks SET human_feedback=?,human_notes=?,requires_human_review=? WHERE session_id=? AND track_id=?",
                         (feedback.status, feedback.notes, int(feedback.status == "needs_research"), session_id, track_id))
        cls.log_agent_event(session_id,"FEEDBACK",f"Operator marked Track #{track_id} as {feedback.status}.","action")
        # Report GET regenerates from these durable decisions, never an old snapshot.
        return next(track for track in load_tracks(session_id) if track.track_id == track_id)
