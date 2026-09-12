from click import Tuple
import os
import json
import time
import cv2
import asyncio
from datetime import datetime
from typing import Dict, Any, List, Optional, Callable
from app.database import get_db_connection
from app.models.schemas import (
    TargetConfiguration, SearchPlan, VideoMetadata, SessionStatus,
    AgentLogEntry, TrackResult, HumanFeedbackInput, GPSPoint, AttributeDetail
)
from app.services.video_service import VideoService
from app.services.search_agent import SearchPlanAgent
from app.services.detector import PersonDetector
from app.services.tracker import PersonTracker
from app.services.appearance_analyzer import AppearanceAnalyzer
from app.services.telemetry_service import TelemetryService
from app.services.report_generator import ReportGenerator

DATA_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "data"))

class AgenticLoopManager:
    def __init__(self):
        pass

    @staticmethod
    def log_agent_event(session_id: str, step: str, message: str, level: str = "info"):
        conn = get_db_connection()
        now_str = datetime.now().strftime("%H:%M:%S")
        conn.execute(
            "INSERT INTO agent_logs (session_id, timestamp, step, message, level) VALUES (?, ?, ?, ?, ?)",
            (session_id, now_str, step, message, level)
        )
        conn.commit()
        conn.close()

    @staticmethod
    def update_session_status(
        session_id: str,
        status: str,
        progress: float,
        stage: str,
        people_count: int = 0,
        tracks_count: int = 0
    ):
        conn = get_db_connection()
        conn.execute(
            "UPDATE sessions SET status=?, progress_percent=?, current_stage=? WHERE session_id=?",
            (status, round(progress, 1), stage, session_id)
        )
        conn.commit()
        conn.close()

    @classmethod
    def execute_analysis(
        cls,
        session_id: str,
        target_config: TargetConfiguration,
        progress_callback: Optional[Callable[[Dict[str, Any]], None]] = None
    ):
        cls.log_agent_event(session_id, "INIT", "Forming Search Plan from target description...", "action")
        cls.update_session_status(session_id, "analyzing", 5.0, "search_plan_generation")

        conn = get_db_connection()
        session_row = conn.execute("SELECT * FROM sessions WHERE session_id=?", (session_id,)).fetchone()
        if not session_row:
            conn.close()
            raise ValueError(f"Session {session_id} not found.")

        video_meta_dict = json.loads(session_row["video_metadata"])
        video_info = VideoMetadata(**video_meta_dict)
        has_telemetry = bool(session_row["has_telemetry"])

        # Step 1: Form search plan
        search_plan = SearchPlanAgent.create_search_plan(target_config)
        conn.execute(
            "UPDATE sessions SET target_config=?, search_plan=? WHERE session_id=?",
            (json.dumps(target_config.dict()), json.dumps(search_plan.dict()), session_id)
        )
        conn.commit()

        cls.log_agent_event(
            session_id,
            "SEARCH_PLAN",
            f"Search Plan created: High-value attributes: {', '.join(search_plan.high_value_attributes)}",
            "info"
        )

        # Step 2: Telemetry loading
        telemetry_points: List[GPSPoint] = []
        if has_telemetry:
            t_rows = conn.execute("SELECT * FROM telemetry WHERE session_id=?", (session_id,)).fetchall()
            for tr in t_rows:
                telemetry_points.append(GPSPoint(
                    timestamp_seconds=tr["timestamp_seconds"],
                    latitude=tr["latitude"],
                    longitude=tr["longitude"],
                    altitude_m=tr["altitude_m"],
                    relative_altitude_m=tr["relative_altitude_m"]
                ))
            cls.log_agent_event(session_id, "TELEMETRY", f"Correlated {len(telemetry_points)} flight telemetry GPS points.", "info")

        conn.close()

        # Step 3: Stage 1 Broad Scan (~1 FPS)
        broad_fps = search_plan.analysis_strategy.broad_scan_fps
        broad_timestamps = VideoService.get_sample_timestamps(video_info.duration_seconds, broad_fps)
        cls.log_agent_event(
            session_id,
            "BROAD_SCAN",
            f"Starting Stage 1 Broad Scan at {broad_fps} FPS across {len(broad_timestamps)} frames...",
            "action"
        )
        cls.update_session_status(session_id, "analyzing", 15.0, "stage_1_broad_scan")

        detector = PersonDetector(crop_dir=os.path.join(DATA_DIR, "crops"))
        cap = cv2.VideoCapture(video_info.filepath)

        detection_windows: List[float] = []
        broad_detections: List[Dict[str, Any]] = []

        # Fast sequential decode for Stage 1 using cap.grab()
        broad_target_frames = {int(t * video_info.fps): t for t in broad_timestamps}
        total_broad = len(broad_target_frames)
        max_broad_frame = max(broad_target_frames.keys()) if broad_target_frames else 0

        curr_f = 0
        proc_broad = 0
        while cap.isOpened() and curr_f <= max_broad_frame:
            if curr_f in broad_target_frames:
                ret, frame = cap.read()
                if not ret or frame is None:
                    break
                t_sec = broad_target_frames[curr_f]
                dets = detector.detect_in_frame(
                    frame=frame,
                    session_id=session_id,
                    frame_idx=curr_f,
                    timestamp_seconds=t_sec,
                    min_confidence=search_plan.analysis_strategy.minimum_person_confidence
                )
                if dets:
                    detection_windows.append(t_sec)
                    for d in dets:
                        broad_detections.append((t_sec, d))
                    min_ts = int(t_sec // 60)
                    sec_ts = int(t_sec % 60)
                    cls.log_agent_event(
                        session_id,
                        "DETECTION",
                        f"Person detected at {min_ts:02d}:{sec_ts:02d} ({t_sec}s) with confidence {dets[0].confidence}.",
                        "match"
                    )

                proc_broad += 1
                pct = 15.0 + (proc_broad / float(max(1, total_broad))) * 35.0
                cls.update_session_status(session_id, "analyzing", pct, "stage_1_broad_scan", len(broad_detections), 0)
            else:
                ret = cap.grab()
                if not ret:
                    break

            curr_f += 1

        # Step 4: Stage 2 Focused Inspection around detections
        cls.log_agent_event(
            session_id,
            "FOCUSED_SCAN",
            f"Stage 1 found {len(detection_windows)} detection timestamps. Increasing sampling rate to 3.0 FPS for focused track inspection...",
            "action"
        )
        cls.update_session_status(session_id, "analyzing", 55.0, "stage_2_focused_scan")

        focused_window_sec = search_plan.analysis_strategy.focused_window_seconds
        focused_fps = search_plan.analysis_strategy.focused_scan_fps

        # Merge overlapping focused timestamp intervals
        intervals: List[Tuple[float, float]] = []
        for det_t in detection_windows:
            t_start = max(0.0, det_t - focused_window_sec)
            t_end = min(video_info.duration_seconds, det_t + focused_window_sec)
            if not intervals or t_start > intervals[-1][1]:
                intervals.append((t_start, t_end))
            else:
                intervals[-1] = (intervals[-1][0], max(intervals[-1][1], t_end))

        focused_timestamps_set = set()
        for start, end in intervals:
            t_curr = start
            while t_curr <= end:
                focused_timestamps_set.add(round(t_curr, 2))
                t_curr += (1.0 / focused_fps)

        focused_timestamps = sorted(list(focused_timestamps_set))
        tracker = PersonTracker()

        # Fast sequential decode for Stage 2 using cap.grab()
        focused_target_frames = {int(t * video_info.fps): t for t in focused_timestamps}
        max_target_frame = max(focused_target_frames.keys()) if focused_target_frames else 0

        cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
        curr_f = 0
        total_focused = len(focused_target_frames)
        proc_count = 0

        while cap.isOpened() and curr_f <= max_target_frame:
            if curr_f in focused_target_frames:
                ret, frame = cap.read()
                if not ret or frame is None:
                    break
                t_sec = focused_target_frames[curr_f]
                dets = detector.detect_in_frame(
                    frame=frame,
                    session_id=session_id,
                    frame_idx=curr_f,
                    timestamp_seconds=t_sec,
                    min_confidence=0.30
                )
                if dets:
                    tracker.process_detections(dets)

                proc_count += 1
                pct = 55.0 + (proc_count / float(max(1, total_focused))) * 25.0
                cls.update_session_status(session_id, "analyzing", pct, "stage_2_focused_scan")
            else:
                ret = cap.grab()
                if not ret:
                    break

            curr_f += 1

        cap.release()

        # Step 5: Multi-frame evidence aggregation & Appearance Analysis
        cls.log_agent_event(session_id, "EVALUATION", "Aggregating multi-frame track evidence and evaluating target appearance match...", "action")
        cls.update_session_status(session_id, "analyzing", 85.0, "appearance_matching")

        tracks_state = tracker.finalize()
        track_results: List[TrackResult] = []

        for tr_state in tracks_state:
            if len(tr_state.detections) < search_plan.analysis_strategy.minimum_track_observations:
                continue

            tr_res = AppearanceAnalyzer.evaluate_track(
                session_id=session_id,
                track_id=tr_state.track_id,
                detections=tr_state.detections,
                target_config=target_config,
                search_plan=search_plan,
                data_base_dir=DATA_DIR
            )

            # Correlate GPS location if available
            if telemetry_points:
                gps_match = TelemetryService.get_gps_for_timestamp(telemetry_points, tr_res.best_timestamp_seconds)
                if gps_match:
                    tr_res.gps_location = gps_match

            track_results.append(tr_res)

        # Save tracks to DB
        conn = get_db_connection()
        for tr in track_results:
            conn.execute(
                """
                INSERT OR REPLACE INTO tracks (
                    session_id, track_id, first_seen_seconds, last_seen_seconds, best_timestamp_seconds,
                    classification, person_detection_confidence, appearance_similarity, evidence_quality,
                    final_ranking_score, observations_analyzed, attributes, matching_evidence,
                    conflicting_evidence, unknown_attributes, requires_human_review, explanation,
                    best_frame_path, cropped_samples, human_feedback, human_notes, gps_location
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    tr.session_id, tr.track_id, tr.first_seen_seconds, tr.last_seen_seconds, tr.best_timestamp_seconds,
                    tr.classification, tr.person_detection_confidence, tr.appearance_similarity, tr.evidence_quality,
                    tr.final_ranking_score, tr.observations_analyzed, json.dumps({k: v.dict() for k, v in tr.attributes.items()}),
                    json.dumps(tr.matching_evidence), json.dumps(tr.conflicting_evidence), json.dumps(tr.unknown_attributes),
                    1 if tr.requires_human_review else 0, tr.explanation, tr.best_frame_path,
                    json.dumps(tr.cropped_samples), tr.human_feedback, tr.human_notes,
                    json.dumps(tr.gps_location.dict()) if tr.gps_location else None
                )
            )
        conn.commit()

        # Step 6: Generate post-flight report
        cls.log_agent_event(session_id, "REPORT", "Generating post-flight SAR search report and actionable recommendations...", "action")
        reports_dir = os.path.join(DATA_DIR, "reports")
        report, report_rel_path = ReportGenerator.generate_report(
            session_id=session_id,
            target_config=target_config,
            search_plan=search_plan,
            video_info=video_info,
            total_sampled_frames=len(broad_timestamps) + len(focused_timestamps),
            tracks=track_results,
            has_telemetry=has_telemetry,
            reports_dir=reports_dir
        )

        cls.log_agent_event(
            session_id,
            "COMPLETE",
            f"Analysis complete. Found {len(track_results)} unique tracks across {video_info.duration_seconds}s flight recording. Report ready.",
            "info"
        )
        cls.update_session_status(session_id, "completed", 100.0, "completed", len(broad_detections), len(track_results))
        conn.close()

        return report

    @staticmethod
    def apply_human_feedback(session_id: str, track_id: int, feedback: HumanFeedbackInput) -> TrackResult:
        conn = get_db_connection()
        row = conn.execute("SELECT * FROM tracks WHERE session_id=? AND track_id=?", (session_id, track_id)).fetchone()
        if not row:
            conn.close()
            raise ValueError(f"Track {track_id} not found in session {session_id}.")

        # Update feedback and adjust classification based on human review
        new_classification = row["classification"]
        if feedback.status == "confirmed":
            new_classification = "strong_match"
        elif feedback.status == "rejected":
            new_classification = "unlikely_match"
        elif feedback.status == "needs_research":
            new_classification = "possible_match"

        conn.execute(
            "UPDATE tracks SET human_feedback=?, human_notes=?, classification=?, requires_human_review=0 WHERE session_id=? AND track_id=?",
            (feedback.status, feedback.notes, new_classification, session_id, track_id)
        )
        conn.commit()

        # Log event
        now_str = datetime.now().strftime("%H:%M:%S")
        conn.execute(
            "INSERT INTO agent_logs (session_id, timestamp, step, message, level) VALUES (?, ?, ?, ?, ?)",
            (session_id, now_str, "FEEDBACK", f"Operator submitted feedback '{feedback.status}' for Track #{track_id}.", "action")
        )
        conn.commit()

        # Fetch updated track
        updated_row = conn.execute("SELECT * FROM tracks WHERE session_id=? AND track_id=?", (session_id, track_id)).fetchone()
        conn.close()

        # Re-build TrackResult
        attrs_raw = json.loads(updated_row["attributes"])
        attributes = {k: AttributeDetail(**v) for k, v in attrs_raw.items()}
        gps_raw = json.loads(updated_row["gps_location"]) if updated_row["gps_location"] else None

        return TrackResult(
            session_id=session_id,
            track_id=track_id,
            first_seen_seconds=updated_row["first_seen_seconds"],
            last_seen_seconds=updated_row["last_seen_seconds"],
            best_timestamp_seconds=updated_row["best_timestamp_seconds"],
            classification=updated_row["classification"],
            person_detection_confidence=updated_row["person_detection_confidence"],
            appearance_similarity=updated_row["appearance_similarity"],
            evidence_quality=updated_row["evidence_quality"],
            final_ranking_score=updated_row["final_ranking_score"],
            observations_analyzed=updated_row["observations_analyzed"],
            attributes=attributes,
            matching_evidence=json.loads(updated_row["matching_evidence"]),
            conflicting_evidence=json.loads(updated_row["conflicting_evidence"]),
            unknown_attributes=json.loads(updated_row["unknown_attributes"]),
            requires_human_review=bool(updated_row["requires_human_review"]),
            explanation=updated_row["explanation"],
            best_frame_path=updated_row["best_frame_path"],
            cropped_samples=json.loads(updated_row["cropped_samples"]),
            human_feedback=updated_row["human_feedback"],
            human_notes=updated_row["human_notes"],
            gps_location=GPSPoint(**gps_raw) if gps_raw else None
        )
