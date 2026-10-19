"""Purpose-built local automatic license plate recognition.

The reader deliberately separates raw OCR from matching policy.  A single noisy
frame must never be treated as proof that a requested plate was present.
"""
from dataclasses import dataclass
import os
import re
import threading
from typing import List, Sequence

import numpy as np
import cv2

from app.models.open_vocabulary import ModelProvenance


DETECTOR_MODEL = "yolo-v9-t-384-license-plate-end2end"
OCR_MODEL = "cct-xs-v2-global-model"
_MODEL_LOCK = threading.RLock()
_MODEL_CACHE = None


def normalize_plate(value: str) -> str:
    return re.sub(r"[^A-Z0-9]", "", value.upper())


@dataclass(frozen=True)
class PlateReading:
    text: str
    confidence: float
    bbox: List[int]
    source_variant: str = "original"


_CONFUSABLE = str.maketrans({"O": "0", "Q": "0", "I": "1", "L": "1", "S": "5", "B": "8", "Z": "2"})


def plate_edit_distance(left: str, right: str) -> int:
    """Small dependency-free Levenshtein distance for OCR candidate review."""
    left, right = normalize_plate(left), normalize_plate(right)
    if len(left) < len(right):
        left, right = right, left
    previous = list(range(len(right) + 1))
    for row, left_char in enumerate(left, start=1):
        current = [row]
        for column, right_char in enumerate(right, start=1):
            current.append(min(
                current[-1] + 1,
                previous[column] + 1,
                previous[column - 1] + (left_char != right_char),
            ))
        previous = current
    return previous[-1]


def plate_similarity(observed: str, expected: str) -> float:
    """Return an OCR-aware similarity without ever redefining an exact match."""
    observed, expected = normalize_plate(observed), normalize_plate(expected)
    if not observed or not expected:
        return 0.0
    if observed == expected:
        return 1.0
    plain = 1.0 - plate_edit_distance(observed, expected) / max(len(observed), len(expected))
    folded_observed, folded_expected = observed.translate(_CONFUSABLE), expected.translate(_CONFUSABLE)
    folded = 1.0 - plate_edit_distance(folded_observed, folded_expected) / max(
        len(folded_observed), len(folded_expected)
    )
    # Confusable characters are useful for review, but must not become an exact read.
    return max(0.0, min(0.99, max(plain, folded * 0.97)))


def _intersection_over_union(left: Sequence[int], right: Sequence[int]) -> float:
    x1, y1 = max(left[0], right[0]), max(left[1], right[1])
    x2, y2 = min(left[2], right[2]), min(left[3], right[3])
    intersection = max(0, x2 - x1) * max(0, y2 - y1)
    left_area = max(0, left[2] - left[0]) * max(0, left[3] - left[1])
    right_area = max(0, right[2] - right[0]) * max(0, right[3] - right[1])
    return intersection / max(1, left_area + right_area - intersection)


class LicensePlateReader:
    def __init__(self):
        self.reader = self._load()

    @staticmethod
    def _load():
        global _MODEL_CACHE
        with _MODEL_LOCK:
            if _MODEL_CACHE is None:
                try:
                    from fast_alpr import ALPR
                    _MODEL_CACHE = ALPR(
                        detector_model=DETECTOR_MODEL, detector_conf_thresh=.4,
                        ocr_model=OCR_MODEL, ocr_device="cpu",
                    )
                except Exception as error:
                    raise RuntimeError(
                        "License-plate recognition models are unavailable. "
                        "Run: python backend/download_models.py"
                    ) from error
            return _MODEL_CACHE

    @property
    def provenance(self):
        return ModelProvenance(
            provider="fast-alpr", model_name=f"{DETECTOR_MODEL}+{OCR_MODEL}",
            model_version="0.4.0", device="cpu",
            metadata={"task": "automatic-license-plate-recognition"},
        )

    @staticmethod
    def _confidence(value) -> float:
        values = list(value) if isinstance(value, (list, tuple, np.ndarray)) else []
        confidence = float(sum(values) / len(values)) if values else 0.0
        if confidence > 1.0:
            confidence /= 100.0
        return max(0.0, min(1.0, confidence))

    def _read_region(self, image: np.ndarray, offset_x=0, offset_y=0) -> List[PlateReading]:
        if image is None or image.size == 0:
            return []
        readings = []
        for result in self.reader.predict(image):
            if not result.ocr:
                continue
            text = normalize_plate(result.ocr.text)
            if not 4 <= len(text) <= 10:
                continue
            box = result.detection.bounding_box
            readings.append(PlateReading(
                text=text,
                confidence=self._confidence(result.ocr.confidence),
                bbox=[offset_x + int(box.x1), offset_y + int(box.y1),
                      offset_x + int(box.x2), offset_y + int(box.y2)],
            ))
        return readings

    @staticmethod
    def _deduplicate(readings: Sequence[PlateReading]) -> List[PlateReading]:
        output = []
        for reading in sorted(readings, key=lambda item: item.confidence, reverse=True):
            duplicate = any(
                reading.text == kept.text and _intersection_over_union(reading.bbox, kept.bbox) >= 0.35
                for kept in output
            )
            if not duplicate:
                output.append(reading)
        return output

    def read_frame(self, frame: np.ndarray, *, tiled: bool = True) -> List[PlateReading]:
        """Read a full frame, tiles, and a guarded mirrored-camera recovery pass."""
        if frame is None or frame.size == 0:
            return []
        height, width = frame.shape[:2]
        readings = self._read_region(frame)
        if tiled and width >= 1000 and height >= 600:
            overlap_x, overlap_y = int(width * 0.08), int(height * 0.08)
            middle_x, middle_y = width // 2, height // 2
            regions = [
                (0, 0, middle_x + overlap_x, middle_y + overlap_y),
                (middle_x - overlap_x, 0, width, middle_y + overlap_y),
                (0, middle_y - overlap_y, middle_x + overlap_x, height),
                (middle_x - overlap_x, middle_y - overlap_y, width, height),
            ]
            for x1, y1, x2, y2 in regions:
                readings.extend(self._read_region(frame[y1:y2, x1:x2], x1, y1))
        readings = self._deduplicate(readings)
        mirror_enabled = os.environ.get("AIEYE_PLATE_MIRROR_FALLBACK", "true").lower() not in (
            "0", "false", "no",
        )
        mirror_threshold = float(os.environ.get("AIEYE_PLATE_MIRROR_THRESHOLD", ".72"))
        if not 0 <= mirror_threshold <= 1:
            raise ValueError("AIEYE_PLATE_MIRROR_THRESHOLD must be between 0 and 1.")
        if mirror_enabled and max((item.confidence for item in readings), default=0.0) < mirror_threshold:
            for reading in self._read_region(cv2.flip(frame, 1)):
                x1, y1, x2, y2 = reading.bbox
                readings.append(PlateReading(
                    text=reading.text, confidence=reading.confidence,
                    bbox=[width - x2, y1, width - x1, y2],
                    source_variant="horizontal_flip",
                ))
        return self._deduplicate(readings)

    def read_vehicle(self, frame: np.ndarray, bbox: Sequence[float]) -> List[PlateReading]:
        x1, y1, x2, y2 = map(int, bbox)
        x1, y1 = max(0, x1), max(0, y1)
        x2, y2 = min(frame.shape[1], x2), min(frame.shape[0], y2)
        if x2 <= x1 or y2 <= y1:
            return []
        vehicle = frame[y1:y2, x1:x2]
        return self._deduplicate(self._read_region(vehicle, x1, y1))
