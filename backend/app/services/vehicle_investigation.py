"""Plate-first dealership video investigation.

This path avoids semantic retrieval and sparse generic keyframes.  It scans the
recording at a declared cadence, keeps every credible OCR observation, groups
observations into sightings, and distinguishes exact evidence from review-only
OCR candidates.
"""
import json
import os
from pathlib import Path
import time
import uuid

import cv2

from app import database
from app.models.open_vocabulary import EntityDetection, EntityTrack, EvidenceAssessment, SearchResult
from app.models.schemas import TargetConfiguration, VideoMetadata
from app.services.generic_search import _extract_clip
from app.services.license_plate_reader import LicensePlateReader, normalize_plate, plate_similarity
from app.services.plate_consensus import build_plate_consensus
from app.services.plate_evidence import save_plate_derivatives
from app.services.query_parser import StructuredQueryParser
from app.services.vehicle_sightings import save_sighting
from app.services.vehicle_recognizer import VehicleRecognizer


MODE_SCAN_FPS = {"fast": 1.0, "balanced": 2.0, "thorough": 4.0}


def is_plate_investigation(query) -> bool:
    return any(
        attribute.name == "license_plate"
        for entity in query.entities
        for attribute in entity.attributes
    )


def _group_sightings(observations, maximum_gap_seconds=6.0):
    groups = []
    for observation in sorted(observations, key=lambda item: item["timestamp_seconds"]):
        if not groups or observation["timestamp_seconds"] - groups[-1][-1]["timestamp_seconds"] > maximum_gap_seconds:
            groups.append([observation])
        else:
            groups[-1].append(observation)
    return groups


def _distinct_frames(items):
    return len({item["frame_idx"] for item in items})


def _status(session_id, progress, stage):
    with database.get_db_connection() as conn:
        conn.execute(
            "UPDATE sessions SET progress_percent=?,current_stage=? "
            "WHERE session_id=? AND status='analyzing'",
            (progress, stage, session_id),
        )


class VehicleInvestigationManager:
    @staticmethod
    def _log(session_id, step, message, level="info"):
        from app.services.agentic_loop import AgenticLoopManager
        AgenticLoopManager.log_agent_event(session_id, step, message, level)

    @classmethod
    def execute_analysis(cls, session_id: str, target: TargetConfiguration, *, run_id: str, checkpoint):
        started = time.perf_counter()
        query = StructuredQueryParser().parse(target.free_text_description, target.processing_mode)
        plate_constraint = next((
            attribute for entity in query.entities for attribute in entity.attributes
            if attribute.name == "license_plate"
        ), None)
        requested_plate = normalize_plate(target.plate_number or (plate_constraint.value if plate_constraint else ""))
        if not 3 <= len(requested_plate) <= 10:
            raise ValueError("Enter 3-10 letters or numbers for a full or partial licence plate.")
        target = target.model_copy(update={"plate_number": requested_plate})
        context_constraints = [
            attribute for entity in query.entities for attribute in entity.attributes
            if attribute.name != "license_plate"
        ]
        with database.get_db_connection() as conn:
            session = conn.execute("SELECT video_metadata FROM sessions WHERE session_id=?", (session_id,)).fetchone()
        if not session or not session["video_metadata"]:
            raise ValueError("Session video metadata is missing.")
        video = VideoMetadata(**json.loads(session["video_metadata"]))
        search_id = f"search_{uuid.uuid4().hex}"
        with database.get_db_connection() as conn:
            conn.execute("BEGIN IMMEDIATE")
            conn.execute(
                """INSERT INTO searches(search_id,session_id,status,processing_mode,query_json,
                   parser_provenance,started_at) VALUES (?,?,?,?,?,?,CURRENT_TIMESTAMP)""",
                (search_id, session_id, "scanning_plates", query.processing_mode,
                 query.model_dump_json(), query.parser_provenance.model_dump_json()),
            )
            conn.execute(
                "UPDATE sessions SET search_id=?,search_query=? WHERE session_id=?",
                (search_id, query.model_dump_json(), session_id),
            )

        scan_fps = float(os.environ.get("AIEYE_PLATE_SCAN_FPS", MODE_SCAN_FPS[query.processing_mode]))
        if not 0.1 <= scan_fps <= 15:
            raise ValueError("AIEYE_PLATE_SCAN_FPS must be between 0.1 and 15.")
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
                [(run_id, index, index / video.fps, "plate_scan", "planned") for index in frame_indices],
            )

        cls._log(
            session_id, "PLATE_SCAN",
            f"Scanning {len(frame_indices)} frames at {scan_fps:g} FPS for plate {requested_plate}. Exact and review-only OCR evidence remain separate.",
            "action",
        )
        _status(session_id, 5, "plate_scan")
        reader = LicensePlateReader()
        vehicle_recognizer = VehicleRecognizer(str(Path(database.DB_DIR) / "evidence"))
        threshold = float(os.environ.get("AIEYE_PLATE_REVIEW_SIMILARITY", "0.78"))
        if not 0 <= threshold <= 1:
            raise ValueError("AIEYE_PLATE_REVIEW_SIMILARITY must be between 0 and 1.")
        plate_model_manifest = {
            "plate_reader": reader.provenance.model_dump(mode="json"),
            "review_similarity_threshold": threshold,
            "scan_fps": scan_fps,
            "consensus": {"name": "exact-string-independent-frame-v1", "top_k": 5},
        }
        evidence_dir = Path(database.DB_DIR) / "evidence" / session_id
        evidence_dir.mkdir(parents=True, exist_ok=True)
        observations = []
        cap = cv2.VideoCapture(video.filepath)
        if not cap.isOpened():
            raise ValueError("The video could not be opened for plate scanning.")
        try:
            for position, frame_idx in enumerate(frame_indices):
                if position % 8 == 0:
                    checkpoint()
                cap.set(cv2.CAP_PROP_POS_FRAMES, frame_idx)
                ok, frame = cap.read()
                if not ok or frame is None or frame.size == 0:
                    with database.get_db_connection() as conn:
                        conn.execute(
                            "UPDATE frame_samples SET status='failed' WHERE run_id=? AND frame_idx=?",
                            (run_id, frame_idx),
                        )
                    continue
                readings = reader.read_frame(frame, tiled=query.processing_mode != "fast")
                candidates = []
                for reading in readings:
                    normalized_read = normalize_plate(reading.text)
                    partial_match = target.plate_match_mode == "partial" and requested_plate in normalized_read
                    similarity = 1.0 if partial_match else plate_similarity(normalized_read, requested_plate)
                    if partial_match or similarity >= threshold:
                        candidates.append((reading, similarity))
                if candidates:
                    frame_path = evidence_dir / f"plate_source_{frame_idx:09d}.jpg"
                    if not cv2.imwrite(str(frame_path), frame, [cv2.IMWRITE_JPEG_QUALITY, 94]):
                        raise OSError("Could not save plate evidence frame.")
                    for candidate_position, (reading, similarity) in enumerate(candidates):
                        derivatives = save_plate_derivatives(
                            frame, reading.bbox, evidence_dir,
                            f"plate_{frame_idx:09d}_{candidate_position:02d}",
                        )
                        raw_candidate = {
                            "text": reading.text, "confidence": reading.confidence,
                            "source_variant": reading.source_variant,
                        }
                        candidate_values = [raw_candidate]
                        if hasattr(reader, "read_crop"):
                            candidate_values.extend({
                                "text": item.text, "confidence": item.confidence,
                                "source_variant": item.source_variant,
                            } for item in reader.read_crop(
                                derivatives["enhanced_image"], source_variant="enhanced_crop"
                            ))
                        best_candidate = max(
                            candidate_values,
                            key=lambda item: (
                                plate_similarity(item["text"], requested_plate), item["confidence"]
                            ),
                        )
                        normalized_best = normalize_plate(best_candidate["text"])
                        best_partial = target.plate_match_mode == "partial" and requested_plate in normalized_best
                        observations.append({
                            "frame_idx": frame_idx,
                            "timestamp_seconds": frame_idx / video.fps,
                            "frame_path": str(frame_path),
                            "text": best_candidate["text"],
                            "confidence": best_candidate["confidence"],
                            "similarity": 1.0 if best_partial else plate_similarity(normalized_best, requested_plate),
                            "bbox": reading.bbox,
                            "source_variant": best_candidate["source_variant"],
                            "exact": target.plate_match_mode == "exact" and normalized_best == requested_plate,
                            "partial": best_partial,
                            "candidates": candidate_values,
                            "quality_score": derivatives["metrics"]["quality_score"],
                            "quality_metrics": derivatives["metrics"],
                            "raw_plate_crop_reference": f"/evidence/{session_id}/{Path(derivatives['raw_path']).name}",
                            "enhanced_plate_crop_reference": f"/evidence/{session_id}/{Path(derivatives['enhanced_path']).name}",
                        })
                with database.get_db_connection() as conn:
                    conn.execute(
                        "UPDATE frame_samples SET status='sampled' WHERE run_id=? AND frame_idx=?",
                        (run_id, frame_idx),
                    )
                _status(session_id, 5 + 75 * (position + 1) / max(1, len(frame_indices)), "plate_scan")
        finally:
            cap.release()

        checkpoint()
        _status(session_id, 82, "evidence_review")
        results = []
        for sighting_number, sighting in enumerate(_group_sightings(observations), start=1):
            consensus = build_plate_consensus(sighting)
            repeated_candidate = consensus["selected_plate"] or sighting[0]["text"]
            repeated_frames = (consensus["ranked_candidates"][0]["distinct_frames"]
                               if consensus["ranked_candidates"] else 0)
            exact = [item for item in sighting if any(
                normalize_plate(candidate["text"]) == requested_plate
                for candidate in item.get("candidates") or []
            )]
            exact_frames = _distinct_frames(exact)
            partial = [item for item in sighting if any(
                requested_plate in normalize_plate(candidate["text"])
                for candidate in item.get("candidates") or []
            )]
            partial_frames = _distinct_frames(partial)
            selected_matches = (
                repeated_candidate == requested_plate if target.plate_match_mode == "exact"
                else requested_plate in repeated_candidate
            )
            strong = consensus["state"] == "exact_consensus" and selected_matches
            classification = "strong_match" if strong else "possible_match"
            supporting = [item for item in sighting if any(
                normalize_plate(candidate["text"]) == repeated_candidate
                for candidate in item.get("candidates") or []
            )] or sighting
            best = max(supporting, key=lambda item: (
                item["quality_score"], item["similarity"], item["confidence"]
            ))
            confidence = max(
                candidate["confidence"] for item in sighting
                for candidate in item.get("candidates") or []
            )
            repeat_support = min(1.0, max(exact_frames, repeated_frames) / 3.0)
            score = min(1.0, 0.62 * best["similarity"] + 0.23 * confidence + 0.15 * repeat_support)
            if not strong:
                score = min(score, 0.89)

            image = cv2.imread(best["frame_path"])
            if image is None:
                continue
            vehicle = vehicle_recognizer.recognize(
                image_path=best["frame_path"], plate_bbox=best["bbox"], session_id=session_id,
                frame_idx=best["frame_idx"], timestamp_seconds=best["timestamp_seconds"],
            )
            if vehicle is None:
                strong = False
                classification = "possible_match"
            x1, y1, x2, y2 = best["bbox"]
            color = (44, 170, 70) if strong else (0, 170, 255)
            if vehicle:
                vx1, vy1, vx2, vy2 = map(int, vehicle.bbox)
                cv2.rectangle(image, (vx1, vy1), (vx2, vy2), (220, 150, 40), 3)
                vehicle_label = vehicle.category
                if vehicle.color:
                    vehicle_label = f"{vehicle.color} {vehicle_label}"
                cv2.putText(
                    image, vehicle_label.upper(), (max(0, vx1), max(28, vy1 - 10)),
                    cv2.FONT_HERSHEY_SIMPLEX, .65, (220, 150, 40), 2,
                )
            cv2.rectangle(image, (x1, y1), (x2, y2), color, 4)
            cv2.putText(
                image, f"{repeated_candidate} {'MATCH' if strong else 'REVIEW'}",
                (max(0, x1), max(28, y1 - 10)), cv2.FONT_HERSHEY_SIMPLEX, .8, color, 2,
            )
            annotated = evidence_dir / f"plate_sighting_{sighting_number:03d}.jpg"
            if not cv2.imwrite(str(annotated), image, [cv2.IMWRITE_JPEG_QUALITY, 94]):
                raise OSError("Could not save annotated plate evidence.")
            first, last = sighting[0]["timestamp_seconds"], sighting[-1]["timestamp_seconds"]
            clip_start, clip_end = max(0.0, first - 2.5), min(video.duration_seconds, last + 2.5)
            if clip_end <= clip_start:
                clip_end = min(video.duration_seconds, clip_start + 0.5)
            clip = evidence_dir / f"plate_sighting_{sighting_number:03d}.mp4"
            _extract_clip(video.filepath, clip_start, clip_end, clip)

            detections = [EntityDetection(
                detection_id=f"plate_{item['frame_idx']}_{position}", frame_idx=item["frame_idx"],
                timestamp_seconds=item["timestamp_seconds"], label=vehicle.category if vehicle else "licence_plate",
                bbox=vehicle.bbox if vehicle else item["bbox"],
                confidence=max(0.0, min(1.0, item["confidence"])), visibility=max(.1, item["similarity"]),
                attributes={
                    "license_plate_readings": item.get("candidates") or [],
                    "requested_plate": requested_plate,
                    "plate_similarity": item["similarity"],
                    "plate_match_kind": ("exact" if item["exact"] else
                                         "partial" if item.get("partial") else "review_candidate"),
                    "vehicle_detected": vehicle is not None,
                    "vehicle_category": vehicle.category if vehicle else None,
                    "vehicle_color": vehicle.color if vehicle else None,
                    "vehicle_color_distribution": vehicle.colors if vehicle else {},
                },
                provenance=vehicle.provenance if vehicle else reader.provenance,
            ) for position, item in enumerate(sighting)]
            track = EntityTrack(
                track_id=f"vehicle-sighting-{sighting_number}", label="vehicle",
                start_seconds=first, end_seconds=last, detections=detections,
                attributes={
                    "requested_plate": requested_plate,
                    "plate_consensus": consensus,
                    "plate_match_mode": target.plate_match_mode, "camera_name": target.camera_name,
                    "camera_role": target.camera_role,
                    "vehicle_detected": vehicle is not None,
                    "vehicle_color": vehicle.color if vehicle else None,
                    "vehicle_body_type": vehicle.category if vehicle else None,
                    "requested_vehicle_make": target.vehicle_make,
                    "requested_vehicle_model": target.vehicle_model,
                    "requested_vehicle_year": target.vehicle_year,
                    "requested_vehicle_color": target.vehicle_color,
                    "requested_vehicle_body_type": target.vehicle_body_type,
                },
            )
            if strong and target.plate_match_mode == "exact":
                explanation = (
                    f"Plate {requested_plate} was selected by exact-string consensus across "
                    f"{repeated_frames} distinct sampled frame(s). "
                    f"Review the saved clip before using this result as evidence."
                )
                assessment = "supported"
            elif strong and target.plate_match_mode == "partial":
                explanation = (
                    f"Partial plate {requested_plate} appears within OCR read {repeated_candidate} in "
                    f"{partial_frames} distinct sampled frame(s). Confirm the full plate in the saved clip."
                )
                assessment = "supported"
            else:
                explanation = (
                    f"Possible OCR match for {requested_plate}: top candidate {repeated_candidate}; "
                    f"consensus state {consensus['state'].replace('_', ' ')}. "
                    "This is not a confirmed exact plate identity."
                )
                assessment = "uncertain"
            if vehicle:
                description = " ".join(value for value in (vehicle.color, vehicle.category) if value)
                explanation += f" The plate is associated with a detected {description or 'vehicle'}."
            else:
                explanation += " No containing vehicle was detected, so this result remains review-only."
            plate_evidence = EvidenceAssessment(
                criterion_id=plate_constraint.criterion_id if plate_constraint else "vehicle-1.license_plate",
                kind="attribute", assessment=assessment,
                score=round(best["similarity"], 4), explanation=explanation,
                timestamps=[item["timestamp_seconds"] for item in sighting],
                entity_track_ids=[track.track_id], evidence_paths=[f"/evidence/{session_id}/{annotated.name}"],
                provenance=reader.provenance,
            )
            evidence = [plate_evidence]
            for constraint in context_constraints:
                evidence.append(EvidenceAssessment(
                    criterion_id=constraint.criterion_id, kind="attribute", assessment="uncertain",
                    score=None,
                    explanation=(
                        f"Requested {constraint.name.replace('_', ' ')} '{constraint.value}' is context only in the plate-first MVP. "
                        "Verify it visually in the saved frame and original footage."
                    ),
                    timestamps=[best["timestamp_seconds"]], entity_track_ids=[track.track_id],
                    evidence_paths=[f"/evidence/{session_id}/{annotated.name}"],
                ))
            result_id = f"result_{uuid.uuid4().hex}"
            frame_url = f"/evidence/{session_id}/{annotated.name}"
            clip_url = f"/evidence/{session_id}/{clip.name}"
            results.append(SearchResult(
                result_id=result_id, search_id=search_id,
                start_seconds=clip_start, end_seconds=clip_end,
                best_timestamp_seconds=best["timestamp_seconds"], classification=classification,
                overall_score=round(score, 4),
                component_scores={"plate_similarity": round(best["similarity"], 4),
                                  "ocr_confidence": round(confidence, 4),
                                  "multi_frame_support": round(repeat_support, 4)},
                entities=[track], evidence=evidence, explanation=explanation,
                best_frame_path=frame_url, clip_path=clip_url,
                model_provenance=[reader.provenance] + ([vehicle.provenance] if vehicle else []),
            ))
            save_sighting(
                session_id=session_id, search_id=search_id, result_id=result_id, target=target,
                video=video, observation={**best, "text": repeated_candidate},
                first_seen=first, last_seen=last,
                frame_path=frame_url, clip_path=clip_url,
                match_kind=("exact_consensus" if strong and target.plate_match_mode == "exact"
                            else "partial_consensus" if strong else "review_candidate"),
                vehicle=vehicle,
                plate_analysis={
                    "consensus": consensus,
                    "best_observation": best,
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
                    } for item in sighting],
                },
            )

        results.sort(key=lambda item: (item.classification == "strong_match", item.overall_score), reverse=True)
        metrics = {
            "stage_timings": {"total": round(time.perf_counter() - started, 6)},
            "scan_fps": scan_fps, "frames_planned": len(frame_indices),
            "ocr_review_observations": len(observations), "result_count": len(results),
            "requested_plate": requested_plate,
        }
        with database.get_db_connection() as conn:
            conn.execute("BEGIN IMMEDIATE")
            conn.executemany(
                """INSERT INTO search_results(search_id,result_id,start_seconds,end_seconds,
                   classification,overall_score,payload) VALUES (?,?,?,?,?,?,?)""",
                [(search_id, item.result_id, item.start_seconds, item.end_seconds,
                  item.classification, item.overall_score, item.model_dump_json()) for item in results],
            )
            conn.execute(
                "UPDATE searches SET status='completed',finished_at=CURRENT_TIMESTAMP,metrics_json=? WHERE search_id=?",
                (json.dumps(metrics), search_id),
            )
            conn.execute(
                "UPDATE analysis_runs SET status='completed',finished_at=CURRENT_TIMESTAMP WHERE run_id=?",
                (run_id,),
            )
            conn.execute(
                """UPDATE sessions SET status='completed',progress_percent=100,current_stage='completed'
                   WHERE session_id=? AND run_id=? AND status='analyzing'""",
                (session_id, run_id),
            )
        cls._log(
            session_id, "COMPLETE",
            f"Plate investigation completed with {len(results)} sighting(s); {sum(item.classification == 'strong_match' for item in results)} have repeated or high-confidence plate support.",
        )
        return results
