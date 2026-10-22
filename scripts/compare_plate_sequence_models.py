"""Compare open-source FastALPR sequence readers on labelled plate crops."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import sys
import time

import cv2


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT)); sys.path.insert(0, str(ROOT / "backend"))

from app.services.license_plate_reader import normalize_plate
from scripts.audit_yolo_ocr_dataset import IMAGE_SUFFIXES, load_class_names, ordered_sequence, parse_label
from scripts.evaluate_plate_crop_ocr import summarize


DEFAULT_MODELS = [
    "cct-xs-v2-global-model", "cct-s-v2-global-model",
    "european-plates-mobile-vit-v2-model", "global-plates-mobile-vit-v2-model",
]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", required=True, type=Path)
    parser.add_argument("--split", choices=["valid", "test"], required=True)
    parser.add_argument("--models", nargs="+", default=DEFAULT_MODELS)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    from fast_alpr.default_ocr import DefaultOCR

    names = load_class_names(args.dataset / "data.yaml")
    images = sorted(
        item for item in (args.dataset / args.split / "images").iterdir()
        if item.is_file() and item.suffix.lower() in IMAGE_SUFFIXES
    )
    expected = {}
    for image in images:
        characters, errors = parse_label(args.dataset / args.split / "labels" / f"{image.stem}.txt", names)
        if errors:
            raise ValueError(errors[0])
        expected[image.name] = ordered_sequence(characters)
    results = {}
    for model_name in args.models:
        reader = DefaultOCR(hub_ocr_model=model_name, device="cpu")
        rows = []; started = time.perf_counter()
        for image in images:
            frame = cv2.imread(str(image))
            result = reader.predict(frame) if frame is not None else None
            observed = normalize_plate(result.text if result else "")
            rows.append({
                "file": image.name, "expected": expected[image.name],
                "top1": observed, "candidates": [observed] if observed else [],
            })
        results[model_name] = {
            "metrics": summarize(rows), "elapsed_seconds": time.perf_counter() - started,
            "rows": rows,
        }
    ranking = sorted(results, key=lambda name: (
        results[name]["metrics"]["top1_exact_plate_accuracy"],
        results[name]["metrics"]["character_accuracy"],
    ), reverse=True)
    report = {
        "schema_version": 1, "generated_at": datetime.now(timezone.utc).isoformat(),
        "dataset": str(args.dataset.resolve()), "split": args.split,
        "selection_policy": (
            "Model selection is permitted only on valid; test accepts an explicitly selected model."
        ),
        "ranking": ranking, "models": results,
        "limitations": [
            "Direct OCR on cropped plates; no plate localization, tracking, or event measurement.",
            "The 37-plate regression split has already been inspected and is not a fresh final test.",
        ],
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({
        "output": str(args.output), "ranking": ranking,
        "metrics": {name: results[name]["metrics"] for name in ranking},
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
