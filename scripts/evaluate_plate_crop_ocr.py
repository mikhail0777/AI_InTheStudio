"""Evaluate LotTrace OCR on plate crops with full text encoded in filenames."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import platform
import sys
import time

import cv2


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "backend"))

from app.services.license_plate_reader import LicensePlateReader, normalize_plate
from scripts.audit_yolo_ocr_dataset import IMAGE_SUFFIXES, filename_truth
from scripts.evaluation_metrics import levenshtein, wilson_interval


def summarize(rows: list[dict]) -> dict:
    eligible = [row for row in rows if row["expected"]]
    top1_exact = sum(row["top1"] == row["expected"] for row in eligible)
    topk_exact = sum(row["expected"] in row["candidates"] for row in eligible)
    edits = sum(levenshtein(row["top1"], row["expected"]) for row in eligible)
    characters = sum(len(row["expected"]) for row in eligible)
    return {
        "eligible_plate_crops": len(eligible),
        "crops_with_reading": sum(bool(row["top1"]) for row in eligible),
        "read_coverage": sum(bool(row["top1"]) for row in eligible) / len(eligible) if eligible else 0.0,
        "top1_exact_matches": top1_exact,
        "top1_exact_plate_accuracy": top1_exact / len(eligible) if eligible else 0.0,
        "top1_exact_plate_accuracy_wilson_95": wilson_interval(top1_exact, len(eligible)),
        "topk_exact_matches": topk_exact,
        "topk_exact_plate_accuracy": topk_exact / len(eligible) if eligible else 0.0,
        "topk_exact_plate_accuracy_wilson_95": wilson_interval(topk_exact, len(eligible)),
        "character_edits": edits,
        "ground_truth_characters": characters,
        "character_error_rate": edits / characters if characters else 0.0,
        "character_accuracy": 1.0 - edits / characters if characters else 0.0,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--images", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--limit", type=int)
    args = parser.parse_args()

    image_paths = sorted(
        path for path in args.images.iterdir()
        if path.is_file() and path.suffix.lower() in IMAGE_SUFFIXES
    )
    if args.limit is not None:
        if args.limit < 1:
            raise SystemExit("--limit must be at least 1")
        image_paths = image_paths[:args.limit]
    unresolved = [path.name for path in image_paths if filename_truth(path) is None]
    if unresolved:
        raise SystemExit(
            f"Full plate text could not be derived for {len(unresolved)} images; "
            f"first unresolved file: {unresolved[0]}"
        )
    if not image_paths:
        raise SystemExit(f"No supported images found under {args.images}")

    reader = LicensePlateReader()
    rows: list[dict] = []
    invalid_images = 0
    started = time.perf_counter()
    for index, image_path in enumerate(image_paths, start=1):
        frame = cv2.imread(str(image_path))
        expected = normalize_plate(filename_truth(image_path) or "")
        if frame is None or frame.size == 0:
            invalid_images += 1
            rows.append({
                "file": image_path.name, "expected": expected, "top1": "",
                "candidates": [], "status": "invalid_image",
            })
            continue
        readings = sorted(reader.read_frame(frame, tiled=False), key=lambda item: item.confidence, reverse=True)
        candidates = list(dict.fromkeys(item.text for item in readings if item.text))
        rows.append({
            "file": image_path.name,
            "expected": expected,
            "top1": candidates[0] if candidates else "",
            "candidates": candidates,
            "observations": [
                {
                    "text": item.text,
                    "confidence": round(item.confidence, 6),
                    "source_variant": item.source_variant,
                    "bbox": item.bbox,
                }
                for item in readings
            ],
            "status": "read" if candidates else "no_read",
        })
        if index % 25 == 0:
            print(f"Plate crops {index}/{len(image_paths)}", file=sys.stderr, flush=True)

    elapsed = time.perf_counter() - started
    valid_rows = [row for row in rows if row["status"] != "invalid_image"]
    report = {
        "schema_version": 1,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "dataset": {
            "images_directory": str(args.images.resolve()),
            "truth_source": "leading alphanumeric filename token",
            "images_selected": len(image_paths),
            "images_evaluated": len(valid_rows),
            "invalid_images": invalid_images,
        },
        "metrics": summarize(valid_rows),
        "runtime": {
            "python": sys.version,
            "platform": platform.platform(),
            "device": "cpu",
            "elapsed_seconds": elapsed,
            "images_per_second": len(valid_rows) / elapsed if elapsed else 0.0,
        },
        "model": reader.provenance.model_dump(mode="json"),
        "rows": rows,
        "limitations": [
            "This evaluates already-cropped, preprocessed plate images, not full-frame localization.",
            "Filename transcription provenance must be verified before this is called human-labelled ground truth.",
            "This does not measure tracking, crossings, plate-to-vehicle association, or false events per hour.",
        ],
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({
        "output": str(args.output), "metrics": report["metrics"], "runtime": report["runtime"],
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
