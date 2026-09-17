"""Semantic retrieval followed by localized evidence ranking for generic entities."""
import json
import os
from pathlib import Path
import uuid
from typing import Dict, List, Sequence

import cv2
import numpy as np

from app import database
from app.models.open_vocabulary import (
    EntityTrack, EvidenceAssessment, SearchQuery, SearchResult,
)
from app.models.open_vocabulary import ModelProvenance
from app.models.schemas import TargetConfiguration, VideoMetadata
from app.services.generic_detector import CandidateFrame, YoloDetectionProvider
from app.services.event_ranker import build_event_results
from app.services.grounding import Owlv2GroundingProvider
from app.services.query_parser import StructuredQueryParser
from app.services.semantic_retrieval import SemanticRetrievalService
from app.services.temporal_verifier import MultiFrameEvidenceVerifier
from app.services.video_indexer import VideoIndexer
from app.services.visual_features import color_match_score


def _iou(a, b):
    intersection = max(0.0, min(a[2], b[2]) - max(a[0], b[0])) * max(0.0, min(a[3], b[3]) - max(a[1], b[1]))
    area_a = max(0.0, a[2] - a[0]) * max(0.0, a[3] - a[1])
    area_b = max(0.0, b[2] - b[0]) * max(0.0, b[3] - b[1])
    return intersection / max(1.0, area_a + area_b - intersection)


def track_entities(detections, max_gap=4.0, minimum_iou=.2):
    active, completed = [], []
    for detection in sorted(detections, key=lambda item: (item.timestamp_seconds, -item.confidence)):
        expired = [track for track in active if detection.timestamp_seconds - track[-1].timestamp_seconds > max_gap]
        completed.extend(expired)
        active = [track for track in active if track not in expired]
        choices = []
        for track in active:
            previous = track[-1]
            if previous.label != detection.label or previous.frame_idx == detection.frame_idx:
                continue
            overlap = float(_iou(previous.bbox, detection.bbox))
            ax, ay = (previous.bbox[0] + previous.bbox[2]) / 2, (previous.bbox[1] + previous.bbox[3]) / 2
            bx, by = (detection.bbox[0] + detection.bbox[2]) / 2, (detection.bbox[1] + detection.bbox[3]) / 2
            scale = max(1.0, np.hypot(previous.bbox[2] - previous.bbox[0], previous.bbox[3] - previous.bbox[1]))
            proximity = max(0.0, 1.0 - np.hypot(ax - bx, ay - by) / (1.5 * scale))
            choices.append((max(overlap, float(proximity)), track))
        choices.sort(key=lambda item: item[0], reverse=True)
        if choices and choices[0][0] >= minimum_iou:
            choices[0][1].append(detection)
        else:
            active.append([detection])
    completed.extend(active)
    return completed


def _track_priority(query: SearchQuery, track):
    color = next((attribute.value for entity in query.entities for attribute in entity.attributes
                  if attribute.name == "color" and attribute.required), None)
    color_support = max((color_match_score(color, item.attributes.get("colors", {}))[1]
                         for item in track), default=0.0) if color else 1.0
    semantic = max((float(item.attributes.get("semantic_similarity", -1.0)) for item in track), default=-1.0)
    confidence = max((item.confidence for item in track), default=0.0)
    visibility = max((item.visibility for item in track), default=0.0)
    return color_support, semantic, confidence, visibility


def _matches_entity(label, entity):
    expected = (entity.entity_type or entity.name).lower()
    aliases = {expected}
    if expected in {"woman", "man", "child", "someone"}:
        aliases.add("person")
    if expected == "vehicle":
        aliases.update({"car", "truck", "bus", "motorcycle"})
    return label.lower() in aliases


def localize_entities(frames, query: SearchQuery, session_id: str, evidence_root: Path,
                      detector=None, grounder_factory=Owlv2GroundingProvider):
    detector = detector or YoloDetectionProvider(str(evidence_root))
    vocabulary = [entity.entity_type or entity.name for entity in query.entities]
    supported = [value for value in vocabulary if detector.supported_labels([value])]
    grounded = [value for value in vocabulary if not detector.supported_labels([value])]
    detections = detector.detect(frames, supported, session_id)
    if grounded:
        detections.extend(grounder_factory(str(evidence_root)).ground(frames, grounded, session_id))
    return detections, grounded


def _extract_clip(video_path: str, start: float, end: float, destination: Path):
    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        raise ValueError("Source video could not be opened for clip extraction.")
    fps = float(cap.get(cv2.CAP_PROP_FPS))
    source_width, source_height = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)), int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    max_width = max(320, int(os.environ.get("AIEYE_RESULT_CLIP_WIDTH", "1280")))
    scale = min(1.0, max_width / max(1, source_width))
    width, height = int(source_width * scale), int(source_height * scale)
    width -= width % 2
    height -= height % 2
    if fps <= 0 or width <= 0 or height <= 0:
        cap.release()
        raise ValueError("Source video has invalid clip metadata.")
    destination.parent.mkdir(parents=True, exist_ok=True)
    writer = cv2.VideoWriter(str(destination), cv2.VideoWriter_fourcc(*"mp4v"), fps, (width, height))
    if not writer.isOpened():
        cap.release()
        raise OSError("Could not create result clip.")
    cap.set(cv2.CAP_PROP_POS_FRAMES, max(0, int(start * fps)))
    written = 0
    try:
        while cap.get(cv2.CAP_PROP_POS_FRAMES) / fps <= end:
            ok, frame = cap.read()
            if not ok or frame is None:
                break
            if scale < 1:
                frame = cv2.resize(frame, (width, height), interpolation=cv2.INTER_AREA)
            writer.write(frame)
            written += 1
    finally:
        writer.release()
        cap.release()
    if not written:
        destination.unlink(missing_ok=True)
        raise ValueError("No frames were available for the result clip.")


def load_search_results(session_id: str) -> List[SearchResult]:
    with database.get_db_connection() as conn:
        session = conn.execute("SELECT search_id FROM sessions WHERE session_id=?", (session_id,)).fetchone()
        if not session or not session["search_id"]:
            return []
        rows = conn.execute("SELECT payload,human_feedback,human_notes FROM search_results WHERE search_id=? ORDER BY overall_score DESC",
                            (session["search_id"],)).fetchall()
    results = []
    for row in rows:
        payload = json.loads(row["payload"])
        payload["human_feedback"] = row["human_feedback"]
        payload["human_notes"] = row["human_notes"]
        results.append(SearchResult(**payload))
    return results


class OpenVocabularySearchManager:
    @staticmethod
    def _log(session_id, step, message, level="info"):
        from app.services.agentic_loop import AgenticLoopManager
        AgenticLoopManager.log_agent_event(session_id, step, message, level)

    @staticmethod
    def _status(session_id, progress, stage):
        with database.get_db_connection() as conn:
            conn.execute("""UPDATE sessions SET progress_percent=?,current_stage=?
                WHERE session_id=? AND status='analyzing'""", (progress, stage, session_id))

    @classmethod
    def execute_analysis(cls, session_id: str, target_config: TargetConfiguration, *, run_id: str, checkpoint):
        checkpoint()
        with database.get_db_connection() as conn:
            row = conn.execute("SELECT * FROM sessions WHERE session_id=?", (session_id,)).fetchone()
            if not row or not row["video_metadata"]:
                raise ValueError("Session video metadata is missing.")
            video = VideoMetadata(**json.loads(row["video_metadata"]))
        query = StructuredQueryParser().parse(target_config.free_text_description)
        search_id = f"search_{uuid.uuid4().hex}"
        with database.get_db_connection() as conn:
            conn.execute("BEGIN IMMEDIATE")
            conn.execute("""INSERT INTO searches(search_id,session_id,status,processing_mode,query_json,parser_provenance)
                VALUES (?,?,?,?,?,?)""", (search_id, session_id, "indexing", query.processing_mode,
                query.model_dump_json(), query.parser_provenance.model_dump_json() if query.parser_provenance else None))
            conn.execute("UPDATE sessions SET search_id=?,search_query=? WHERE session_id=?",
                         (search_id, query.model_dump_json(), session_id))
        cls._log(session_id, "QUERY", f"Structured query with {len(query.entities)} required entities and {len(query.actions)} actions.")
        if query.unsupported_concepts or not query.entities:
            cls._complete_without_results(session_id, run_id, search_id, "unsupported_query",
                "The query contains no entity supported by the current parser.")
            return []
        cls._status(session_id, 5, "video_indexing")
        index = VideoIndexer().build_or_reuse(video, query.processing_mode)
        checkpoint()
        with database.get_db_connection() as conn:
            conn.execute("UPDATE sessions SET index_id=? WHERE session_id=?", (index.index_id, session_id))
            conn.execute("UPDATE searches SET index_id=?,status='retrieving',started_at=CURRENT_TIMESTAMP WHERE search_id=?",
                         (index.index_id, search_id))
        cls._log(session_id, "VIDEO_INDEX", f"{'Reused' if index.cache_hit else 'Built'} index {index.index_id}.", "action")
        cls._status(session_id, 20, "semantic_retrieval")
        retrieval_limit = {"fast": 16, "balanced": 40, "thorough": 80}[query.processing_mode]
        retrieval = SemanticRetrievalService()
        candidates = retrieval.retrieve(
            index.index_id, query.original_text, limit=retrieval_limit,
            search_id=search_id, owner_kinds=("frame", "clip"),
        )
        checkpoint()
        # Frames and clips can share a representative image. Localize it once, preserving the best score.
        best_by_path = {}
        for candidate in candidates:
            previous = best_by_path.get(candidate.artifact_path)
            if not previous or candidate.semantic_similarity > previous.semantic_similarity:
                best_by_path[candidate.artifact_path] = candidate
        with database.get_db_connection() as conn:
            frame_rows = conn.execute("SELECT frame_id,frame_idx,timestamp_seconds,image_path FROM indexed_frames WHERE index_id=?",
                                      (index.index_id,)).fetchall()
        frame_by_path = {str(Path(item["image_path"]).resolve()): item for item in frame_rows}
        frames = []
        for path, candidate in best_by_path.items():
            frame = frame_by_path.get(str(Path(path).resolve()))
            if frame:
                frames.append(CandidateFrame(
                    frame_id=frame["frame_id"], frame_idx=frame["frame_idx"],
                    timestamp_seconds=frame["timestamp_seconds"], image_path=frame["image_path"],
                    semantic_similarity=candidate.semantic_similarity,
                ))
        frames.sort(key=lambda item: item.timestamp_seconds)
        cls._status(session_id, 50, "entity_localization")
        evidence_root = Path(database.DB_DIR) / "evidence"
        detections, grounded = localize_entities(frames, query, session_id, evidence_root)
        if grounded:
            cls._log(session_id, "GROUNDING", "Grounded open-vocabulary entities: " + ", ".join(grounded), "action")
        checkpoint()
        tracks = track_entities(detections)
        max_tracks = max(1, int(os.environ.get("AIEYE_MAX_RESULT_TRACKS", "10")))
        tracks = sorted(tracks, key=lambda track: _track_priority(query, track), reverse=True)[:max_tracks]
        cls._status(session_id, 75, "evidence_ranking")
        results = cls._rank(query, search_id, session_id, video, tracks, evidence_root,
                            retrieval.provider.provenance)
        checkpoint()
        with database.get_db_connection() as conn:
            conn.execute("BEGIN IMMEDIATE")
            conn.executemany("""INSERT INTO search_results(search_id,result_id,start_seconds,end_seconds,
                classification,overall_score,payload) VALUES (?,?,?,?,?,?,?)""", [
                (search_id, result.result_id, result.start_seconds, result.end_seconds,
                 result.classification, result.overall_score, result.model_dump_json()) for result in results
            ])
            conn.execute("UPDATE searches SET status='completed',finished_at=CURRENT_TIMESTAMP WHERE search_id=?", (search_id,))
            conn.execute("UPDATE analysis_runs SET status='completed',finished_at=CURRENT_TIMESTAMP WHERE run_id=?", (run_id,))
            conn.execute("""UPDATE sessions SET status='completed',progress_percent=100,current_stage='completed'
                WHERE session_id=? AND run_id=? AND status='analyzing'""", (session_id, run_id))
        message = (f"Search completed with {len(results)} localized result tracks. Human review is required."
                   if results else "No matching event was found in the analyzed frames.")
        cls._log(session_id, "COMPLETE", message)
        return results

    @classmethod
    def _complete_without_results(cls, session_id, run_id, search_id, classification, message):
        with database.get_db_connection() as conn:
            conn.execute("BEGIN IMMEDIATE")
            conn.execute("UPDATE searches SET status=?,finished_at=CURRENT_TIMESTAMP,error_message=? WHERE search_id=?",
                         (classification, message, search_id))
            conn.execute("UPDATE analysis_runs SET status='completed',finished_at=CURRENT_TIMESTAMP WHERE run_id=?", (run_id,))
            conn.execute("""UPDATE sessions SET status='completed',progress_percent=100,current_stage=?
                WHERE session_id=? AND run_id=? AND status='analyzing'""", (classification, session_id, run_id))
        cls._log(session_id, "COMPLETE", message, "warning")

    @classmethod
    def _rank(cls, query: SearchQuery, search_id: str, session_id: str, video: VideoMetadata,
              tracks: Sequence[Sequence], evidence_root: Path,
              semantic_provenance: ModelProvenance) -> List[SearchResult]:
        if len(query.entities) > 1 or query.actions or query.relationships:
            event_results = build_event_results(query, search_id, video.duration_seconds, tracks)
            return cls._materialize_events(
                event_results[:max(1, int(os.environ.get("AIEYE_MAX_RESULT_TRACKS", "10")))],
                session_id, video, evidence_root, semantic_provenance,
            )
        expected_entity = query.entities[0]
        color_constraint = next((item for item in expected_entity.attributes if item.name == "color"), None)
        output = []
        for number, observations in enumerate(tracks, start=1):
            if not observations or not _matches_entity(observations[0].label, expected_entity):
                continue
            entity_scores = [item.confidence for item in observations]
            semantic_scores = [float(item.attributes.get("semantic_similarity", 0)) for item in observations]
            visibility_scores = [item.visibility for item in observations]
            color_scores = []
            raw_colors = []
            if color_constraint:
                for item in observations:
                    score, raw = color_match_score(color_constraint.value, item.attributes.get("colors", {}))
                    color_scores.append(score)
                    raw_colors.append(raw)
            entity_evidence = EvidenceAssessment(
                criterion_id=expected_entity.entity_id, kind="entity", assessment="supported",
                score=max(entity_scores), explanation=f"Localized {observations[0].label} in {len(observations)} indexed observations.",
                timestamps=[item.timestamp_seconds for item in observations],
                entity_track_ids=[f"{observations[0].label}:{number}"],
                evidence_paths=[item.crop_path for item in observations if item.crop_path],
                provenance=observations[0].provenance,
            )
            evidence = [entity_evidence]
            color_support = 1.0
            color_assessment = "supported"
            if color_constraint:
                color_support = max(color_scores, default=0.0)
                raw_support = max(raw_colors, default=0.0)
                color_assessment = "supported" if color_support >= .30 and raw_support >= .18 else (
                    "conflicting" if raw_support < .05 else "uncertain"
                )
                evidence.append(EvidenceAssessment(
                    criterion_id=color_constraint.criterion_id, kind="attribute",
                    assessment=color_assessment, score=color_support,
                    explanation=(f"Requested {color_constraint.value}; strongest masked color support was "
                                 f"{round(raw_support * 100)}% of localized pixels."),
                    timestamps=[item.timestamp_seconds for item, score in zip(observations, color_scores) if score >= .35],
                    entity_track_ids=[f"{observations[0].label}:{number}"],
                    evidence_paths=[item.crop_path for item in observations if item.crop_path],
                    provenance=observations[0].provenance,
                ))
            if color_assessment == "supported":
                classification = "strong_match" if len(observations) >= 2 else "possible_match"
            elif color_assessment == "conflicting":
                classification = "unlikely_match"
            else:
                classification = "insufficient_visibility"
            semantic = max(semantic_scores, default=-1.0)
            semantic_component = max(0.0, min(1.0, (semantic + 1.0) / 2.0))
            overall = .25 * max(entity_scores) + .4 * color_support + .15 * max(visibility_scores) + .2 * semantic_component
            best_index = max(range(len(observations)), key=lambda index: (
                color_scores[index] if color_scores else 1.0, observations[index].confidence,
                observations[index].visibility,
            ))
            best = observations[best_index]
            start = max(0.0, min(item.timestamp_seconds for item in observations) - 1.5)
            end = min(video.duration_seconds, max(item.timestamp_seconds for item in observations) + 1.5)
            track = EntityTrack(
                track_id=f"{best.label}:{number}", label=best.label,
                start_seconds=min(item.timestamp_seconds for item in observations),
                end_seconds=max(item.timestamp_seconds for item in observations),
                detections=list(observations),
                attributes={"requested_color": color_constraint.value if color_constraint else None,
                            "color_support": round(color_support, 4)},
            )
            constraint_evidence = MultiFrameEvidenceVerifier().verify(query, [track])
            evidence.extend(constraint_evidence)
            if any(item.assessment != "supported" for item in constraint_evidence):
                classification = "insufficient_visibility"
            with database.get_db_connection() as conn:
                frame_row = conn.execute("SELECT image_path FROM indexed_frames WHERE frame_id=? AND index_id=(SELECT index_id FROM sessions WHERE session_id=?)",
                                         (best.frame_id, session_id)).fetchone()
            if not frame_row:
                continue
            image = cv2.imread(frame_row["image_path"])
            if image is None:
                continue
            for observation in observations:
                if observation.frame_idx == best.frame_idx:
                    x1, y1, x2, y2 = map(int, observation.bbox)
                    cv2.rectangle(image, (x1, y1), (x2, y2), (0, 210, 255), 5)
                    cv2.putText(image, f"{observation.label} {observation.confidence:.2f}",
                                (x1, max(30, y1 - 10)), cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 210, 255), 3)
            directory = evidence_root / session_id
            directory.mkdir(parents=True, exist_ok=True)
            annotated = directory / f"result_{number}_frame.jpg"
            clip = directory / f"result_{number}_clip.mp4"
            if not cv2.imwrite(str(annotated), image):
                raise OSError("Could not save annotated result frame.")
            _extract_clip(video.filepath, start, end, clip)
            explanation = (f"{classification.replace('_', ' ').title()}: localized {best.label}. "
                           + (evidence[-1].explanation if color_constraint else "Entity evidence is present."))
            output.append(SearchResult(
                result_id=f"result_{uuid.uuid4().hex}", search_id=search_id,
                start_seconds=start, end_seconds=end, best_timestamp_seconds=best.timestamp_seconds,
                classification=classification, overall_score=round(max(0.0, min(1.0, overall)), 4),
                component_scores={"entity_presence": round(max(entity_scores), 4),
                                  "attribute_agreement": round(color_support, 4),
                                  "visibility": round(max(visibility_scores), 4),
                                  "semantic_similarity": round(semantic_component, 4)},
                entities=[track], evidence=evidence, explanation=explanation,
                best_frame_path=f"/evidence/{session_id}/{annotated.name}",
                clip_path=f"/evidence/{session_id}/{clip.name}",
                model_provenance=[semantic_provenance] + list({
                    item.provenance.model_version: item.provenance for item in observations
                }.values()),
            ))
        return sorted(output, key=lambda item: item.overall_score, reverse=True)

    @classmethod
    def _materialize_events(cls, results, session_id, video, evidence_root, semantic_provenance):
        directory = evidence_root / session_id
        directory.mkdir(parents=True, exist_ok=True)
        output = []
        for number, result in enumerate(results, start=1):
            detections = [item for track in result.entities for item in track.detections if item.frame_id]
            if not detections:
                continue
            best = min(detections, key=lambda item: abs(item.timestamp_seconds - result.best_timestamp_seconds))
            with database.get_db_connection() as conn:
                frame_row = conn.execute(
                    "SELECT image_path FROM indexed_frames WHERE frame_id=? AND index_id=(SELECT index_id FROM sessions WHERE session_id=?)",
                    (best.frame_id, session_id),
                ).fetchone()
            if not frame_row:
                continue
            image = cv2.imread(frame_row["image_path"])
            if image is None:
                continue
            colors = [(0, 210, 255), (255, 120, 20), (80, 220, 80), (220, 80, 220)]
            for index, track in enumerate(result.entities):
                observation = min(track.detections, key=lambda item: abs(item.timestamp_seconds - best.timestamp_seconds))
                if abs(observation.timestamp_seconds - best.timestamp_seconds) > .6:
                    continue
                x1, y1, x2, y2 = map(int, observation.bbox)
                color = colors[index % len(colors)]
                cv2.rectangle(image, (x1, y1), (x2, y2), color, 5)
                cv2.putText(image, f"{track.label} {observation.confidence:.2f}",
                            (x1, max(30, y1 - 10)), cv2.FONT_HERSHEY_SIMPLEX, 1, color, 3)
            annotated = directory / f"event_{number}_frame.jpg"
            clip = directory / f"event_{number}_clip.mp4"
            if not cv2.imwrite(str(annotated), image):
                raise OSError("Could not save annotated event frame.")
            _extract_clip(video.filepath, result.start_seconds, result.end_seconds, clip)
            result.best_timestamp_seconds = best.timestamp_seconds
            result.best_frame_path = f"/evidence/{session_id}/{annotated.name}"
            result.clip_path = f"/evidence/{session_id}/{clip.name}"
            if not any(item.model_version == semantic_provenance.model_version for item in result.model_provenance):
                result.model_provenance.insert(0, semantic_provenance)
            output.append(result)
        return output

    @staticmethod
    def apply_feedback(session_id, result_id, feedback):
        with database.get_db_connection() as conn:
            conn.execute("BEGIN IMMEDIATE")
            session = conn.execute("SELECT status,search_id FROM sessions WHERE session_id=?", (session_id,)).fetchone()
            if not session:
                raise LookupError("Session not found.")
            if session["status"] in ("queued", "analyzing", "paused"):
                raise RuntimeError("Wait for analysis to finish before reviewing results.")
            updated = conn.execute("""UPDATE search_results SET human_feedback=?,human_notes=?
                WHERE search_id=? AND result_id=?""",
                (feedback.status, feedback.notes, session["search_id"], result_id))
            if updated.rowcount != 1:
                raise LookupError("Result not found.")
        return next(item for item in load_search_results(session_id) if item.result_id == result_id)
