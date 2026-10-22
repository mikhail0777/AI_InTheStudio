"""Summarize exact-plate OCR failures without changing any predictions."""
from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timezone
import json
from pathlib import Path
from difflib import SequenceMatcher

import cv2


def edit_breakdown(expected: str, observed: str) -> tuple[Counter, Counter]:
    """Return edit-type and substitution-pair counts for one prediction."""
    kinds: Counter = Counter()
    substitutions: Counter = Counter()
    for tag, i1, i2, j1, j2 in SequenceMatcher(None, expected, observed).get_opcodes():
        if tag == "equal":
            continue
        if tag == "delete":
            kinds["missing_character"] += i2 - i1
        elif tag == "insert":
            kinds["extra_character"] += j2 - j1
        else:
            paired = min(i2 - i1, j2 - j1)
            kinds["substitution"] += paired
            substitutions.update(zip(expected[i1:i1 + paired], observed[j1:j1 + paired]))
            kinds["missing_character"] += (i2 - i1) - paired
            kinds["extra_character"] += (j2 - j1) - paired
    if expected != observed and len(expected) == len(observed) and Counter(expected) == Counter(observed):
        kinds["ordering_error"] += 1
    return kinds, substitutions


def image_quality(path: Path) -> dict:
    image = cv2.imread(str(path), cv2.IMREAD_GRAYSCALE)
    if image is None:
        return {"available": False}
    height, width = image.shape
    blur_score = float(cv2.Laplacian(image, cv2.CV_64F).var())
    brightness = float(image.mean())
    contrast = float(image.std())
    tags = []
    if width < 160 or height < 48:
        tags.append("small_crop")
    if blur_score < 80:
        tags.append("low_sharpness")
    if brightness < 55:
        tags.append("dark")
    elif brightness > 210:
        tags.append("bright")
    if contrast < 30:
        tags.append("low_contrast")
    return {
        "available": True, "width": width, "height": height,
        "blur_score": round(blur_score, 3), "brightness": round(brightness, 3),
        "contrast": round(contrast, 3), "diagnostic_tags": tags,
    }


def analyze(report: dict, image_dir: Path | None = None) -> dict:
    rows = report.get("rows") or []
    failed = [row for row in rows if row.get("expected") != row.get("observed")]
    edit_types: Counter = Counter()
    substitution_pairs: Counter = Counter()
    quality_tags: Counter = Counter()
    details = []
    for row in failed:
        kinds, substitutions = edit_breakdown(str(row.get("expected", "")), str(row.get("observed", "")))
        edit_types.update(kinds); substitution_pairs.update(substitutions)
        quality = image_quality(image_dir / row["file"]) if image_dir and row.get("file") else {"available": False}
        quality_tags.update(quality.get("diagnostic_tags", []))
        details.append({
            "file": row.get("file"), "expected": row.get("expected"), "observed": row.get("observed"),
            "edit_types": dict(kinds), "image_quality": quality,
        })
    total = len(rows)
    return {
        "schema_version": 1,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source_model": report.get("model"),
        "source_split": report.get("split"),
        "total_plates": total,
        "exact_matches": total - len(failed),
        "exact_plate_accuracy": (total - len(failed)) / total if total else 0.0,
        "failed_plates": len(failed),
        "edit_type_counts": dict(edit_types.most_common()),
        "top_substitutions": [
            {"expected": pair[0], "observed": pair[1], "count": count}
            for pair, count in substitution_pairs.most_common(25)
        ],
        "diagnostic_quality_tag_counts": dict(quality_tags.most_common()),
        "failures": details,
        "limitations": [
            "Image-quality tags are deterministic diagnostics, not human condition labels.",
            "Rain, glare, skew, occlusion, and plate style require human labels and are not inferred here.",
            "SequenceMatcher edit categories are diagnostic and are not a replacement for character error rate.",
        ],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--image-dir", type=Path)
    args = parser.parse_args()
    result = analyze(json.loads(args.input.read_text(encoding="utf-8")), args.image_dir)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({key: result[key] for key in (
        "total_plates", "exact_matches", "exact_plate_accuracy", "failed_plates",
        "edit_type_counts", "top_substitutions", "diagnostic_quality_tag_counts",
    )}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
