"""Build auditable multi-entity event candidates from localized tracks."""
from itertools import product
import os
from statistics import mean
from typing import Sequence
import uuid

from app.models.open_vocabulary import EntityTrack, EvidenceAssessment, ModelProvenance, SearchQuery, SearchResult
from app.services.temporal_verifier import MultiFrameEvidenceVerifier
from app.services.visual_features import color_match_score
from app.services.license_plate_reader import normalize_plate


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


def _associated(left, right):
    for first in left.detections:
        for second in right.detections:
            if abs(first.timestamp_seconds - second.timestamp_seconds) > 1.1:
                continue
            ax, ay = (first.bbox[0] + first.bbox[2]) / 2, (first.bbox[1] + first.bbox[3]) / 2
            bx, by = (second.bbox[0] + second.bbox[2]) / 2, (second.bbox[1] + second.bbox[3]) / 2
            scale = max(1.0, ((first.bbox[2] - first.bbox[0]) ** 2 + (first.bbox[3] - first.bbox[1]) ** 2) ** .5)
            if ((ax - bx) ** 2 + (ay - by) ** 2) ** .5 / scale <= 2.0:
                return True
    return False


def _attribute_evidence(entity, selected):
    evidence = []
    detections = [item for track in selected for item in track.detections]
    for attribute in entity.attributes:
        scores, raw_scores = [], []
        if attribute.name == "color":
            for detection in detections:
                score, raw = color_match_score(attribute.value, detection.attributes.get("colors", {}))
                scores.append(score)
                raw_scores.append(raw)
            support, raw = max(scores, default=0.0), max(raw_scores, default=0.0)
            if attribute.negative:
                assessment = "supported" if raw < .05 else ("conflicting" if raw >= .18 else "uncertain")
                explanation = f"Excluded {attribute.value}; strongest localized color coverage was {round(raw * 100)}%."
                score = 1.0 - support
            else:
                assessment = "supported" if support >= .30 and raw >= .18 else (
                    "conflicting" if raw < .05 else "uncertain"
                )
                explanation = f"Requested {attribute.value}; strongest localized color coverage was {round(raw * 100)}%."
                score = support
        elif attribute.name == "license_plate":
            expected = normalize_plate(attribute.value)
            readings = [reading for detection in detections
                        for reading in detection.attributes.get("license_plate_readings", [])]
            exact = [reading for reading in readings if normalize_plate(reading.get("text", "")) == expected]
            if exact:
                assessment, score = "supported", max(float(item.get("confidence", 0.0)) for item in exact)
                explanation = f"License plate {expected} was read in {len(exact)} localized observation(s)."
            elif readings:
                assessment, score = "conflicting", 0.0
                observed = ", ".join(sorted({normalize_plate(item.get("text", "")) for item in readings}))
                explanation = f"Requested plate {expected}; OCR read {observed or 'different text'}."
            else:
                assessment, score = "uncertain", None
                explanation = f"Requested plate {expected}, but no plate text was readable."
            scores = [score or 0.0 for _ in detections]
        else:
            assessment, score = "uncertain", None
            explanation = f"The visible attribute '{attribute.value}' has no specialized verifier yet."
        evidence_provenance = detections[0].provenance if detections else None
        if attribute.name == "license_plate" and detections:
            serialized = next((item.attributes.get("license_plate_provenance") for item in detections
                               if item.attributes.get("license_plate_provenance")), None)
            if serialized:
                evidence_provenance = ModelProvenance(**serialized)
        evidence.append(EvidenceAssessment(
            criterion_id=attribute.criterion_id, kind="attribute", assessment=assessment,
            score=score, explanation=explanation,
            timestamps=([item.timestamp_seconds for item in detections
                         if any(normalize_plate(reading.get("text", "")) == normalize_plate(attribute.value)
                                for reading in item.attributes.get("license_plate_readings", []))]
                        if attribute.name == "license_plate" else
                        [item.timestamp_seconds for item, value in zip(detections, scores) if value >= .3]),
            entity_track_ids=[track.track_id for track in selected],
            evidence_paths=[item.crop_path for item in detections if item.crop_path],
            provenance=evidence_provenance,
        ))
    return evidence


def build_event_results(query: SearchQuery, search_id: str, duration: float,
                        raw_tracks: Sequence[Sequence]):
    tracks = _as_tracks(raw_tracks)
    positive_entities = [entity for entity in query.entities if not entity.negative]
    negative_entities = [entity for entity in query.entities if entity.negative]
    if not positive_entities:
        return []
    slots = [entity for entity in positive_entities for _ in range(entity.quantity or 1)]
    per_entity = []
    limit = max(1, int(os.environ.get("AIEYE_MAX_TRACKS_PER_ENTITY", "12")))
    for entity in slots:
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
        selected_by_entity = {entity.entity_id: [] for entity in positive_entities}
        for entity, track in zip(slots, combination):
            selected_by_entity[entity.entity_id].append(track)
        for entity in positive_entities:
            selected = selected_by_entity[entity.entity_id]
            detections = [item for track in selected for item in track.detections]
            entity_evidence.append(EvidenceAssessment(
                criterion_id=entity.entity_id, kind="entity", assessment="supported",
                score=mean(item.confidence for item in detections),
                explanation=(f"Localized {len(selected)} required {entity.entity_type or entity.name} track(s) "
                             f"in {len(detections)} indexed observations."),
                timestamps=[item.timestamp_seconds for item in detections],
                entity_track_ids=[track.track_id for track in selected],
                evidence_paths=[item.crop_path for item in detections if item.crop_path],
                provenance=detections[0].provenance,
            ))
            constraint_evidence.extend(_attribute_evidence(entity, selected))
        primary_tracks = selected_by_entity[positive_entities[0].entity_id] if positive_entities else []
        for entity in negative_entities:
            excluded = [track for track in tracks if _matches(track.label, entity)]
            conflicts = [track for track in excluded if any(_associated(primary, track) for primary in primary_tracks)]
            assessment = "conflicting" if conflicts else "supported"
            constraint_evidence.append(EvidenceAssessment(
                criterion_id=entity.entity_id, kind="entity", assessment=assessment,
                score=0.0 if conflicts else 1.0,
                explanation=(f"Found {len(conflicts)} associated excluded {entity.entity_type or entity.name} track(s)."
                             if conflicts else f"No associated {entity.entity_type or entity.name} was localized in sampled moments."),
                timestamps=[item.timestamp_seconds for track in conflicts for item in track.detections],
                entity_track_ids=[track.track_id for track in conflicts],
                evidence_paths=[item.crop_path for track in conflicts for item in track.detections if item.crop_path],
                provenance=conflicts[0].detections[0].provenance if conflicts else verifier.provenance,
            ))
        assessments = [item.assessment for item in constraint_evidence]
        if constraint_evidence and all(value == "supported" for value in assessments):
            classification = "strong_match"
        elif any(value == "conflicting" for value in assessments):
            classification = "unlikely_match"
        elif constraint_evidence:
            classification = "insufficient_visibility"
        else:
            classification = "strong_match" if all(len(track.detections) >= 2 for track in combination) else "possible_match"
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
        for track in combination:
            for detection in track.detections:
                serialized = detection.attributes.get("license_plate_provenance")
                if serialized:
                    plate_provenance = ModelProvenance(**serialized)
                    provenance[(plate_provenance.provider, plate_provenance.model_name,
                                plate_provenance.model_version)] = plate_provenance
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
        result_track_ids = {entity.track_id for entity in result.entities}
        duplicate = any(
            result_track_ids.intersection(entity.track_id for entity in prior.entities)
            and min(prior.end_seconds, result.end_seconds) > max(prior.start_seconds, result.start_seconds)
            for prior in deduplicated
        )
        if not duplicate:
            deduplicated.append(result)
    return deduplicated
