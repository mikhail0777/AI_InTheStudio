"""Evaluate LotTrace plate localization against a YOLO-format test split."""
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


def intersection_over_union(left: list[float], right: list[float]) -> float:
    x1, y1 = max(left[0], right[0]), max(left[1], right[1])
    x2, y2 = min(left[2], right[2]), min(left[3], right[3])
    intersection = max(0.0, x2 - x1) * max(0.0, y2 - y1)
    left_area = max(0.0, left[2] - left[0]) * max(0.0, left[3] - left[1])
    right_area = max(0.0, right[2] - right[0]) * max(0.0, right[3] - right[1])
    return intersection / max(1.0, left_area + right_area - intersection)


def match_boxes(ground_truth: list[list[float]], predictions: list[list[float]], threshold: float):
    candidates = sorted(
        ((intersection_over_union(gt, pred), gt_index, pred_index)
         for gt_index, gt in enumerate(ground_truth)
         for pred_index, pred in enumerate(predictions)),
        reverse=True,
    )
    matched_gt, matched_pred, matches = set(), set(), []
    for iou, gt_index, pred_index in candidates:
        if iou < threshold:
            break
        if gt_index in matched_gt or pred_index in matched_pred:
            continue
        matched_gt.add(gt_index)
        matched_pred.add(pred_index)
        matches.append((gt_index, pred_index, iou))
    return matches


def load_yolo_boxes(path: Path, width: int, height: int) -> list[list[float]]:
    boxes = []
    for line in path.read_text(encoding="utf-8").splitlines():
        values = line.split()
        if len(values) != 5 or values[0] != "0":
            continue
        center_x, center_y, box_width, box_height = map(float, values[1:])
        boxes.append([
            (center_x - box_width / 2) * width,
            (center_y - box_height / 2) * height,
            (center_x + box_width / 2) * width,
            (center_y + box_height / 2) * height,
        ])
    return boxes


def summarize(counts: dict[str, float]) -> dict[str, float | int]:
    true_positive = int(counts["true_positive"])
    false_positive = int(counts["false_positive"])
    false_negative = int(counts["false_negative"])
    precision = true_positive / max(1, true_positive + false_positive)
    recall = true_positive / max(1, true_positive + false_negative)
    return {
        "true_positive": true_positive,
        "false_positive": false_positive,
        "false_negative": false_negative,
        "precision": round(precision, 4),
        "recall": round(recall, 4),
        "f1": round(2 * precision * recall / max(1e-12, precision + recall), 4),
        "mean_matched_iou": round(counts["iou_sum"] / max(1, true_positive), 4),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", required=True, help="Dataset root containing test/images and test/labels")
    parser.add_argument("--limit", type=int, default=None, help="Optional deterministic image limit")
    parser.add_argument("--output", help="Optional JSON report path")
    args = parser.parse_args()
    root = Path(args.dataset)
    images_dir, labels_dir = root / "test" / "images", root / "test" / "labels"
    images = sorted(images_dir.glob("*.jpg"))
    if args.limit is not None:
        if args.limit < 1:
            raise SystemExit("--limit must be at least 1")
        images = images[:args.limit]
    if not images:
        raise SystemExit(f"No JPG test images found under {images_dir}")

    reader = LicensePlateReader()
    thresholds = (0.5, 0.7)
    totals = {threshold: {"true_positive": 0, "false_positive": 0,
                          "false_negative": 0, "iou_sum": 0.0} for threshold in thresholds}
    gt_total = prediction_total = readable_predictions = images_with_gt = images_with_detection = 0
    missing_labels = invalid_images = 0
    started = time.perf_counter()
    for position, image_path in enumerate(images, start=1):
        label_path = labels_dir / f"{image_path.stem}.txt"
        if not label_path.exists():
            missing_labels += 1
            continue
        image = cv2.imread(str(image_path))
        if image is None or image.size == 0:
            invalid_images += 1
            continue
        height, width = image.shape[:2]
        ground_truth = load_yolo_boxes(label_path, width, height)
        raw_predictions = reader.reader.predict(image)
        predictions = []
        for result in raw_predictions:
            box = result.detection.bounding_box
            predictions.append([float(box.x1), float(box.y1), float(box.x2), float(box.y2)])
            if result.ocr and 4 <= len(normalize_plate(result.ocr.text)) <= 10:
                readable_predictions += 1
        gt_total += len(ground_truth)
        prediction_total += len(predictions)
        images_with_gt += bool(ground_truth)
        images_with_detection += bool(predictions)
        for threshold in thresholds:
            matches = match_boxes(ground_truth, predictions, threshold)
            totals[threshold]["true_positive"] += len(matches)
            totals[threshold]["false_positive"] += len(predictions) - len(matches)
            totals[threshold]["false_negative"] += len(ground_truth) - len(matches)
            totals[threshold]["iou_sum"] += sum(match[2] for match in matches)
        if position % 100 == 0:
            print(f"Processed {position}/{len(images)} images", file=sys.stderr, flush=True)

    elapsed = time.perf_counter() - started
    report = {
        "dataset": str(root),
        "images_evaluated": len(images) - missing_labels - invalid_images,
        "missing_labels": missing_labels,
        "invalid_images": invalid_images,
        "ground_truth_plates": gt_total,
        "predicted_plates": prediction_total,
        "images_with_ground_truth": images_with_gt,
        "images_with_any_detection": images_with_detection,
        "readable_ocr_predictions": readable_predictions,
        "ocr_coverage_of_predictions": round(readable_predictions / max(1, prediction_total), 4),
        "metrics": {f"iou_{threshold:.2f}": summarize(totals[threshold]) for threshold in thresholds},
        "elapsed_seconds": round(elapsed, 3),
        "images_per_second": round((len(images) - missing_labels - invalid_images) / max(elapsed, 1e-9), 3),
        "model": reader.provenance.model_dump(mode="json"),
        "limitation": "Dataset labels contain plate boxes but no plate text; OCR character accuracy cannot be calculated.",
    }
    rendered = json.dumps(report, indent=2)
    print(rendered)
    if args.output:
        Path(args.output).write_text(rendered + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
