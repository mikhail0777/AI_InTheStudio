"""Dense dealership vehicle search when no licence plate is known."""
from __future__ import annotations

import json
from pathlib import Path
import time
import uuid

import cv2

from app import database
from app.models.open_vocabulary import EntityDetection, EntityTrack, EvidenceAssessment, SearchResult
from app.models.schemas import TargetConfiguration, VideoMetadata
from app.services.generic_search import _extract_clip
from app.services.license_plate_reader import LicensePlateReader
from app.services.plate_evidence import save_plate_derivatives
from app.services.plate_profiles import get_plate_profile
from app.services.plate_track_consensus import build_track_plate_consensus, plate_observation_score
from app.services.query_parser import StructuredQueryParser
from app.services.vehicle_investigation import MODE_SCAN_FPS, _status
from app.services.vehicle_recognizer import VehicleObservation, VehicleRecognizer
from app.services.vehicle_attribute_consensus import build_vehicle_attribute_consensus
from app.services.vehicle_sightings import save_sighting
from app.services.visual_features import color_match_score


def is_vehicle_profile_search(target: TargetConfiguration) -> bool:
    return not target.plate_number and any((
        target.vehicle_make, target.vehicle_model, target.vehicle_year,
        target.vehicle_color, target.vehicle_body_type,
    ))


def _plate_belongs_to_vehicle(vehicle_bbox, plate_bbox) -> bool:
    """Require the plate centre to fall inside the detected vehicle."""
    plate_x = (plate_bbox[0] + plate_bbox[2]) / 2
    plate_y = (plate_bbox[1] + plate_bbox[3]) / 2
    return (
        vehicle_bbox[0] <= plate_x <= vehicle_bbox[2]
        and vehicle_bbox[1] <= plate_y <= vehicle_bbox[3]
    )


def _iou(left, right) -> float:
    x1, y1 = max(left[0], right[0]), max(left[1], right[1])
    x2, y2 = min(left[2], right[2]), min(left[3], right[3])
    intersection = max(0.0, x2 - x1) * max(0.0, y2 - y1)
    left_area = max(0.0, left[2] - left[0]) * max(0.0, left[3] - left[1])
    right_area = max(0.0, right[2] - right[0]) * max(0.0, right[3] - right[1])
    return intersection / max(1.0, left_area + right_area - intersection)


def _group_tracks(observations, maximum_gap_seconds=4.0, minimum_iou=.15):
    active, completed = [], []
    for item in sorted(observations, key=lambda value: value["timestamp_seconds"]):
        expired = [track for track in active
                   if item["timestamp_seconds"] - track[-1]["timestamp_seconds"] > maximum_gap_seconds]
        completed.extend(expired)
        active = [track for track in active if track not in expired]
        choices = [
            (_iou(track[-1]["vehicle"].bbox, item["vehicle"].bbox), track)
            for track in active
            if track[-1]["frame_idx"] != item["frame_idx"]
            and track[-1]["vehicle"].category == item["vehicle"].category
        ]
        choices.sort(key=lambda value: value[0], reverse=True)
        if choices and choices[0][0] >= minimum_iou:
            choices[0][1].append(item)
        else:
            active.append([item])
    return completed + active


def _category_matches(requested: str | None, observed: str) -> bool:
    if not requested:
        return True
    value = requested.lower()
    if "motorcycle" in value:
        return observed == "motorcycle"
    if "truck" in value or "pickup" in value:
        return observed == "truck"
    if "van" in value or any(name in value for name in ("sedan", "suv", "crossover", "coupe", "hatchback", "wagon", "convertible")):
        return observed in {"car", "truck"}
    return observed in {"car", "truck", "bus", "motorcycle"}


def _requested_color(value: str | None) -> str | None:
    if not value:
        return None
    normalized = value.lower().replace("gray", "grey")
    aliases = {"silver": "grey", "burgundy": "red", "maroon": "red",
               "teal": "blue", "turquoise": "blue", "gold": "yellow", "bronze": "brown"}
    for source, target in aliases.items():
        if source in normalized:
            return target
    return normalized


class VehicleScanManager:
    @staticmethod
    def _log(session_id, step, message, level="info"):
        from app.services.agentic_loop import AgenticLoopManager
        AgenticLoopManager.log_agent_event(session_id, step, message, level)

    @classmethod
    def execute_analysis(cls, session_id: str, target: TargetConfiguration, *, run_id: str, checkpoint):
        started = time.perf_counter()
        query = StructuredQueryParser().parse(target.free_text_description, target.processing_mode)
        with database.get_db_connection() as conn:
            session = conn.execute("SELECT video_metadata FROM sessions WHERE session_id=?", (session_id,)).fetchone()
        if not session or not session["video_metadata"]:
            raise ValueError("Session video metadata is missing.")
        video = VideoMetadata(**json.loads(session["video_metadata"]))
        search_id = f"search_{uuid.uuid4().hex}"
        with database.get_db_connection() as conn:
            conn.execute(
                """INSERT INTO searches(search_id,session_id,status,processing_mode,query_json,
                   parser_provenance,started_at) VALUES (?,?,?,?,?,?,CURRENT_TIMESTAMP)""",
                (search_id, session_id, "scanning_vehicles", query.processing_mode,
                 query.model_dump_json(), query.parser_provenance.model_dump_json()),
            )
            conn.execute("UPDATE sessions SET search_id=?,search_query=? WHERE session_id=?",
                         (search_id, query.model_dump_json(), session_id))

        scan_fps = MODE_SCAN_FPS[query.processing_mode]
        interval = max(1, round(video.fps / scan_fps))
        start_frame = max(0, int((target.search_start_seconds or 0) * video.fps))
        end_seconds = target.search_end_seconds if target.search_end_seconds is not None else video.duration_seconds
        end_frame = min(video.frame_count - 1, int(end_seconds * video.fps)) if video.frame_count else -1
        if end_frame < start_frame:
            raise ValueError("The search end time must be after the search start time and inside the recording.")
        frame_indices = list(range(start_frame, end_frame + 1, interval))
        if end_frame >= 0 and (not frame_indices or frame_indices[-1] != end_frame):
            frame_indices.append(end_frame)
        with database.get_db_connection() as conn:
            conn.executemany(
                "INSERT OR REPLACE INTO frame_samples(run_id,frame_idx,timestamp_seconds,stage,status) VALUES (?,?,?,?,?)",
                [(run_id, index, index / video.fps, "vehicle_scan", "planned") for index in frame_indices],
            )

        evidence_dir = Path(database.DB_DIR) / "evidence" / session_id
        evidence_dir.mkdir(parents=True, exist_ok=True)
        recognizer = VehicleRecognizer(str(Path(database.DB_DIR) / "evidence"))
        plate_reader = LicensePlateReader() if target.inventory_scan else None
        region_profile = get_plate_profile("unknown")
        plate_model_manifest = ({
            "plate_reader": plate_reader.provenance.model_dump(mode="json"),
            "consensus": {"name": "adaptive-quality-temporal-diversity-v1", "top_k": 5},
            "region_profile": {"name": region_profile.name, "format_rules_are_ranking_only": True},
        } if plate_reader else {})
        observations = []
        cap = cv2.VideoCapture(video.filepath)
        if not cap.isOpened():
            raise ValueError("The video could not be opened for vehicle scanning.")
        cls._log(session_id, "VEHICLE_SCAN",
                 f"Scanning {len(frame_indices)} frames at {scan_fps:g} FPS for vehicles.", "action")
        _status(session_id, 5, "vehicle_scan")
        try:
            for position, frame_idx in enumerate(frame_indices):
                if position % 8 == 0:
                    checkpoint()
                cap.set(cv2.CAP_PROP_POS_FRAMES, frame_idx)
                ok, frame = cap.read()
                if not ok or frame is None or frame.size == 0:
                    continue
                source = evidence_dir / f"vehicle_source_{frame_idx:09d}.jpg"
                if not cv2.imwrite(str(source), frame, [cv2.IMWRITE_JPEG_QUALITY, 92]):
                    raise OSError("Could not save vehicle evidence frame.")
                detected = recognizer.recognize_all(
                    image_path=str(source), session_id=session_id, frame_idx=frame_idx,
                    timestamp_seconds=frame_idx / video.fps,
                )
                kept = [item for item in detected if _category_matches(target.vehicle_body_type, item.category)]
                frame_plate_readings = plate_reader.read_frame(frame, tiled=True) if plate_reader else []
                if not kept:
                    source.unlink(missing_ok=True)
                for vehicle_position, item in enumerate(kept):
                    plate_observations = []
                    associated = [reading for reading in frame_plate_readings
                                  if _plate_belongs_to_vehicle(item.bbox, reading.bbox)]
                    for plate_position, reading in enumerate(associated):
                        derivatives = save_plate_derivatives(
                            frame, reading.bbox, evidence_dir,
                            f"inventory_plate_{frame_idx:09d}_{vehicle_position:02d}_{plate_position:02d}",
                        )
                        candidates = [{
                            "text": reading.text, "confidence": reading.confidence,
                            "source_variant": reading.source_variant,
                        }]
                        candidates.extend({
                            "text": candidate.text, "confidence": candidate.confidence,
                            "source_variant": candidate.source_variant,
                        } for candidate in plate_reader.read_crop(
                            derivatives["enhanced_image"], source_variant="enhanced_crop"
                        ))
                        plate_observations.append({
                            "frame_idx": frame_idx,
                            "timestamp_seconds": frame_idx / video.fps,
                            "frame_path": str(source),
                            "bbox": list(reading.bbox),
                            "text": reading.text,
                            "confidence": reading.confidence,
                            "candidates": candidates,
                            "quality_score": derivatives["metrics"]["quality_score"],
                            "quality_metrics": derivatives["metrics"],
                            "raw_plate_crop_reference": f"/evidence/{session_id}/{Path(derivatives['raw_path']).name}",
                            "enhanced_plate_crop_reference": f"/evidence/{session_id}/{Path(derivatives['enhanced_path']).name}",
                        })
                    observations.append({
                        "frame_idx": frame_idx, "timestamp_seconds": frame_idx / video.fps,
                        "frame_path": str(source), "vehicle": item,
                        "plate_observations": plate_observations,
                    })
                with database.get_db_connection() as conn:
                    conn.execute("UPDATE frame_samples SET status='sampled' WHERE run_id=? AND frame_idx=?",
                                 (run_id, frame_idx))
                _status(session_id, 5 + 75 * (position + 1) / max(1, len(frame_indices)), "vehicle_scan")
        finally:
            cap.release()

        checkpoint()
        requested_color = _requested_color(target.vehicle_color)
        results = []
        for number, track_items in enumerate(_group_tracks(observations), start=1):
            plate_observations = [plate for item in track_items
                                  for plate in item.get("plate_observations", [])]
            plate_consensus, _ = build_track_plate_consensus(
                plate_observations, profile=region_profile,
            )
            selected_plate = plate_consensus.get("selected_plate")
            best_plate = (max(plate_observations, key=plate_observation_score)
                          if plate_observations else None)
            attribute_consensus = build_vehicle_attribute_consensus([{
                "frame_idx": item["frame_idx"],
                "quality_score": item["vehicle"].confidence,
                "candidates": list(item["vehicle"].make_model_candidates),
            } for item in track_items])
            scored = [(color_match_score(requested_color, item["vehicle"].colors)[0]
                       if requested_color else 1.0, item) for item in track_items]
            best_color_score, best = max(scored, key=lambda value: (value[0], value[1]["vehicle"].confidence))
            if requested_color and best_color_score < .35:
                continue
            distinct_frames = len({item["frame_idx"] for item in track_items})
            strong = distinct_frames >= 2 and (not requested_color or best_color_score >= .55)
            vehicle: VehicleObservation = best["vehicle"]
            image = cv2.imread(best["frame_path"])
            if image is None:
                continue
            x1, y1, x2, y2 = map(int, vehicle.bbox)
            color = (44, 170, 70) if strong else (0, 170, 255)
            cv2.rectangle(image, (x1, y1), (x2, y2), color, 4)
            description = " ".join(value for value in (vehicle.color, vehicle.category) if value)
            display_label = " · ".join(value for value in (description, selected_plate) if value)
            cv2.putText(image, (display_label or "vehicle").upper(), (max(0, x1), max(28, y1 - 10)),
                        cv2.FONT_HERSHEY_SIMPLEX, .7, color, 2)
            annotated = evidence_dir / f"vehicle_sighting_{number:03d}.jpg"
            if not cv2.imwrite(str(annotated), image, [cv2.IMWRITE_JPEG_QUALITY, 94]):
                raise OSError("Could not save annotated vehicle evidence.")
            first, last = track_items[0]["timestamp_seconds"], track_items[-1]["timestamp_seconds"]
            clip_start, clip_end = max(0.0, first - 2.5), min(video.duration_seconds, last + 2.5)
            if clip_end <= clip_start:
                clip_end = min(video.duration_seconds, clip_start + .5)
            clip = evidence_dir / f"vehicle_sighting_{number:03d}.mp4"
            _extract_clip(video.filepath, clip_start, clip_end, clip)
            detections = [EntityDetection(
                detection_id=f"vehicle_{item['frame_idx']}_{index}", frame_idx=item["frame_idx"],
                timestamp_seconds=item["timestamp_seconds"], label=item["vehicle"].category,
                bbox=item["vehicle"].bbox, confidence=item["vehicle"].confidence,
                visibility=max(.1, item["vehicle"].color_confidence),
                crop_path=item["vehicle"].crop_path, mask_path=item["vehicle"].mask_path,
                attributes={"vehicle_detected": True, "vehicle_color": item["vehicle"].color,
                            "vehicle_body_type": item["vehicle"].category,
                            "vehicle_color_distribution": item["vehicle"].colors},
                provenance=item["vehicle"].provenance,
            ) for index, item in enumerate(track_items)]
            track = EntityTrack(
                track_id=f"vehicle-sighting-{number}", label="vehicle", start_seconds=first,
                end_seconds=last, detections=detections,
                attributes={"vehicle_detected": True, "vehicle_color": vehicle.color,
                            "vehicle_body_type": vehicle.category,
                            "observed_plate": selected_plate,
                            "plate_consensus": plate_consensus,
                            "vehicle_attribute_consensus": attribute_consensus,
                            "vehicle_make_model": attribute_consensus["selected"],
                            "requested_vehicle_make": target.vehicle_make,
                            "requested_vehicle_model": target.vehicle_model,
                            "requested_vehicle_year": target.vehicle_year,
                            "requested_vehicle_color": target.vehicle_color,
                            "requested_vehicle_body_type": target.vehicle_body_type},
            )
            selected_attributes = attribute_consensus["selected"]
            if selected_attributes:
                years = (f", estimated {selected_attributes['year_start']}-{selected_attributes['year_end']}"
                         if selected_attributes.get("year_start") is not None else "")
                attribute_text = (
                    f" Candidate consensus: {selected_attributes['make']} "
                    f"{selected_attributes['model']}{years}; requires benchmark validation."
                )
            else:
                attribute_text = " Make, model and year are unknown and require visual confirmation."
            explanation = (f"Detected a {description or 'vehicle'} in {distinct_frames} sampled frame(s)."
                           + attribute_text)
            evidence = [EvidenceAssessment(
                criterion_id="vehicle-1", kind="entity", assessment="supported" if strong else "uncertain",
                score=vehicle.confidence, explanation=explanation,
                timestamps=[item["timestamp_seconds"] for item in track_items],
                entity_track_ids=[track.track_id], evidence_paths=[f"/evidence/{session_id}/{annotated.name}"],
                provenance=vehicle.provenance,
            )]
            if plate_observations:
                evidence.append(EvidenceAssessment(
                    criterion_id="vehicle-1.plate", kind="attribute",
                    assessment=("supported" if plate_consensus["state"] == "exact_consensus"
                                else "uncertain"),
                    score=plate_consensus.get("decision_score", 0.0),
                    explanation=(f"Multi-frame OCR selected {selected_plate}. "
                                 f"{plate_consensus['reason'].replace('_', ' ')}."),
                    timestamps=[item["timestamp_seconds"] for item in plate_observations],
                    entity_track_ids=[track.track_id],
                    evidence_paths=[best_plate["raw_plate_crop_reference"]] if best_plate else [],
                    provenance=plate_reader.provenance if plate_reader else None,
                ))
            if requested_color:
                evidence.append(EvidenceAssessment(
                    criterion_id="vehicle-1.color", kind="attribute",
                    assessment="supported" if best_color_score >= .55 else "uncertain",
                    score=round(best_color_score, 4),
                    explanation=f"Observed colour evidence compared with requested {target.vehicle_color}.",
                    timestamps=[best["timestamp_seconds"]], entity_track_ids=[track.track_id],
                    evidence_paths=[f"/evidence/{session_id}/{annotated.name}"], provenance=vehicle.provenance,
                ))
            result_id = f"result_{uuid.uuid4().hex}"
            score = min(1.0, .6 * vehicle.confidence + .25 * best_color_score + .15 * min(1, distinct_frames / 3))
            result = SearchResult(
                result_id=result_id, search_id=search_id, start_seconds=clip_start, end_seconds=clip_end,
                best_timestamp_seconds=best["timestamp_seconds"],
                classification="strong_match" if strong else "possible_match", overall_score=round(score, 4),
                component_scores={"vehicle_confidence": round(vehicle.confidence, 4),
                                  "color_support": round(best_color_score, 4),
                                  "multi_frame_support": round(min(1, distinct_frames / 3), 4),
                                  "plate_consensus": round(plate_consensus.get("decision_score", 0.0), 4)},
                entities=[track], evidence=evidence, explanation=explanation,
                best_frame_path=f"/evidence/{session_id}/{annotated.name}",
                clip_path=f"/evidence/{session_id}/{clip.name}",
                model_provenance=[vehicle.provenance] + ([plate_reader.provenance] if plate_reader else []),
            )
            results.append(result)
            save_sighting(
                session_id=session_id, search_id=search_id, result_id=result_id, target=target, video=video,
                observation={
                    "text": selected_plate or "",
                    "confidence": max((candidate.get("confidence", 0.0)
                                       for item in plate_observations
                                       for candidate in item.get("candidates", [])), default=0.0),
                    "similarity": plate_consensus.get("decision_score", 0.0),
                    "timestamp_seconds": best["timestamp_seconds"],
                },
                first_seen=first, last_seen=last, frame_path=result.best_frame_path,
                clip_path=result.clip_path,
                match_kind=("exact_consensus" if plate_consensus["state"] == "exact_consensus"
                            else "review_candidate" if plate_observations else "vehicle_only"),
                vehicle=vehicle,
                plate_analysis=({
                    "consensus": plate_consensus,
                    "best_observation": best_plate,
                    "observations": [{
                        "frame_idx": item["frame_idx"],
                        "timestamp_seconds": item["timestamp_seconds"],
                        "source_frame_reference": f"/evidence/{session_id}/{Path(item['frame_path']).name}",
                        "bbox": item["bbox"],
                        "raw_plate_crop_reference": item["raw_plate_crop_reference"],
                        "enhanced_plate_crop_reference": item["enhanced_plate_crop_reference"],
                        "quality_metrics": item["quality_metrics"],
                        "candidates": item["candidates"],
                        "model_manifest": plate_model_manifest,
                    } for item in plate_observations],
                } if plate_observations else None),
                vehicle_attributes=attribute_consensus,
            )

        results.sort(key=lambda item: (item.classification == "strong_match", item.overall_score), reverse=True)
        metrics = {"stage_timings": {"total": round(time.perf_counter() - started, 6)},
                   "scan_fps": scan_fps, "frames_planned": len(frame_indices),
                   "vehicle_observations": len(observations),
                   "plate_observations": sum(len(item.get("plate_observations", [])) for item in observations),
                   "result_count": len(results)}
        with database.get_db_connection() as conn:
            conn.execute("BEGIN IMMEDIATE")
            conn.executemany(
                """INSERT INTO search_results(search_id,result_id,start_seconds,end_seconds,
                   classification,overall_score,payload) VALUES (?,?,?,?,?,?,?)""",
                [(search_id, item.result_id, item.start_seconds, item.end_seconds,
                  item.classification, item.overall_score, item.model_dump_json()) for item in results],
            )
            conn.execute("UPDATE searches SET status='completed',finished_at=CURRENT_TIMESTAMP,metrics_json=? WHERE search_id=?",
                         (json.dumps(metrics), search_id))
            conn.execute("UPDATE analysis_runs SET status='completed',finished_at=CURRENT_TIMESTAMP WHERE run_id=?",
                         (run_id,))
            conn.execute("""UPDATE sessions SET status='completed',progress_percent=100,current_stage='completed'
                          WHERE session_id=? AND run_id=? AND status='analyzing'""", (session_id, run_id))
        cls._log(session_id, "COMPLETE", f"Vehicle scan completed with {len(results)} sighting(s).")
        return results
