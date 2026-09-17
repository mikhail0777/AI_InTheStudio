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


def _matching_tracks(entity, tracks: Sequence[EntityTrack]):
    expected = (entity.entity_type or entity.name).lower()
    aliases = {expected}
    if expected in {"woman", "man", "child", "someone"}:
        aliases.add("person")
    if expected == "vehicle":
        aliases.update({"car", "truck", "bus", "motorcycle"})
    return [track for track in tracks if track.label.lower() in aliases]


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
                    for left in subject.detections:
                        for right in obj.detections:
                            if abs(left.timestamp_seconds - right.timestamp_seconds) > 1.1:
                                continue
                            distance = math.dist(_center(left), _center(right)) / max(_diagonal(left), _diagonal(right))
                            if distance <= 2.0:
                                close_times.append((left.timestamp_seconds + right.timestamp_seconds) / 2)
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
