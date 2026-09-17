"""Conservative multi-frame evidence checks for localized entity tracks."""
import math
from typing import Dict, Sequence

from app.models.open_vocabulary import EntityTrack, EvidenceAssessment, ModelProvenance, SearchQuery


def _center(detection):
    x1, y1, x2, y2 = detection.bbox
    return (x1 + x2) / 2, (y1 + y2) / 2


def _diagonal(detection):
    x1, y1, x2, y2 = detection.bbox
    return max(1.0, math.hypot(x2 - x1, y2 - y1))


def _overlap(left, right):
    intersection = max(0.0, min(left.bbox[2], right.bbox[2]) - max(left.bbox[0], right.bbox[0])) * max(
        0.0, min(left.bbox[3], right.bbox[3]) - max(left.bbox[1], right.bbox[1])
    )
    left_area = max(1.0, (left.bbox[2] - left.bbox[0]) * (left.bbox[3] - left.bbox[1]))
    right_area = max(1.0, (right.bbox[2] - right.bbox[0]) * (right.bbox[3] - right.bbox[1]))
    return intersection / min(left_area, right_area)


def _matching_tracks(entity, tracks: Sequence[EntityTrack]):
    expected = (entity.entity_type or entity.name).lower()
    aliases = {expected}
    if expected in {"woman", "man", "child", "someone"}:
        aliases.add("person")
    if expected == "vehicle":
        aliases.update({"car", "truck", "bus", "motorcycle"})
    return [track for track in tracks if track.label.lower() in aliases]


def _paired_observations(left: EntityTrack, right: EntityTrack, maximum_gap=1.1):
    pairs = []
    for first in left.detections:
        choices = [second for second in right.detections
                   if abs(first.timestamp_seconds - second.timestamp_seconds) <= maximum_gap]
        if choices:
            pairs.append((first, min(choices, key=lambda item: abs(first.timestamp_seconds - item.timestamp_seconds))))
    return pairs


def _association(left: EntityTrack, right: EntityTrack):
    pairs = _paired_observations(left, right)
    close = []
    for first, second in pairs:
        distance = math.dist(_center(first), _center(second)) / max(_diagonal(first), _diagonal(second))
        if distance <= 2.0:
            close.append((first, second, distance))
    return close


def _co_motion(close):
    if len(close) < 2:
        return 0.0
    first_left, first_right, _ = close[0]
    last_left, last_right, _ = close[-1]
    actor = (_center(last_left)[0] - _center(first_left)[0], _center(last_left)[1] - _center(first_left)[1])
    obj = (_center(last_right)[0] - _center(first_right)[0], _center(last_right)[1] - _center(first_right)[1])
    actor_length, object_length = math.hypot(*actor), math.hypot(*obj)
    scale = max(_diagonal(first_left), _diagonal(first_right), _diagonal(last_left), _diagonal(last_right))
    if actor_length / scale < .12 or object_length / scale < .12:
        return 0.0
    return (actor[0] * obj[0] + actor[1] * obj[1]) / max(1.0, actor_length * object_length)


class MultiFrameEvidenceVerifier:
    """Geometry/motion verifier that refuses unsupported interaction claims."""

    @property
    def provenance(self):
        return ModelProvenance(
            provider="local-deterministic", model_name="multi-frame-geometry-verifier",
            model_version="1", device="cpu",
            metadata={"minimum_temporal_observations": 2},
        )

    def verify(self, query: SearchQuery, tracks: Sequence[EntityTrack]):
        by_id: Dict[str, Sequence[EntityTrack]] = {
            entity.entity_id: _matching_tracks(entity, tracks) for entity in query.entities
        }
        evidence = []
        for relationship in query.relationships:
            subjects, objects = by_id.get(relationship.subject_entity_id, []), by_id.get(relationship.object_entity_id, [])
            close_times = []
            for subject in subjects:
                for obj in objects:
                    close_times.extend((left.timestamp_seconds + right.timestamp_seconds) / 2
                                       for left, right, _ in _association(subject, obj))
            distinct = sorted({round(value, 2) for value in close_times})
            if len(distinct) >= 2 and relationship.predicate in {"near", "beside", "behind"}:
                assessment, score = "supported", min(1.0, .55 + .1 * len(distinct))
                explanation = f"The requested entities remain spatially associated in {len(distinct)} sampled moments."
            elif subjects and objects:
                assessment, score = "conflicting", 0.0
                explanation = "Both entities were localized, but repeated spatial association was not observed."
            else:
                assessment, score = "missing", None
                explanation = "One or both entities required for the relationship were not localized."
            evidence.append(EvidenceAssessment(
                criterion_id=relationship.criterion_id, kind="relationship", assessment=assessment,
                score=score, explanation=explanation, timestamps=distinct,
                entity_track_ids=[track.track_id for track in subjects + objects], provenance=self.provenance,
            ))
        for action in query.actions:
            actors = by_id.get(action.actor_entity_id, [])
            objects = by_id.get(action.object_entity_id, []) if action.object_entity_id else []
            timestamps = sorted({round(item.timestamp_seconds, 2) for track in actors for item in track.detections})
            assessment, score = "uncertain", None
            explanation = "The action requires multi-frame interaction evidence that was not established."
            if not actors or (action.object_entity_id and not objects):
                assessment = "missing"
                explanation = "An entity required for the action was not localized."
            elif action.action == "running" and any(self._normalized_motion(track) >= .75 for track in actors):
                assessment, score = "supported", .7
                explanation = "The actor has sustained multi-frame displacement consistent with running; human review is required."
            elif action.action == "pushing" and objects:
                associations = [(actor, obj, _association(actor, obj)) for actor in actors for obj in objects]
                best = max(associations, key=lambda item: (
                    sum(_overlap(left, right) >= .03 for left, right, _ in item[2]),
                    len(item[2]), _co_motion(item[2])), default=None)
                contact_count = (sum(_overlap(left, right) >= .03 for left, right, _ in best[2])
                                 if best else 0)
                if best and len(best[2]) >= 2 and contact_count >= 2 and _co_motion(best[2]) >= .3:
                    assessment, score = "supported", min(.95, .7 + .04 * contact_count)
                    timestamps = sorted({round((left.timestamp_seconds + right.timestamp_seconds) / 2, 2)
                                         for left, right, _ in best[2] if _overlap(left, right) >= .03})
                    explanation = "Person and stroller remain in contact and move together across multiple sampled moments."
                elif best and len(best[2]) >= 2:
                    assessment, score = "uncertain", .35
                    explanation = "Person and stroller are nearby, but repeated contact and coordinated motion are not both clear."
                else:
                    assessment, score = "conflicting", 0.0
                    explanation = "Person and stroller were not repeatedly associated in the sampled moments."
            evidence.append(EvidenceAssessment(
                criterion_id=action.criterion_id, kind="action", assessment=assessment,
                score=score, explanation=explanation, timestamps=timestamps,
                entity_track_ids=[track.track_id for track in actors + objects], provenance=self.provenance,
            ))
        return evidence

    @staticmethod
    def _normalized_motion(track: EntityTrack):
        detections = sorted(track.detections, key=lambda item: item.timestamp_seconds)
        if len(detections) < 3 or detections[-1].timestamp_seconds - detections[0].timestamp_seconds < .5:
            return 0.0
        return math.dist(_center(detections[0]), _center(detections[-1])) / max(
            _diagonal(detections[0]), _diagonal(detections[-1])
        )
