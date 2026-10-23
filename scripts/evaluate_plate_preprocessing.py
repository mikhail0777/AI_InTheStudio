"""Run a validation-only FastPlateOCR preprocessing ablation on identical crops."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sys
import time

import cv2

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT)); sys.path.insert(0, str(ROOT / "backend"))

from app.services.license_plate_reader import normalize_plate
from app.services.plate_evidence import preprocessing_variants, save_preprocessing_variants
from scripts.audit_yolo_ocr_dataset import IMAGE_SUFFIXES, load_class_names, ordered_sequence, parse_label
from scripts.evaluate_plate_crop_ocr import summarize


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", required=True, type=Path)
    parser.add_argument("--split", choices=["valid"], default="valid")
    parser.add_argument("--model", default="cct-s-v2-global-model")
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--derivatives", type=Path)
    args = parser.parse_args()
    from fast_alpr.default_ocr import DefaultOCR

    names = load_class_names(args.dataset / "data.yaml")
    images = sorted(path for path in (args.dataset / args.split / "images").iterdir()
                    if path.suffix.lower() in IMAGE_SUFFIXES)
    reader = DefaultOCR(hub_ocr_model=args.model, device="cpu")
    rows_by_variant: dict[str, list[dict]] = {}
    started = time.perf_counter()
    source_hashes = {}
    for image_path in images:
        characters, errors = parse_label(
            args.dataset / args.split / "labels" / f"{image_path.stem}.txt", names,
        )
        if errors:
            raise ValueError(errors[0])
        expected = ordered_sequence(characters)
        crop = cv2.imread(str(image_path))
        if crop is None:
            raise ValueError(f"Unreadable crop: {image_path}")
        source_hashes[image_path.name] = file_sha256(image_path)
        variants = preprocessing_variants(crop)
        if args.derivatives:
            save_preprocessing_variants(crop, args.derivatives, image_path.stem)
        for variant, candidate in variants.items():
            result = reader.predict(candidate)
            observed = normalize_plate(result.text if result else "")
            rows_by_variant.setdefault(variant, []).append({
                "file": image_path.name, "expected": expected,
                "top1": observed, "candidates": [observed] if observed else [],
            })
    metrics = {name: summarize(rows) for name, rows in sorted(rows_by_variant.items())}
    ranking = sorted(metrics, key=lambda name: (
        metrics[name]["top1_exact_plate_accuracy"], metrics[name]["character_accuracy"], name,
    ), reverse=True)
    report = {
        "schema_version": 1,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "dataset": str(args.dataset.resolve()), "split": args.split,
        "model": args.model, "plates": len(images), "source_sha256": source_hashes,
        "selection_policy": "Choose preprocessing on validation exact accuracy, then character accuracy.",
        "ranking": ranking, "metrics": metrics,
        "rows": rows_by_variant,
        "limitations": [
            "Validation-only crop ablation; it is not a final-test or event-level result.",
            "Derivative variants from one source image are not independent frames.",
        ],
        "elapsed_seconds": time.perf_counter() - started,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"ranking": ranking, "metrics": metrics}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
