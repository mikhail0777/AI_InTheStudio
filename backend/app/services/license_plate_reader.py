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
DIRECT_CROP_OCR_MODEL = "cct-s-v2-global-model"
DIRECT_CROP_OCR_SHA256 = "384bbbd2cea3ef54761d3df70822ef3a349ee1a112aeafddbe0e3ba06bc6e47b"
DETECTOR_SHA256 = "888397b96d761c89db40bc9c305838e8652660f5e282c2cadebbe8d2951a77a8"
OCR_SHA256 = "8031afb5fdc6b4d80462c9d542f1284ebd2cfddf5dbacd62609848d7e2855f44"
OCR_MODES = {
    "existing": {
        "model": OCR_MODEL, "sha256": OCR_SHA256,
        "release_status": "production_baseline",
    },
    "fastplate-cct-s-experiment": {
        "model": "cct-s-v2-global-model",
        "sha256": "384bbbd2cea3ef54761d3df70822ef3a349ee1a112aeafddbe0e3ba06bc6e47b",
        "release_status": "validation_underperformed_do_not_auto_promote",
    },
}
DETECTOR_CONFIDENCE_THRESHOLD = .4
_MODEL_LOCK = threading.RLock()
_MODEL_CACHE = {}
_DIRECT_OCR_CACHE = {}


def normalize_plate(value: str) -> str:
    return re.sub(r"[^A-Z0-9]", "", value.upper())


@dataclass(frozen=True)
class PlateReading:
    text: str
    confidence: float
    bbox: List[int]
    source_variant: str = "original"


_CONFUSABLE = str.maketrans({
    "O": "0", "Q": "0", "I": "1", "L": "1", "S": "5", "B": "8",
    "Z": "2", "G": "6", "T": "7",
})


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
    def __init__(self, *, mode: str | None = None):
        self.mode = mode or os.environ.get("AIEYE_PLATE_OCR_MODE", "existing")
        if self.mode not in OCR_MODES:
            raise ValueError(
                f"AIEYE_PLATE_OCR_MODE must be one of: {', '.join(sorted(OCR_MODES))}"
            )
        self.ocr_config = OCR_MODES[self.mode]
        self.reader = self._load(self.ocr_config["model"])
        self.crop_reader = self._load_direct_ocr(DIRECT_CROP_OCR_MODEL)

    @staticmethod
    def _load(ocr_model: str = OCR_MODEL):
        global _MODEL_CACHE
        with _MODEL_LOCK:
            if ocr_model not in _MODEL_CACHE:
                try:
                    from fast_alpr import ALPR
                    _MODEL_CACHE[ocr_model] = ALPR(
                        detector_model=DETECTOR_MODEL, detector_conf_thresh=DETECTOR_CONFIDENCE_THRESHOLD,
                        ocr_model=ocr_model, ocr_device="cpu",
                    )
                except Exception as error:
                    raise RuntimeError(
                        "License-plate recognition models are unavailable. "
                        "Run: python backend/download_models.py"
                    ) from error
            return _MODEL_CACHE[ocr_model]

    @staticmethod
    def _load_direct_ocr(ocr_model: str = DIRECT_CROP_OCR_MODEL):
        global _DIRECT_OCR_CACHE
        with _MODEL_LOCK:
            if ocr_model not in _DIRECT_OCR_CACHE:
                try:
                    from fast_alpr.default_ocr import DefaultOCR
                    _DIRECT_OCR_CACHE[ocr_model] = DefaultOCR(hub_ocr_model=ocr_model, device="cpu")
                except Exception as error:
                    raise RuntimeError(
                        "Direct plate-crop OCR model is unavailable. "
                        "Run: python backend/download_models.py"
                    ) from error
            return _DIRECT_OCR_CACHE[ocr_model]

    @property
    def provenance(self):
        return ModelProvenance(
            provider="fast-alpr", model_name=f"{DETECTOR_MODEL}+{self.ocr_config['model']}",
            model_version="0.4.0", device="cpu",
            metadata={
                "task": "automatic-license-plate-recognition",
                "detector": {"name": DETECTOR_MODEL, "sha256": DETECTOR_SHA256,
                             "confidence_threshold": DETECTOR_CONFIDENCE_THRESHOLD},
                "ocr": {
                    "name": self.ocr_config["model"],
                    "sha256": self.ocr_config["sha256"],
                    "mode": self.mode,
                    "release_status": self.ocr_config["release_status"],
                },
                "direct_crop_ocr": {
                    "name": DIRECT_CROP_OCR_MODEL,
                    "sha256": DIRECT_CROP_OCR_SHA256,
                    "selection": "OpenALPR 300-image development split; padded direct-crop OCR",
                    "scope": "already-localized crop candidate generation only",
                },
            },
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
                _intersection_over_union(reading.bbox, kept.bbox) >= 0.45
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

    def read_crop(self, crop: np.ndarray, *, source_variant: str = "enhanced_crop") -> List[PlateReading]:
        """Run OCR directly on an already-localized plate crop.

        Sending a known crop through the detector again can trim characters or
        select decorative text. The recognizer therefore receives the crop
        directly plus a border-preserving padded derivative. Both remain raw
        candidates; disagreement is never silently rewritten into a match.
        """
        if crop is None or crop.size == 0:
            return []
        ocr = getattr(self, "crop_reader", None) or getattr(self.reader, "ocr", None)
        if ocr is None or not hasattr(ocr, "predict"):
            return [PlateReading(
                text=item.text, confidence=item.confidence, bbox=item.bbox,
                source_variant=source_variant,
            ) for item in self._deduplicate(self._read_region(crop))]
        height, width = crop.shape[:2]
        pad_x, pad_y = max(2, round(width * .08)), max(2, round(height * .12))
        variants = {
            source_variant: crop,
            f"{source_variant}_padded": cv2.copyMakeBorder(
                crop, pad_y, pad_y, pad_x, pad_x, cv2.BORDER_REPLICATE,
            ),
        }
        best_by_text: dict[str, PlateReading] = {}
        for variant, image in variants.items():
            result = ocr.predict(image)
            if not result:
                continue
            text = normalize_plate(result.text)
            if not 3 <= len(text) <= 10:
                continue
            reading = PlateReading(
                text=text,
                confidence=self._confidence(result.confidence),
                bbox=[0, 0, width, height],
                source_variant=variant,
            )
            current = best_by_text.get(text)
            if current is None or reading.confidence > current.confidence:
                best_by_text[text] = reading
        # Validation selected the padded crop as the primary direct-OCR view.
        # Confidence is retained as evidence but is not calibrated well enough
        # to let a conflicting raw view overrule that selection.
        return sorted(best_by_text.values(), key=lambda item: (
            item.source_variant.endswith("_padded"), item.confidence,
        ), reverse=True)

    def read_vehicle(self, frame: np.ndarray, bbox: Sequence[float]) -> List[PlateReading]:
        x1, y1, x2, y2 = map(int, bbox)
        x1, y1 = max(0, x1), max(0, y1)
        x2, y2 = min(frame.shape[1], x2), min(frame.shape[0], y2)
        if x2 <= x1 or y2 <= y1:
            return []
        vehicle = frame[y1:y2, x1:x2]
        return self._deduplicate(self._read_region(vehicle, x1, y1))
