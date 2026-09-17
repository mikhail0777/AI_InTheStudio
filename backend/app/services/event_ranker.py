"""Build auditable multi-entity event candidates from localized tracks."""
from itertools import product
import os
from statistics import mean
from typing import Sequence
import uuid

from app.models.open_vocabulary import EntityTrack, EvidenceAssessment, SearchQuery, SearchResult
from app.services.temporal_verifier import MultiFrameEvidenceVerifier


def _matches(label, entity):
    expected = (entity.entity_type or entity.name).lower()
    aliases = {expected}
    if expected in {"woman", "man", "child", "someone"}:
        aliases.add("person")
    if expected == "vehicle":
        aliases.update({"car", "truck", "bus", "motorcycle"})
    return label.lower() in aliases


def _as_tracks(raw_tracks):
    counters = {}
    output = []
    for observations in raw_tracks:
        if not observations:
            continue
        label = observations[0].label
        counters[label] = counters.get(label, 0) + 1
        output.append(EntityTrack(
            track_id=f"{label}:{counters[label]}", label=label,
            start_seconds=min(item.timestamp_seconds for item in observations),
            end_seconds=max(item.timestamp_seconds for item in observations),
            detections=list(observations), attributes={},
        ))
    return output


def build_event_results(query: SearchQuery, search_id: str, duration: float,
                        raw_tracks: Sequence[Sequence]):
    tracks = _as_tracks(raw_tracks)
    per_entity = []
    limit = max(1, int(os.environ.get("AIEYE_MAX_TRACKS_PER_ENTITY", "12")))
    for entity in query.entities:
        matches = [track for track in tracks if _matches(track.label, entity)]
        matches.sort(key=lambda track: max(item.confidence for item in track.detections), reverse=True)
        if not matches:
            return []
        per_entity.append(matches[:limit])
    verifier = MultiFrameEvidenceVerifier()
    results = []
    max_combinations = max(1, int(os.environ.get("AIEYE_MAX_EVENT_COMBINATIONS", "500")))
    for combination_number, combination in enumerate(product(*per_entity)):
        if combination_number >= max_combinations:
            break
        if len({track.track_id for track in combination}) != len(combination):
            continue
        constraint_evidence = verifier.verify(query, combination)
        entity_evidence = []
        for entity, track in zip(query.entities, combination):
            entity_evidence.append(EvidenceAssessment(
                criterion_id=entity.entity_id, kind="entity", assessment="supported",
                score=max(item.confidence for item in track.detections),
                explanation=f"Localized {track.label} in {len(track.detections)} indexed observations.",
                timestamps=[item.timestamp_seconds for item in track.detections],
                entity_track_ids=[track.track_id],
                evidence_paths=[item.crop_path for item in track.detections if item.crop_path],
                provenance=track.detections[0].provenance,
            ))
        assessments = [item.assessment for item in constraint_evidence]
        if constraint_evidence and all(value == "supported" for value in assessments):
            classification = "strong_match"
        elif any(value == "conflicting" for value in assessments):
            classification = "unlikely_match"
        else:
            classification = "insufficient_visibility"
        constraint_score = mean(item.score or 0.0 for item in constraint_evidence) if constraint_evidence else 1.0
        entity_score = mean(max(item.confidence for item in track.detections) for track in combination)
        visibility = mean(max(item.visibility for item in track.detections) for track in combination)
        semantic = max(float(item.attributes.get("semantic_similarity", -1.0))
                       for track in combination for item in track.detections)
        semantic_score = max(0.0, min(1.0, (semantic + 1.0) / 2.0))
        overall = .3 * entity_score + .4 * constraint_score + .15 * visibility + .15 * semantic_score
        supported_times = [time for item in constraint_evidence if item.assessment == "supported" for time in item.timestamps]
        all_times = [item.timestamp_seconds for track in combination for item in track.detections]
        best_timestamp = supported_times[len(supported_times) // 2] if supported_times else all_times[len(all_times) // 2]
        first, last = min(all_times), max(all_times)
        provenance = {}
        for track in combination:
            for detection in track.detections:
                key = (detection.provenance.provider, detection.provenance.model_name,
                       detection.provenance.model_version)
                provenance[key] = detection.provenance
        provenance[(verifier.provenance.provider, verifier.provenance.model_name,
                    verifier.provenance.model_version)] = verifier.provenance
        explanation = (f"{classification.replace('_', ' ').title()}: "
                       + "; ".join(item.explanation for item in constraint_evidence))
        results.append(SearchResult(
            result_id=f"result_{uuid.uuid4().hex}", search_id=search_id,
            start_seconds=max(0.0, first - 1.5), end_seconds=min(duration, last + 1.5),
            best_timestamp_seconds=max(max(0.0, first - 1.5), min(best_timestamp, min(duration, last + 1.5))),
            classification=classification, overall_score=round(max(0.0, min(1.0, overall)), 4),
            component_scores={"entity_presence": round(entity_score, 4),
                              "action_relationship": round(constraint_score, 4),
                              "visibility": round(visibility, 4),
                              "semantic_similarity": round(semantic_score, 4)},
            entities=list(combination), evidence=entity_evidence + constraint_evidence,
            explanation=explanation, model_provenance=list(provenance.values()),
        ))
    ranked = sorted(results, key=lambda item: (
        item.classification == "strong_match", item.classification != "unlikely_match", item.overall_score
    ), reverse=True)
    deduplicated = []
    for result in ranked:
        duplicate = any(
            prior.entities[0].track_id == result.entities[0].track_id
            and min(prior.end_seconds, result.end_seconds) > max(prior.start_seconds, result.start_seconds)
            for prior in deduplicated
        )
        if not duplicate:
            deduplicated.append(result)
    return deduplicated
