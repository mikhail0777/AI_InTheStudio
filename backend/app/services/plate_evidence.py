"""Non-destructive plate-crop quality scoring and enhancement derivatives."""
from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np


def crop_plate(frame: np.ndarray, bbox) -> np.ndarray:
    if frame is None or frame.size == 0:
        raise ValueError("A non-empty source frame is required.")
    height, width = frame.shape[:2]
    x1, y1, x2, y2 = (int(round(float(value))) for value in bbox)
    x1, y1, x2, y2 = max(0, x1), max(0, y1), min(width, x2), min(height, y2)
    if x2 <= x1 or y2 <= y1:
        raise ValueError("Plate bounding box does not intersect the source frame.")
    return frame[y1:y2, x1:x2].copy()


def quality_metrics(crop: np.ndarray) -> dict[str, float | int]:
    if crop is None or crop.size == 0:
        raise ValueError("A non-empty plate crop is required.")
    gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY) if crop.ndim == 3 else crop
    sharpness = float(cv2.Laplacian(gray, cv2.CV_64F).var())
    contrast = float(gray.std())
    brightness = float(gray.mean())
    exposure = max(0.0, 1.0 - abs(brightness - 127.5) / 127.5)
    score = (
        .45 * min(1.0, sharpness / 500.0)
        + .25 * min(1.0, contrast / 64.0)
        + .20 * exposure
        + .10 * min(1.0, gray.shape[1] / 180.0)
    )
    return {
        "width": int(gray.shape[1]), "height": int(gray.shape[0]),
        "sharpness": round(sharpness, 6), "contrast": round(contrast, 6),
        "brightness": round(brightness, 6), "exposure_score": round(exposure, 6),
        "quality_score": round(score, 6),
    }


def enhance_plate_crop(crop: np.ndarray) -> np.ndarray:
    """Create a separate OCR derivative; never mutate the supplied crop."""
    if crop is None or crop.size == 0:
        raise ValueError("A non-empty plate crop is required.")
    scale = max(1.0, 240.0 / max(1, crop.shape[1]))
    enlarged = cv2.resize(crop, None, fx=scale, fy=scale, interpolation=cv2.INTER_CUBIC)
    lab = cv2.cvtColor(enlarged, cv2.COLOR_BGR2LAB)
    light, a, b = cv2.split(lab)
    normalized = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8)).apply(light)
    enhanced = cv2.cvtColor(cv2.merge((normalized, a, b)), cv2.COLOR_LAB2BGR)
    blurred = cv2.GaussianBlur(enhanced, (0, 0), 1.0)
    return cv2.addWeighted(enhanced, 1.35, blurred, -.35, 0)


def save_plate_derivatives(frame: np.ndarray, bbox, directory: Path, stem: str) -> dict:
    """Persist lossless raw and enhanced crops with auditable quality metadata."""
    directory.mkdir(parents=True, exist_ok=True)
    raw = crop_plate(frame, bbox)
    enhanced = enhance_plate_crop(raw)
    raw_path = directory / f"{stem}_raw.png"
    enhanced_path = directory / f"{stem}_enhanced.png"
    if not cv2.imwrite(str(raw_path), raw):
        raise OSError("Could not save the original plate crop.")
    if not cv2.imwrite(str(enhanced_path), enhanced):
        raw_path.unlink(missing_ok=True)
        raise OSError("Could not save the enhanced plate derivative.")
    return {
        "raw_path": str(raw_path), "enhanced_path": str(enhanced_path),
        "metrics": quality_metrics(raw), "enhanced_image": enhanced,
    }
