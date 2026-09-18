"""Purpose-built local automatic license plate recognition."""
from dataclasses import dataclass
import re
import threading
from typing import List, Sequence

import numpy as np

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

    def read_vehicle(self, frame: np.ndarray, bbox: Sequence[float]) -> List[PlateReading]:
        x1, y1, x2, y2 = map(int, bbox)
        x1, y1 = max(0, x1), max(0, y1)
        x2, y2 = min(frame.shape[1], x2), min(frame.shape[0], y2)
        if x2 <= x1 or y2 <= y1:
            return []
        vehicle = frame[y1:y2, x1:x2]
        readings = []
        for result in self.reader.predict(vehicle):
            if not result.ocr:
                continue
            text = normalize_plate(result.ocr.text)
            if not 4 <= len(text) <= 10:
                continue
            values = (list(result.ocr.confidence)
                      if isinstance(result.ocr.confidence, (list, tuple, np.ndarray)) else [])
            confidence = sum(values) / len(values) if values else 0.0
            box = result.detection.bounding_box
            readings.append(PlateReading(
                text=text, confidence=float(confidence),
                bbox=[x1 + int(box.x1), y1 + int(box.y1), x1 + int(box.x2), y1 + int(box.y2)],
            ))
        return readings
