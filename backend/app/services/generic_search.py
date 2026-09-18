"""Semantic retrieval followed by localized evidence ranking for generic entities."""
import json
import os
from pathlib import Path
import subprocess
import time
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
from app.services.processing_profiles import get_processing_profile
from app.services.semantic_retrieval import SemanticRetrievalService
from app.services.temporal_verifier import MultiFrameEvidenceVerifier
from app.services.video_indexer import VideoIndexer
from app.services.visual_features import color_match_score
from app.services.license_plate_reader import LicensePlateReader, normalize_plate


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
                      detector=None, grounder_factory=Owlv2GroundingProvider, batch_size=None,
                      on_batch=None):
    detector = detector or YoloDetectionProvider(str(evidence_root))
    vocabulary = [entity.entity_type or entity.name for entity in query.entities]
    supported = [value for value in vocabulary if detector.supported_labels([value])]
    grounded = [value for value in vocabulary if not detector.supported_labels([value])]
    batch_size = max(1, int(batch_size or len(frames) or 1))
    detections = []
    grounder = grounder_factory(str(evidence_root)) if grounded else None
    if not frames:
        detections.extend(detector.detect([], supported, session_id))
        if grounder:
            detections.extend(grounder.ground([], grounded, session_id))
        return detections, grounded
    for start in range(0, len(frames), batch_size):
        batch = frames[start:start + batch_size]
        detections.extend(detector.detect(batch, supported, session_id))
        if grounder:
            detections.extend(grounder.ground(batch, grounded, session_id))
        if on_batch:
            on_batch(min(len(frames), start + len(batch)), len(frames))
    return detections, grounded


def _extract_clip(video_path: str, start: float, end: float, destination: Path):
    if end <= start:
        raise ValueError("Result clip interval must have positive duration.")
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_suffix(".encoding.mp4")
    try:
        from imageio_ffmpeg import get_ffmpeg_exe
        max_width = max(320, int(os.environ.get("AIEYE_RESULT_CLIP_WIDTH", "1280")))
        command = [
            get_ffmpeg_exe(), "-hide_banner", "-loglevel", "error", "-y",
            "-ss", f"{start:.3f}", "-i", str(video_path), "-t", f"{end - start:.3f}",
            "-vf", f"scale='min({max_width},iw)':-2", "-an", "-c:v", "libx264",
            "-preset", "veryfast", "-crf", "23", "-pix_fmt", "yuv420p",
            "-movflags", "+faststart", str(temporary),
        ]
        subprocess.run(command, check=True, capture_output=True, timeout=180)
        if not temporary.is_file() or temporary.stat().st_size == 0:
            raise OSError("Browser-compatible result clip was not created.")
        os.replace(temporary, destination)
    except (OSError, subprocess.SubprocessError) as error:
        raise OSError("Could not create browser-compatible H.264 result clip.") from error
    finally:
        temporary.unlink(missing_ok=True)


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
        total_started = time.perf_counter()
        timings = {}
        checkpoint()
        with database.get_db_connection() as conn:
            row = conn.execute("SELECT * FROM sessions WHERE session_id=?", (session_id,)).fetchone()
            if not row or not row["video_metadata"]:
                raise ValueError("Session video metadata is missing.")
            video = VideoMetadata(**json.loads(row["video_metadata"]))
        query = StructuredQueryParser().parse(
            target_config.free_text_description, target_config.processing_mode,
        )
        profile = get_processing_profile(query.processing_mode)
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
        stage_started = time.perf_counter()
        index = VideoIndexer().build_or_reuse(video, query.processing_mode)
        timings["indexing"] = time.perf_counter() - stage_started
        checkpoint()
        with database.get_db_connection() as conn:
            conn.execute("UPDATE sessions SET index_id=? WHERE session_id=?", (index.index_id, session_id))
            conn.execute("UPDATE searches SET index_id=?,status='retrieving',started_at=CURRENT_TIMESTAMP WHERE search_id=?",
                         (index.index_id, search_id))
        cls._log(session_id, "VIDEO_INDEX", f"{'Reused' if index.cache_hit else 'Built'} index {index.index_id}.", "action")
        cls._status(session_id, 20, "semantic_retrieval")
        retrieval = SemanticRetrievalService()
        stage_started = time.perf_counter()
        candidates = retrieval.retrieve(
            index.index_id, query.original_text, limit=profile.retrieval_limit,
            search_id=search_id, owner_kinds=("frame", "clip"),
        )
        timings["semantic_retrieval"] = time.perf_counter() - stage_started
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
        has_plate_query = any(attribute.name == "license_plate" for entity in query.entities
                              for attribute in entity.attributes)
        frames = []
        if has_plate_query:
            # Text-specific searches must scan the timeline; image/text retrieval cannot reliably
            # distinguish one short alphanumeric identifier from another.
            frames = [CandidateFrame(
                frame_id=frame["frame_id"], frame_idx=frame["frame_idx"],
                timestamp_seconds=frame["timestamp_seconds"], image_path=frame["image_path"],
                semantic_similarity=0.0,
            ) for frame in frame_rows]
        else:
            for path, candidate in best_by_path.items():
                frame = frame_by_path.get(str(Path(path).resolve()))
                if frame:
                    frames.append(CandidateFrame(
                        frame_id=frame["frame_id"], frame_idx=frame["frame_idx"],
                        timestamp_seconds=frame["timestamp_seconds"], image_path=frame["image_path"],
                        semantic_similarity=candidate.semantic_similarity,
                    ))
                    if len(frames) >= profile.localization_frame_limit:
                        break
        frames.sort(key=lambda item: item.timestamp_seconds)
        cls._status(session_id, 50, "entity_localization")
        evidence_root = Path(database.DB_DIR) / "evidence"
        stage_started = time.perf_counter()
        detections, grounded = localize_entities(
            frames, query, session_id, evidence_root,
            batch_size=profile.localization_batch_size,
            on_batch=lambda complete, total: cls._status(
                session_id, 50 + 20 * complete / max(1, total), "entity_localization",
            ),
        )
        timings["entity_localization"] = time.perf_counter() - stage_started
        if grounded:
            cls._log(session_id, "GROUNDING", "Grounded open-vocabulary entities: " + ", ".join(grounded), "action")
        checkpoint()
        tracks = track_entities(detections)
        max_tracks = min(
            profile.result_track_limit,
            max(1, int(os.environ.get("AIEYE_MAX_RESULT_TRACKS", str(profile.result_track_limit)))),
        )
        if has_plate_query:
            max_tracks = max(max_tracks, int(os.environ.get("AIEYE_MAX_PLATE_TRACKS", "50")))
        tracks = sorted(tracks, key=lambda track: _track_priority(query, track), reverse=True)[:max_tracks]
        cls._status(session_id, 75, "evidence_ranking")
        stage_started = time.perf_counter()
        results = cls._rank(query, search_id, session_id, video, tracks, evidence_root,
                            retrieval.provider.provenance, result_limit=max_tracks)
        timings["evidence_ranking"] = time.perf_counter() - stage_started
        checkpoint()
        with database.get_db_connection() as conn:
            conn.execute("BEGIN IMMEDIATE")
            conn.executemany("""INSERT INTO search_results(search_id,result_id,start_seconds,end_seconds,
                classification,overall_score,payload) VALUES (?,?,?,?,?,?,?)""", [
                (search_id, result.result_id, result.start_seconds, result.end_seconds,
                 result.classification, result.overall_score, result.model_dump_json()) for result in results
            ])
            timings["total"] = time.perf_counter() - total_started
            metrics = {
                "stage_timings": {name: round(value, 6) for name, value in timings.items()},
                "cache_hit": index.cache_hit, "candidate_count": len(candidates),
                "localized_frame_count": len(frames), "detection_count": len(detections),
                "track_count": len(tracks), "result_count": len(results),
                "processing_profile": profile.__dict__,
                "actual_result_limit": max_tracks,
                "device": retrieval.provider.provenance.device,
            }
            conn.execute("UPDATE searches SET status='completed',finished_at=CURRENT_TIMESTAMP,metrics_json=? WHERE search_id=?",
                         (json.dumps(metrics), search_id))
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
              semantic_provenance: ModelProvenance, result_limit=None) -> List[SearchResult]:
        result_limit = max(1, int(result_limit or os.environ.get("AIEYE_MAX_RESULT_TRACKS", "10")))
        plate_constraints = [attribute for entity in query.entities for attribute in entity.attributes
                             if attribute.name == "license_plate"]
        if plate_constraints:
            cls._read_license_plates(session_id, tracks)
        needs_event_ranking = (
            len(query.entities) > 1 or query.actions or query.relationships
            or any((entity.quantity or 1) > 1 or entity.negative for entity in query.entities)
            or any(attribute.name != "color" for entity in query.entities for attribute in entity.attributes)
        )
        if needs_event_ranking:
            event_results = build_event_results(query, search_id, video.duration_seconds, tracks)
            if plate_constraints:
                requested = {normalize_plate(item.value) for item in plate_constraints}
                event_results = [result for result in event_results if result.classification == "strong_match"
                                 and requested.issubset({normalize_plate(reading.get("text", ""))
                                     for entity in result.entities for detection in entity.detections
                                     for reading in detection.attributes.get("license_plate_readings", [])})]
            return cls._materialize_events(
                event_results[:result_limit],
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

    @staticmethod
    def _read_license_plates(session_id, tracks, reader=None):
        reader = reader or LicensePlateReader()
        frame_cache = {}
        with database.get_db_connection() as conn:
            rows = conn.execute(
                "SELECT frame_id,image_path FROM indexed_frames WHERE index_id=(SELECT index_id FROM sessions WHERE session_id=?)",
                (session_id,),
            ).fetchall()
        paths = {row["frame_id"]: row["image_path"] for row in rows}
        for track in tracks:
            # Read several of the clearest/largest observations. Plate characters that are
            # ambiguous in one frame often become exact a frame later as the camera moves.
            selected = sorted(
                track,
                key=lambda item: ((item.bbox[2] - item.bbox[0]) * (item.bbox[3] - item.bbox[1]),
                                  item.visibility, item.confidence),
                reverse=True,
            )[:6]
            for detection in track:
                if detection not in selected:
                    detection.attributes["license_plate_readings"] = []
                    continue
                path = paths.get(detection.frame_id)
                if not path:
                    detection.attributes["license_plate_readings"] = []
                    continue
                if path not in frame_cache:
                    frame_cache[path] = cv2.imread(path)
                frame = frame_cache[path]
                readings = reader.read_vehicle(frame, detection.bbox) if frame is not None else []
                detection.attributes["license_plate_readings"] = [
                    {"text": item.text, "confidence": round(item.confidence, 4), "bbox": item.bbox}
                    for item in readings
                ]
                detection.attributes["license_plate_provenance"] = reader.provenance.model_dump()

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
                for reading in observation.attributes.get("license_plate_readings", []):
                    plate_bbox = reading.get("bbox", [])
                    if len(plate_bbox) != 4:
                        continue
                    px1, py1, px2, py2 = map(int, plate_bbox)
                    cv2.rectangle(image, (px1, py1), (px2, py2), (40, 255, 40), 4)
                    cv2.putText(image, reading.get("text", ""), (px1, max(30, py1 - 8)),
                                cv2.FONT_HERSHEY_SIMPLEX, .9, (40, 255, 40), 3)
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
