"""Associate licence-plate evidence with a detected vehicle.

The plate reader only localizes and transcribes plates.  This service uses the
existing COCO segmentation model to prove that a plate belongs to a detected
vehicle and to extract conservative, mask-based appearance observations.
"""
from dataclasses import dataclass
import os
from pathlib import Path
from typing import Optional, Sequence

from app.models.open_vocabulary import EntityDetection, ModelProvenance
from app.services.generic_detector import CandidateFrame, YoloDetectionProvider


VEHICLE_LABELS = ("car", "truck", "bus", "motorcycle")


@dataclass(frozen=True)
class VehicleObservation:
    bbox: list[float]
    category: str
    confidence: float
    color: Optional[str]
    color_confidence: float
    colors: dict[str, float]
    crop_path: Optional[str]
    mask_path: Optional[str]
    provenance: ModelProvenance
    make_model_candidates: tuple[dict, ...] = ()
    body_type_candidates: tuple[dict, ...] = ()


def _contains_plate(vehicle_bbox: Sequence[float], plate_bbox: Sequence[float]) -> bool:
    """Allow a small detector margin while requiring the plate centre in the vehicle."""
    x1, y1, x2, y2 = vehicle_bbox
    width, height = x2 - x1, y2 - y1
    plate_x = (plate_bbox[0] + plate_bbox[2]) / 2
    plate_y = (plate_bbox[1] + plate_bbox[3]) / 2
    return (
        x1 - width * .08 <= plate_x <= x2 + width * .08
        and y1 - height * .08 <= plate_y <= y2 + height * .08
    )


def _dominant_color(distribution: dict[str, float]) -> tuple[Optional[str], float]:
    if not distribution:
        return None, 0.0
    color, share = max(distribution.items(), key=lambda item: item[1])
    # Low-share winners are too ambiguous to present as observed fact.
    return (color, float(share)) if share >= .25 else (None, float(share))


class VehicleRecognizer:
    def __init__(self, evidence_root: str, provider=None, attribute_provider=None):
        self.evidence_root = Path(evidence_root).resolve()
        self.provider = provider or YoloDetectionProvider(evidence_root)
        self.attribute_provider = attribute_provider
        if self.attribute_provider is None:
            model_path = os.environ.get("LOTTRACE_VEHICLE_ATTRIBUTE_MODEL")
            manifest_path = os.environ.get("LOTTRACE_VEHICLE_ATTRIBUTE_MANIFEST")
            if model_path and manifest_path:
                from app.services.vehicle_attribute_model import LocalVehicleAttributeProvider
                self.attribute_provider = LocalVehicleAttributeProvider(model_path, manifest_path)

    def _crop_path(self, value):
        if not value:
            return None
        prefix = "/evidence/"
        if value.startswith(prefix):
            path = (self.evidence_root / value[len(prefix):]).resolve()
            if self.evidence_root not in path.parents:
                raise ValueError("Invalid vehicle crop path.")
            return path
        return Path(value).resolve()

    def _observation(self, detection: EntityDetection) -> VehicleObservation:
        colors = {
            str(name): float(value)
            for name, value in (detection.attributes.get("colors") or {}).items()
        }
        color, color_confidence = _dominant_color(colors)
        candidates = tuple(
            dict(item) for item in detection.attributes.get("vehicle_make_model_candidates") or []
        )
        crop_path = self._crop_path(detection.crop_path)
        if not candidates and self.attribute_provider is not None and crop_path and crop_path.is_file():
            candidates = tuple(self.attribute_provider.predict(crop_path))
        return VehicleObservation(
            bbox=list(detection.bbox), category=detection.label,
            confidence=detection.confidence, color=color,
            color_confidence=color_confidence, colors=colors,
            crop_path=detection.crop_path, mask_path=detection.mask_path,
            provenance=detection.provenance,
            make_model_candidates=candidates,
            body_type_candidates=tuple(
                dict(item) for item in detection.attributes.get("vehicle_body_type_candidates") or []
            ),
        )

    def recognize_all(self, *, image_path: str, session_id: str, frame_idx: int,
                      timestamp_seconds: float) -> list[VehicleObservation]:
        frame = CandidateFrame(
            frame_id=f"vehicle_{frame_idx}", frame_idx=frame_idx,
            timestamp_seconds=timestamp_seconds, image_path=str(Path(image_path)),
            semantic_similarity=1.0,
        )
        detections = self.provider.detect([frame], ["vehicle"], session_id, min_confidence=.25)
        return [self._observation(item) for item in detections]

    def recognize(self, *, image_path: str, plate_bbox: Sequence[float], session_id: str,
                  frame_idx: int, timestamp_seconds: float) -> Optional[VehicleObservation]:
        observations = self.recognize_all(
            image_path=image_path, session_id=session_id, frame_idx=frame_idx,
            timestamp_seconds=timestamp_seconds,
        )
        associated = [item for item in observations if _contains_plate(item.bbox, plate_bbox)]
        if not associated:
            return None
        # Prefer the tightest containing detection; confidence breaks near-ties.
        return min(
            associated,
            key=lambda item: (
                (item.bbox[2] - item.bbox[0]) * (item.bbox[3] - item.bbox[1]),
                -item.confidence,
            ),
        )
