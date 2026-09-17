"""Label-driven search evaluation with explicit denominators and honest missing metrics."""
import math
from typing import Dict, List, Optional

from pydantic import BaseModel, Field, model_validator

from app.models.open_vocabulary import SearchResult


class LabeledBox(BaseModel):
    timestamp_seconds: float = Field(ge=0, allow_inf_nan=False)
    label: str = Field(min_length=1, max_length=200)
    bbox: List[float] = Field(min_length=4, max_length=4)

    @model_validator(mode="after")
    def validate_bbox(self):
        if not all(math.isfinite(value) for value in self.bbox):
            raise ValueError("bbox coordinates must be finite")
        if self.bbox[2] <= self.bbox[0] or self.bbox[3] <= self.bbox[1]:
            raise ValueError("bbox must have positive width and height")
        return self


class GroundTruthEvent(BaseModel):
    event_id: str = Field(min_length=1, max_length=200)
    start_seconds: float = Field(ge=0, allow_inf_nan=False)
    end_seconds: float = Field(ge=0, allow_inf_nan=False)
    required_labels: List[str] = Field(default_factory=list, max_length=32)
    conditions: List[str] = Field(default_factory=list, max_length=32)
    boxes: List[LabeledBox] = Field(default_factory=list, max_length=5000)

    @model_validator(mode="after")
    def validate_interval(self):
        if self.end_seconds < self.start_seconds:
            raise ValueError("end_seconds must be greater than or equal to start_seconds")
        return self


class EvaluationCounts(BaseModel):
    ground_truth_events: int
    retrieved_events: int
    matched_events: int
    promoted_results: int
    false_positive_results: int
    labeled_boxes: int
    localized_boxes: int


class EvaluationMetrics(BaseModel):
    candidate_retrieval_recall: Optional[float] = None
    event_recall: Optional[float] = None
    promoted_false_positive_rate: Optional[float] = None
    event_localization_iou: Optional[float] = None
    box_localization_recall_at_50_iou: Optional[float] = None
    mean_box_iou: Optional[float] = None
    mean_reciprocal_rank: Optional[float] = None
    condition_recall: Dict[str, Optional[float]] = Field(default_factory=dict)


class EvaluationReport(BaseModel):
    counts: EvaluationCounts
    metrics: EvaluationMetrics
    notes: List[str] = Field(default_factory=list)


def _interval_iou(left_start, left_end, right_start, right_end):
    intersection = max(0.0, min(left_end, right_end) - max(left_start, right_start))
    union = max(left_end, right_end) - min(left_start, right_start)
    return intersection / union if union > 0 else float(left_start == right_start)


def _box_iou(left, right):
    intersection = max(0.0, min(left[2], right[2]) - max(left[0], right[0])) * max(
        0.0, min(left[3], right[3]) - max(left[1], right[1])
    )
    left_area = max(0.0, left[2] - left[0]) * max(0.0, left[3] - left[1])
    right_area = max(0.0, right[2] - right[0]) * max(0.0, right[3] - right[1])
    return intersection / max(1.0, left_area + right_area - intersection)


def evaluate_results(events: List[GroundTruthEvent], results: List[SearchResult],
                     candidate_timestamps: List[float], temporal_iou_threshold=.1,
                     box_time_tolerance=.6) -> EvaluationReport:
    promoted = [item for item in results if item.classification in {"strong_match", "possible_match"}]
    ranked = sorted(results, key=lambda item: item.overall_score, reverse=True)
    retrieved = {
        event.event_id for event in events
        if any(event.start_seconds <= timestamp <= event.end_seconds for timestamp in candidate_timestamps)
    }
    matched = {}
    used_results = set()
    reciprocal_ranks = []
    for event in events:
        choices = [(index, result, _interval_iou(
            event.start_seconds, event.end_seconds, result.start_seconds, result.end_seconds,
        )) for index, result in enumerate(ranked, start=1)
                   if result in promoted and result.result_id not in used_results
                   and all(
                       any(entity.label.lower() == required.lower() for entity in result.entities)
                       for required in event.required_labels
                   )]
        choices = [item for item in choices if item[2] >= temporal_iou_threshold]
        if choices:
            rank, result, overlap = max(choices, key=lambda item: (item[2], -item[0]))
            matched[event.event_id] = (result, overlap)
            used_results.add(result.result_id)
            reciprocal_ranks.append(1.0 / rank)

    box_ious = []
    localized = 0
    for event in events:
        match = matched.get(event.event_id)
        for truth in event.boxes:
            best = 0.0
            if match:
                for entity in match[0].entities:
                    if entity.label.lower() != truth.label.lower():
                        continue
                    for detection in entity.detections:
                        if abs(detection.timestamp_seconds - truth.timestamp_seconds) <= box_time_tolerance:
                            best = max(best, _box_iou(truth.bbox, detection.bbox))
            box_ious.append(best)
            localized += best >= .5

    conditions = sorted({condition for event in events for condition in event.conditions})
    condition_recall = {}
    for condition in conditions:
        selected = [event for event in events if condition in event.conditions]
        condition_recall[condition] = (
            sum(event.event_id in matched for event in selected) / len(selected) if selected else None
        )
    false_positives = sum(item.result_id not in used_results for item in promoted)
    notes = []
    if not events:
        notes.append("Recall and localization were not measured because no ground-truth events were supplied.")
    if not promoted:
        notes.append("False-positive rate was not measured because no results were promoted.")
    if not box_ious:
        notes.append("Box localization was not measured because no labeled boxes were supplied.")
    return EvaluationReport(
        counts=EvaluationCounts(
            ground_truth_events=len(events), retrieved_events=len(retrieved), matched_events=len(matched),
            promoted_results=len(promoted), false_positive_results=false_positives,
            labeled_boxes=len(box_ious), localized_boxes=localized,
        ),
        metrics=EvaluationMetrics(
            candidate_retrieval_recall=len(retrieved) / len(events) if events else None,
            event_recall=len(matched) / len(events) if events else None,
            promoted_false_positive_rate=false_positives / len(promoted) if promoted else None,
            event_localization_iou=(sum(value[1] for value in matched.values()) / len(matched)
                                    if matched else None),
            box_localization_recall_at_50_iou=localized / len(box_ious) if box_ious else None,
            mean_box_iou=sum(box_ious) / len(box_ious) if box_ious else None,
            mean_reciprocal_rank=sum(reciprocal_ranks) / len(events) if events else None,
            condition_recall=condition_recall,
        ),
        notes=notes,
    )
