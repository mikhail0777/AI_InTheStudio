"""Evaluate a YOLO character detector as an exact plate-sequence reader."""
from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import platform
import sys
import time


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.audit_yolo_ocr_dataset import IMAGE_SUFFIXES, load_class_names, ordered_sequence, parse_label
from scripts.evaluation_metrics import levenshtein, wilson_interval


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(4 * 1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def predicted_sequence(boxes: list[dict], threshold: float) -> str:
    selected = [item for item in boxes if float(item["confidence"]) >= threshold]
    return "".join(str(item["character"]) for item in sorted(selected, key=lambda item: float(item["x"])))


def summarize(rows: list[dict], threshold: float) -> dict:
    exact = 0
    edits = characters = reads = 0
    confusions: Counter[str] = Counter()
    for row in rows:
        observed = predicted_sequence(row["predictions"], threshold)
        expected = row["expected"]
        reads += int(bool(observed))
        exact += int(observed == expected)
        edits += levenshtein(observed, expected)
        characters += len(expected)
        for expected_char, observed_char in zip(expected, observed):
            if expected_char != observed_char:
                confusions[f"{expected_char}->{observed_char}"] += 1
    total = len(rows)
    return {
        "confidence_threshold": threshold,
        "plates": total,
        "plates_with_reading": reads,
        "read_coverage": reads / total if total else 0.0,
        "exact_matches": exact,
        "exact_plate_accuracy": exact / total if total else 0.0,
        "exact_plate_accuracy_wilson_95": wilson_interval(exact, total),
        "character_edits": edits,
        "ground_truth_characters": characters,
        "character_error_rate": edits / characters if characters else 0.0,
        "character_accuracy": 1.0 - edits / characters if characters else 0.0,
        "common_aligned_confusions": dict(confusions.most_common(20)),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", required=True, type=Path)
    parser.add_argument("--dataset", required=True, type=Path)
    parser.add_argument("--split", choices=["valid", "test"], required=True)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--confidence", type=float)
    parser.add_argument("--thresholds", default="0.05,0.10,0.15,0.20,0.25,0.30,0.40,0.50")
    parser.add_argument("--imgsz", type=int, default=320)
    args = parser.parse_args()
    if args.split == "test" and args.confidence is None:
        raise SystemExit("Test evaluation requires a validation-selected --confidence threshold")

    thresholds = [float(item) for item in args.thresholds.split(",")]
    if args.confidence is not None:
        thresholds = [args.confidence]
    if not thresholds or any(not 0.0 <= item <= 1.0 for item in thresholds):
        raise SystemExit("Confidence thresholds must be between 0 and 1")

    split_root = args.dataset / args.split
    images_dir = split_root / "images"
    labels_dir = split_root / "labels"
    class_names = load_class_names(args.dataset / "data.yaml")
    images = sorted(
        path for path in images_dir.iterdir()
        if path.is_file() and path.suffix.lower() in IMAGE_SUFFIXES
    )
    if not images:
        raise SystemExit(f"No images found under {images_dir}")

    from ultralytics import YOLO
    model = YOLO(str(args.model))
    started = time.perf_counter()
    results = model.predict(
        source=[str(path) for path in images], imgsz=args.imgsz,
        conf=min(thresholds), device="cpu", verbose=False, stream=False,
    )
    rows = []
    for image_path, result in zip(images, results):
        characters, errors = parse_label(labels_dir / f"{image_path.stem}.txt", class_names)
        if errors:
            raise ValueError(f"Invalid ground truth for {image_path.name}: {errors[0]}")
        predictions = []
        if result.boxes is not None:
            for box, class_id, confidence in zip(
                result.boxes.xywhn.cpu().tolist(),
                result.boxes.cls.cpu().tolist(),
                result.boxes.conf.cpu().tolist(),
            ):
                predictions.append({
                    "character": class_names[int(class_id)],
                    "x": box[0], "y": box[1], "width": box[2], "height": box[3],
                    "confidence": confidence,
                })
        rows.append({
            "file": image_path.name,
            "expected": ordered_sequence(characters),
            "predictions": predictions,
        })
    elapsed = time.perf_counter() - started

    metrics_by_threshold = [summarize(rows, threshold) for threshold in thresholds]
    selected = max(
        metrics_by_threshold,
        key=lambda item: (item["exact_plate_accuracy"], item["character_accuracy"], item["confidence_threshold"]),
    )
    for row in rows:
        row["observed"] = predicted_sequence(row["predictions"], selected["confidence_threshold"])
    report = {
        "schema_version": 1,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "dataset": {
            "root": str(args.dataset.resolve()),
            "split": args.split,
            "plates": len(rows),
            "ground_truth": "spatially ordered, consensus-filtered YOLO character labels",
        },
        "model": {
            "path": str(args.model.resolve()),
            "sha256": file_sha256(args.model),
            "framework": "ultralytics",
            "task": "character detection and spatial sequence reconstruction",
        },
        "selection_policy": (
            "Best exact sequence accuracy, then character accuracy, then highest threshold."
            if args.split == "valid" else
            "Confidence threshold fixed from validation before test evaluation."
        ),
        "metrics_by_threshold": metrics_by_threshold,
        "selected_metrics": selected,
        "runtime": {
            "python": sys.version,
            "platform": platform.platform(),
            "device": "cpu",
            "elapsed_seconds": elapsed,
            "images_per_second": len(rows) / elapsed if elapsed else 0.0,
            "image_size": args.imgsz,
        },
        "rows": rows,
        "limitations": [
            "This measures cropped, single-row plates from one dataset, not dealership video events.",
            "The test denominator is too small to establish a 99% production release gate.",
            "Detection confidence is used for thresholding and is not reported as measured accuracy.",
        ],
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"output": str(args.output), "selected_metrics": selected, "runtime": report["runtime"]}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
