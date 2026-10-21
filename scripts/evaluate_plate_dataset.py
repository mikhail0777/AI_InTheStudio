"""Evaluate LotTrace plate localization on a YOLO-labelled image split.

This measures bounding-box detection only. YOLO box labels do not contain plate
text, so the script deliberately does not report OCR character accuracy.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
import time

import cv2

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.services.license_plate_reader import LicensePlateReader, normalize_plate


def iou(left: list[float], right: list[float]) -> float:
    x1, y1 = max(left[0], right[0]), max(left[1], right[1])
    x2, y2 = min(left[2], right[2]), min(left[3], right[3])
    overlap = max(0.0, x2 - x1) * max(0.0, y2 - y1)
    left_area = max(0.0, left[2] - left[0]) * max(0.0, left[3] - left[1])
    right_area = max(0.0, right[2] - right[0]) * max(0.0, right[3] - right[1])
    return overlap / max(1.0, left_area + right_area - overlap)


def labels_for(path: Path, width: int, height: int) -> list[list[float]]:
    boxes = []
    for line in path.read_text(encoding="utf-8").splitlines():
        values = line.split()
        if len(values) != 5:
            continue
        _, cx, cy, w, h = map(float, values)
        boxes.append([
            (cx - w / 2) * width, (cy - h / 2) * height,
            (cx + w / 2) * width, (cy + h / 2) * height,
        ])
    return boxes


def match(predictions: list[list[float]], truth: list[list[float]], threshold: float):
    candidates = sorted(
        ((iou(prediction, target), p, t)
         for p, prediction in enumerate(predictions)
         for t, target in enumerate(truth)),
        reverse=True,
    )
    used_predictions, used_truth, overlaps = set(), set(), []
    for score, prediction, target in candidates:
        if score < threshold:
            break
        if prediction in used_predictions or target in used_truth:
            continue
        used_predictions.add(prediction)
        used_truth.add(target)
        overlaps.append(score)
    tp = len(overlaps)
    return tp, len(predictions) - tp, len(truth) - tp, overlaps


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("dataset", help="Dataset root containing test/images and test/labels")
    parser.add_argument("--split", default="test")
    parser.add_argument("--output")
    args = parser.parse_args()
    split = Path(args.dataset).resolve() / args.split
    image_dir, label_dir = split / "images", split / "labels"
    if not image_dir.is_dir() or not label_dir.is_dir():
        raise SystemExit(f"Expected images and labels below {split}")
    images = sorted(path for path in image_dir.iterdir() if path.suffix.lower() in {".jpg", ".jpeg", ".png"})
    reader = LicensePlateReader()
    totals = {threshold: {"tp": 0, "fp": 0, "fn": 0, "ious": []} for threshold in (.5, .7)}
    ground_truth = predictions = readable = invalid = missing_labels = 0
    started = time.perf_counter()
    for number, image_path in enumerate(images, start=1):
        frame = cv2.imread(str(image_path))
        if frame is None or frame.size == 0:
            invalid += 1
            continue
        label_path = label_dir / f"{image_path.stem}.txt"
        if not label_path.is_file():
            missing_labels += 1
            continue
        height, width = frame.shape[:2]
        truth = labels_for(label_path, width, height)
        results = reader.reader.predict(frame)
        detected = []
        for result in results:
            box = result.detection.bounding_box
            detected.append([float(box.x1), float(box.y1), float(box.x2), float(box.y2)])
            text = normalize_plate(result.ocr.text) if result.ocr else ""
            readable += int(4 <= len(text) <= 10)
        ground_truth += len(truth)
        predictions += len(detected)
        for threshold, counts in totals.items():
            tp, fp, fn, overlaps = match(detected, truth, threshold)
            counts["tp"] += tp
            counts["fp"] += fp
            counts["fn"] += fn
            counts["ious"].extend(overlaps)
        if number % 100 == 0:
            print(f"Evaluated {number}/{len(images)}", file=sys.stderr, flush=True)
    elapsed = time.perf_counter() - started
    metrics = {}
    for threshold, counts in totals.items():
        tp, fp, fn = counts["tp"], counts["fp"], counts["fn"]
        precision = tp / (tp + fp) if tp + fp else 0.0
        recall = tp / (tp + fn) if tp + fn else 0.0
        metrics[f"iou_{threshold:.2f}"] = {
            "true_positive": tp, "false_positive": fp, "false_negative": fn,
            "precision": round(precision, 4), "recall": round(recall, 4),
            "f1": round(2 * precision * recall / (precision + recall), 4) if precision + recall else 0.0,
            "mean_matched_iou": round(sum(counts["ious"]) / len(counts["ious"]), 4) if counts["ious"] else 0.0,
        }
    report = {
        "dataset": str(split), "images_evaluated": len(images) - invalid - missing_labels,
        "missing_labels": missing_labels, "invalid_images": invalid,
        "ground_truth_plates": ground_truth, "predicted_plates": predictions,
        "plausible_ocr_predictions": readable,
        "metrics": metrics, "elapsed_seconds": round(elapsed, 3),
        "images_per_second": round((len(images) - invalid) / elapsed, 3),
        "model": reader.provenance.model_dump(mode="json"),
        "limitation": "The labels contain plate boxes but no plate text; OCR character accuracy cannot be calculated.",
    }
    rendered = json.dumps(report, indent=2)
    print(rendered)
    if args.output:
        Path(args.output).write_text(rendered + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
