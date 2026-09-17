"""Compatibility mapping from the person-search API to generic search contracts."""
from typing import List

from app.models.open_vocabulary import (
    AttributeConstraint, EntityDetection, EntityMention, EntityTrack, EvidenceAssessment,
    ModelProvenance, SearchQuery, SearchResult,
)
from app.models.schemas import TargetConfiguration, TrackResult


def target_to_search_query(target: TargetConfiguration, processing_mode: str = "balanced") -> SearchQuery:
    text = target.free_text_description.strip() or "Locate a person."
    attributes: List[AttributeConstraint] = []
    required_ids: List[str] = ["person"]
    optional_ids: List[str] = []
    fields = (
        ("upper_clothing_type", target.upper_clothing_type),
        ("upper_clothing_color", target.upper_clothing_color),
        ("sleeve_length", target.sleeve_length),
        ("lower_clothing_type", target.lower_clothing_type),
        ("lower_clothing_color", target.lower_clothing_color),
        ("shoe_color", target.shoe_color),
        ("hair_color", target.hair_color),
        ("hair_length", target.hair_length),
        ("body_build", target.body_build),
        ("backpack", target.backpack),
        ("hat", target.hat),
        ("eyewear", target.eyewear),
        ("footwear_type", target.footwear_type),
        ("posture", target.posture),
        ("other_accessories", target.other_accessories),
        ("distinctive_features", target.distinctive_features),
    )
    explicitly_required = set(target.required_attributes)
    explicitly_optional = set(target.optional_attributes)
    explicitly_negative = set(target.negative_attributes)
    for name, raw_value in fields:
        if not raw_value:
            continue
        value = raw_value.strip()
        negative = value.lower().startswith(("not ", "without ")) or value in explicitly_negative
        criterion_id = f"person.{name}"
        required = name in explicitly_required or name not in explicitly_optional
        attributes.append(AttributeConstraint(
            criterion_id=criterion_id, entity_id="person", name=name, value=value,
            required=required, negative=negative,
        ))
        (required_ids if required else optional_ids).append(criterion_id)
    # Preserve unstructured legacy constraints without pretending they were parsed.
    represented = {name for name, value in fields if value}
    unsupported = [item for item in target.required_attributes + target.optional_attributes + target.negative_attributes
                   if item not in represented]
    return SearchQuery(
        original_text=text,
        entities=[EntityMention(entity_id="person", name="person", entity_type="person", attributes=attributes)],
        required_evidence_ids=required_ids,
        optional_evidence_ids=optional_ids,
        unsupported_concepts=unsupported,
        processing_mode=processing_mode,
        parser_provenance=ModelProvenance(
            provider="legacy-adapter", model_name="target-configuration-adapter", model_version="1",
            device="cpu",
        ),
    )


def track_to_search_result(track: TrackResult, search_id: str) -> SearchResult:
    provenance = ModelProvenance(
        provider="legacy-person-pipeline", model_name="person-appearance-pipeline",
        model_version=track.model_version or "unknown", device="unknown",
    )
    detections = [EntityDetection(
        detection_id=item.detection_id, frame_idx=item.frame_idx,
        timestamp_seconds=item.timestamp_seconds, label="person", bbox=item.bbox,
        confidence=item.confidence, visibility=item.quality_score,
        mask_path=item.mask_path, crop_path=item.crop_path,
        attributes={"color_features": item.color_features, "attribute_visibility": item.attribute_visibility},
        provenance=ModelProvenance(
            provider="legacy-detector", model_name=item.detector_name,
            model_version=item.model_version or "unknown", device="unknown",
        ),
    ) for item in track.evidence_observations]
    entity = EntityTrack(
        track_id=f"person:{track.track_id}", label="person",
        start_seconds=track.first_seen_seconds, end_seconds=track.last_seen_seconds,
        detections=detections,
        attributes={name: detail.model_dump(mode="json") for name, detail in track.attributes.items()},
    )
    evidence = []
    assessment_map = {"match": "supported", "conflict": "conflicting", "unknown": "uncertain"}
    for name, detail in track.attributes.items():
        evidence.append(EvidenceAssessment(
            criterion_id=f"person.{name}", kind="attribute",
            assessment=assessment_map[detail.assessment], score=detail.score,
            explanation=f"Expected {detail.expected}; observed {detail.observed}.",
            timestamps=detail.evidence_timestamps, entity_track_ids=[entity.track_id],
            evidence_paths=detail.evidence_paths, provenance=provenance,
        ))
    return SearchResult(
        result_id=f"legacy-track:{track.track_id}", search_id=search_id,
        start_seconds=track.first_seen_seconds, end_seconds=track.last_seen_seconds,
        best_timestamp_seconds=track.best_timestamp_seconds,
        classification=track.classification,
        overall_score=track.final_ranking_score,
        component_scores={
            "entity_presence": track.person_detection_confidence,
            "attribute_agreement": track.appearance_similarity,
            "visibility": track.evidence_quality,
        },
        entities=[entity], evidence=evidence, explanation=track.explanation,
        best_frame_path=track.best_frame_path, model_provenance=[provenance],
        human_feedback=track.human_feedback, human_notes=track.human_notes,
    )
