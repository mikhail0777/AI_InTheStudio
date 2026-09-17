"""Generic COCO localization provider used after semantic retrieval."""
from dataclasses import dataclass
import hashlib
import os
from pathlib import Path
import threading
import uuid
from typing import List, Sequence

import cv2
import numpy as np

from app.models.open_vocabulary import EntityDetection, ModelProvenance
from app.services.visual_features import color_distribution


BACKEND_DIR = Path(__file__).resolve().parents[2]
_MODEL_CACHE = {}
_MODEL_LOCK = threading.RLock()


@dataclass(frozen=True)
class CandidateFrame:
    frame_id: str
    frame_idx: int
    timestamp_seconds: float
    image_path: str
    semantic_similarity: float


def _polygon_mask(polygon, shape):
    mask = np.zeros(shape[:2], dtype=np.uint8)
    if polygon is not None and len(polygon) >= 3:
        cv2.fillPoly(mask, [np.rint(np.asarray(polygon)).astype(np.int32)], 255)
    return mask


class YoloDetectionProvider:
    """Fast fixed-class proposals; unknown vocabulary is left for grounding providers."""

    ALIASES = {
        "vehicle": ("car", "truck", "bus", "motorcycle"),
        "bike": ("bicycle",), "person": ("person",), "woman": ("person",),
        "man": ("person",), "child": ("person",),
    }

    def __init__(self, evidence_root: str, model_path=None):
        self.evidence_root = Path(evidence_root).resolve()
        self.evidence_root.mkdir(parents=True, exist_ok=True)
        self.model_path = Path(model_path or os.environ.get(
            "AIEYE_MODEL_PATH", str(BACKEND_DIR / "models" / "yolo11s-seg.pt")
        )).resolve()
        self.image_size = int(os.environ.get("AIEYE_GENERIC_IMAGE_SIZE", "1280"))
        if not 320 <= self.image_size <= 2048:
            raise ValueError("AIEYE_GENERIC_IMAGE_SIZE must be between 320 and 2048.")
        self._load()

    def _load(self):
        if not self.model_path.is_file():
            raise RuntimeError("YOLO segmentation model missing. Run: python backend/download_models.py")
        config = Path(os.environ.get("AIEYE_DATA_DIR", str(BACKEND_DIR / "data"))) / "ultralytics"
        config.mkdir(parents=True, exist_ok=True)
        os.environ.setdefault("YOLO_CONFIG_DIR", str(config.resolve()))
        key = (str(self.model_path), self.model_path.stat().st_mtime_ns)
        with _MODEL_LOCK:
            if key not in _MODEL_CACHE:
                import torch
                from ultralytics import YOLO
                torch.set_num_threads(max(1, int(os.environ.get("AIEYE_CPU_THREADS", "4"))))
                model = YOLO(str(self.model_path))
                if model.task != "segment":
                    raise RuntimeError("Generic localization requires a segmentation model.")
                digest = hashlib.sha256(self.model_path.read_bytes()).hexdigest()
                _MODEL_CACHE[key] = (model, digest)
            self.model, self.weight_hash = _MODEL_CACHE[key]
        self.names = {int(key): value for key, value in self.model.names.items()}
        self.class_ids = {value.lower(): key for key, value in self.names.items()}

    @property
    def provenance(self):
        return ModelProvenance(
            provider="ultralytics", model_name=self.model_path.name,
            model_version=self.weight_hash, device="cuda" if self._cuda_available() else "cpu",
            metadata={"task": "instance-segmentation", "classes": "COCO"},
        )

    @staticmethod
    def _cuda_available():
        import torch
        return torch.cuda.is_available()

    def supported_labels(self, vocabulary: Sequence[str]):
        supported = []
        for requested in vocabulary:
            labels = self.ALIASES.get(requested.lower(), (requested.lower(),))
            supported.extend(label for label in labels if label in self.class_ids)
        return list(dict.fromkeys(supported))

    def detect(self, frames: Sequence[CandidateFrame], vocabulary: Sequence[str], session_id: str,
               min_confidence: float = .25) -> List[EntityDetection]:
        labels = self.supported_labels(vocabulary)
        if not labels:
            return []
        class_ids = [self.class_ids[label] for label in labels]
        directory = (self.evidence_root / session_id).resolve()
        if directory.parent != self.evidence_root:
            raise ValueError("Invalid evidence directory.")
        directory.mkdir(parents=True, exist_ok=True)
        output = []
        batch_size = max(1, int(os.environ.get("AIEYE_DETECTION_BATCH_SIZE", "2")))
        for start in range(0, len(frames), batch_size):
            batch = frames[start:start + batch_size]
            images = [cv2.imread(item.image_path) for item in batch]
            if any(image is None or image.size == 0 for image in images):
                raise ValueError("A retrieved frame could not be opened for localization.")
            with _MODEL_LOCK:
                try:
                    results = self.model.predict(
                        images, verbose=False, save=False, classes=class_ids,
                        conf=min_confidence, iou=.5, imgsz=self.image_size,
                    )
                except Exception as error:
                    raise RuntimeError("Generic YOLO localization failed.") from error
            for frame, image, result in zip(batch, images, results):
                polygons = result.masks.xy if result.masks is not None else []
                for index, box in enumerate(result.boxes):
                    class_id = int(box.cls.item())
                    confidence = float(box.conf.item())
                    label = self.names[class_id].lower()
                    bbox = [float(value) for value in box.xyxy[0].cpu().tolist()]
                    x1, y1, x2, y2 = bbox
                    a, b = max(0, int(x1)), max(0, int(y1))
                    c, d = min(image.shape[1], int(np.ceil(x2))), min(image.shape[0], int(np.ceil(y2)))
                    if c <= a or d <= b:
                        continue
                    full_mask = _polygon_mask(polygons[index] if index < len(polygons) else None, image.shape)
                    if np.count_nonzero(full_mask) < 40:
                        full_mask[b:d, a:c] = 255
                    crop = image[b:d, a:c]
                    crop_mask = full_mask[b:d, a:c]
                    detection_id = f"det_{frame.frame_idx}_{uuid.uuid4().hex[:10]}"
                    crop_file = directory / f"{detection_id}.jpg"
                    mask_file = directory / f"{detection_id}_mask.png"
                    if not cv2.imwrite(str(crop_file), crop) or not cv2.imwrite(str(mask_file), crop_mask):
                        raise OSError("Could not save localized evidence.")
                    blur = cv2.Laplacian(cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY), cv2.CV_64F).var()
                    visibility = min(1.0, np.count_nonzero(crop_mask) / max(1, crop_mask.size))
                    quality = min(1.0, .5 * visibility + .5 * min(1.0, blur / 250.0))
                    output.append(EntityDetection(
                        detection_id=detection_id, frame_id=frame.frame_id,
                        frame_idx=frame.frame_idx, timestamp_seconds=frame.timestamp_seconds,
                        label=label, bbox=bbox, confidence=confidence, visibility=quality,
                        mask_path=f"/evidence/{session_id}/{mask_file.name}",
                        crop_path=f"/evidence/{session_id}/{crop_file.name}",
                        attributes={"colors": color_distribution(crop, crop_mask),
                                    "semantic_similarity": frame.semantic_similarity},
                        provenance=self.provenance,
                    ))
        return output
