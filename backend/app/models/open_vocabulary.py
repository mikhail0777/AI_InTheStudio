"""Provider-neutral contracts for open-vocabulary video search."""
from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field, model_validator


ProcessingMode = Literal["fast", "balanced", "thorough"]
Assessment = Literal["supported", "conflicting", "missing", "uncertain", "unsupported"]
ResultClassification = Literal[
    "strong_match", "possible_match", "unlikely_match",
    "insufficient_visibility", "unsupported_query",
]


class ModelProvenance(BaseModel):
    provider: str
    model_name: str
    model_version: str
    device: str = "unknown"
    metadata: Dict[str, Any] = Field(default_factory=dict)


class AttributeConstraint(BaseModel):
    criterion_id: str
    entity_id: str
    name: str
    value: str
    required: bool = True
    negative: bool = False


class EntityMention(BaseModel):
    entity_id: str
    name: str
    entity_type: Optional[str] = None
    quantity: Optional[int] = Field(default=None, ge=1)
    required: bool = True
    negative: bool = False
    attributes: List[AttributeConstraint] = Field(default_factory=list)


class RelationshipConstraint(BaseModel):
    criterion_id: str
    subject_entity_id: str
    predicate: str
    object_entity_id: str
    required: bool = True
    negative: bool = False


class ActionConstraint(BaseModel):
    criterion_id: str
    actor_entity_id: str
    action: str
    object_entity_id: Optional[str] = None
    requires_temporal_evidence: bool = True
    required: bool = True
    negative: bool = False


class EventStep(BaseModel):
    step_id: str
    order: int = Field(ge=0)
    description: str
    actor_entity_id: Optional[str] = None
    action: Optional[str] = None
    object_entity_id: Optional[str] = None


class SearchQuery(BaseModel):
    original_text: str = Field(min_length=1, max_length=4000)
    entities: List[EntityMention] = Field(default_factory=list)
    relationships: List[RelationshipConstraint] = Field(default_factory=list)
    actions: List[ActionConstraint] = Field(default_factory=list)
    event_sequence: List[EventStep] = Field(default_factory=list)
    required_evidence_ids: List[str] = Field(default_factory=list)
    optional_evidence_ids: List[str] = Field(default_factory=list)
    unsupported_concepts: List[str] = Field(default_factory=list)
    processing_mode: ProcessingMode = "balanced"
    parser_provenance: Optional[ModelProvenance] = None

    @model_validator(mode="after")
    def validate_references(self):
        entity_ids = [entity.entity_id for entity in self.entities]
        if len(entity_ids) != len(set(entity_ids)):
            raise ValueError("entity_id values must be unique")
        known_entities = set(entity_ids)
        criteria = []
        for entity in self.entities:
            criteria.extend(attribute.criterion_id for attribute in entity.attributes)
            for attribute in entity.attributes:
                if attribute.entity_id != entity.entity_id:
                    raise ValueError("attribute entity_id must match its containing entity")
        for relation in self.relationships:
            criteria.append(relation.criterion_id)
            if relation.subject_entity_id not in known_entities or relation.object_entity_id not in known_entities:
                raise ValueError("relationship references an unknown entity")
        for action in self.actions:
            criteria.append(action.criterion_id)
            refs = [action.actor_entity_id, action.object_entity_id]
            if any(ref is not None and ref not in known_entities for ref in refs):
                raise ValueError("action references an unknown entity")
        for step in self.event_sequence:
            refs = [step.actor_entity_id, step.object_entity_id]
            if any(ref is not None and ref not in known_entities for ref in refs):
                raise ValueError("event step references an unknown entity")
        if len(criteria) != len(set(criteria)):
            raise ValueError("criterion_id values must be unique")
        known_criteria = set(criteria) | known_entities
        requested = self.required_evidence_ids + self.optional_evidence_ids
        if len(requested) != len(set(requested)):
            raise ValueError("evidence IDs must be unique across required and optional evidence")
        if any(item not in known_criteria for item in requested):
            raise ValueError("evidence ID references an unknown entity or criterion")
        return self


class EntityDetection(BaseModel):
    detection_id: str
    frame_id: Optional[str] = None
    frame_idx: int = Field(ge=0)
    timestamp_seconds: float = Field(ge=0)
    label: str
    bbox: List[float] = Field(min_length=4, max_length=4)
    confidence: float = Field(ge=0, le=1)
    visibility: float = Field(default=1, ge=0, le=1)
    mask_path: Optional[str] = None
    crop_path: Optional[str] = None
    attributes: Dict[str, Any] = Field(default_factory=dict)
    provenance: ModelProvenance


class EntityTrack(BaseModel):
    track_id: str
    label: str
    start_seconds: float = Field(ge=0)
    end_seconds: float = Field(ge=0)
    detections: List[EntityDetection] = Field(default_factory=list)
    attributes: Dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_interval(self):
        if self.end_seconds < self.start_seconds:
            raise ValueError("track end_seconds must not precede start_seconds")
        return self


class EvidenceAssessment(BaseModel):
    criterion_id: str
    kind: Literal["entity", "attribute", "action", "relationship", "temporal", "quality"]
    assessment: Assessment
    score: Optional[float] = Field(default=None, ge=0, le=1)
    explanation: str
    timestamps: List[float] = Field(default_factory=list)
    entity_track_ids: List[str] = Field(default_factory=list)
    evidence_paths: List[str] = Field(default_factory=list)
    provenance: Optional[ModelProvenance] = None


class SearchResult(BaseModel):
    result_id: str
    search_id: str
    start_seconds: float = Field(ge=0)
    end_seconds: float = Field(ge=0)
    best_timestamp_seconds: float = Field(ge=0)
    classification: ResultClassification
    overall_score: float = Field(ge=0, le=1)
    component_scores: Dict[str, float] = Field(default_factory=dict)
    entities: List[EntityTrack] = Field(default_factory=list)
    evidence: List[EvidenceAssessment] = Field(default_factory=list)
    explanation: str
    best_frame_path: Optional[str] = None
    clip_path: Optional[str] = None
    model_provenance: List[ModelProvenance] = Field(default_factory=list)
    human_feedback: Optional[Literal["confirmed", "rejected", "needs_research"]] = None
    human_notes: Optional[str] = None

    @model_validator(mode="after")
    def validate_interval(self):
        if self.end_seconds < self.start_seconds:
            raise ValueError("result end_seconds must not precede start_seconds")
        if not self.start_seconds <= self.best_timestamp_seconds <= self.end_seconds:
            raise ValueError("best timestamp must fall inside the result interval")
        if any(not 0 <= value <= 1 for value in self.component_scores.values()):
            raise ValueError("component scores must be between zero and one")
        return self


class SemanticCandidate(BaseModel):
    candidate_id: str
    index_id: str
    owner_kind: Literal["frame", "clip"]
    owner_id: str
    timestamp_seconds: float = Field(ge=0)
    semantic_similarity: float = Field(ge=-1, le=1)
    rank: int = Field(ge=1)
    artifact_path: str
    metadata: Dict[str, Any] = Field(default_factory=dict)
