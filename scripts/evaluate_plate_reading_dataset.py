"""Run the production plate-reading path over every image in a directory."""
from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
import statistics
import sys
import time

import cv2


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.services.license_plate_reader import LicensePlateReader


CSV_FIELDS = (
    "file", "width", "height", "reading_count", "best_text", "best_confidence",
    "best_source_variant", "ground_truth_count", "best_ground_truth_iou",
    "readings_json", "status",
)


def load_yolo_boxes(path: Path, width: int, height: int) -> list[list[float]]:
    boxes = []
    if not path.exists():
        return boxes
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


def intersection_over_union(left: list[float], right: list[float]) -> float:
    x1, y1 = max(left[0], right[0]), max(left[1], right[1])
    x2, y2 = min(left[2], right[2]), min(left[3], right[3])
    intersection = max(0.0, x2 - x1) * max(0.0, y2 - y1)
    left_area = max(0.0, left[2] - left[0]) * max(0.0, left[3] - left[1])
    right_area = max(0.0, right[2] - right[0]) * max(0.0, right[3] - right[1])
    return intersection / max(1.0, left_area + right_area - intersection)


def percentile(values: list[float], fraction: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    position = (len(ordered) - 1) * fraction
    lower = int(position)
    upper = min(lower + 1, len(ordered) - 1)
    weight = position - lower
    return ordered[lower] * (1 - weight) + ordered[upper] * weight


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--images", required=True, help="Directory containing test images")
    parser.add_argument("--csv", required=True, help="Per-image CSV output path")
    parser.add_argument("--summary", required=True, help="JSON summary output path")
    parser.add_argument("--labels", help="Optional directory containing YOLO-format labels")
    parser.add_argument("--limit", type=int, default=None, help="Optional deterministic image limit")
    args = parser.parse_args()

    images_dir = Path(args.images)
    image_paths = sorted(
        path for path in images_dir.iterdir()
        if path.is_file() and path.suffix.lower() in {".jpg", ".jpeg", ".png", ".bmp", ".webp"}
    )
    if args.limit is not None:
        if args.limit < 1:
            raise SystemExit("--limit must be at least 1")
        image_paths = image_paths[:args.limit]
    if not image_paths:
        raise SystemExit(f"No supported images found under {images_dir}")

    reader = LicensePlateReader()
    labels_dir = Path(args.labels) if args.labels else None
    rows: list[dict[str, object]] = []
    invalid_images = 0
    started = time.perf_counter()
    for position, image_path in enumerate(image_paths, start=1):
        image = cv2.imread(str(image_path))
        if image is None or image.size == 0:
            invalid_images += 1
            rows.append({
                "file": image_path.name, "width": 0, "height": 0, "reading_count": 0,
                "best_text": "", "best_confidence": "", "best_source_variant": "",
                "ground_truth_count": "", "best_ground_truth_iou": "",
                "readings_json": "[]", "status": "invalid_image",
            })
            continue
        readings = reader.read_frame(image)
        best = max(readings, key=lambda item: item.confidence, default=None)
        ground_truth = load_yolo_boxes(
            labels_dir / f"{image_path.stem}.txt", image.shape[1], image.shape[0]
        ) if labels_dir else []
        best_iou = max(
            (intersection_over_union(best.bbox, box) for box in ground_truth), default=0.0
        ) if best else 0.0
        rows.append({
            "file": image_path.name,
            "width": image.shape[1],
            "height": image.shape[0],
            "reading_count": len(readings),
            "best_text": best.text if best else "",
            "best_confidence": round(best.confidence, 6) if best else "",
            "best_source_variant": best.source_variant if best else "",
            "ground_truth_count": len(ground_truth) if labels_dir else "",
            "best_ground_truth_iou": round(best_iou, 6) if labels_dir and best else "",
            "readings_json": json.dumps([
                {
                    "text": item.text,
                    "confidence": round(item.confidence, 6),
                    "bbox": item.bbox,
                    "source_variant": item.source_variant,
                }
                for item in readings
            ], separators=(",", ":")),
            "status": "read" if best else "no_read",
        })
        if position % 100 == 0:
            print(f"Processed {position}/{len(image_paths)} images", file=sys.stderr, flush=True)

    elapsed = time.perf_counter() - started
    output_csv = Path(args.csv)
    output_csv.parent.mkdir(parents=True, exist_ok=True)
    with output_csv.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=CSV_FIELDS)
        writer.writeheader()
        writer.writerows(rows)

    valid_rows = [row for row in rows if row["status"] != "invalid_image"]
    read_rows = [row for row in valid_rows if row["status"] == "read"]
    confidences = [float(row["best_confidence"]) for row in read_rows]
    best_original = sum(row["best_source_variant"] == "original" for row in read_rows)
    best_mirrored = sum(row["best_source_variant"] == "horizontal_flip" for row in read_rows)
    summary = {
        "images_directory": str(images_dir.resolve()),
        "images_considered": len(image_paths),
        "images_evaluated": len(valid_rows),
        "invalid_images": invalid_images,
        "images_with_reading": len(read_rows),
        "images_without_reading": len(valid_rows) - len(read_rows),
        "image_read_coverage": round(len(read_rows) / max(1, len(valid_rows)), 4),
        "total_readings": sum(int(row["reading_count"]) for row in valid_rows),
        "best_reading_source": {
            "original": best_original,
            "horizontal_flip": best_mirrored,
        },
        "best_confidence": {
            "mean": round(statistics.fmean(confidences), 4) if confidences else 0.0,
            "median": round(statistics.median(confidences), 4) if confidences else 0.0,
            "p10": round(percentile(confidences, .10), 4),
            "p90": round(percentile(confidences, .90), 4),
            "at_least_0.72": sum(value >= .72 for value in confidences),
            "0.50_to_0.72": sum(.50 <= value < .72 for value in confidences),
            "below_0.50": sum(value < .50 for value in confidences),
        },
        "elapsed_seconds": round(elapsed, 3),
        "images_per_second": round(len(valid_rows) / max(elapsed, 1e-9), 3),
        "model": reader.provenance.model_dump(mode="json"),
        "limitation": (
            "The dataset has plate bounding boxes but no character transcriptions; "
            "read coverage and confidence are not OCR text accuracy."
        ),
    }
    if labels_dir:
        summary["best_reading_localization"] = {
            "images_with_ground_truth": sum(int(row["ground_truth_count"]) > 0 for row in valid_rows),
            "matched_at_iou_0.50": sum(
                row["best_ground_truth_iou"] != "" and float(row["best_ground_truth_iou"]) >= .50
                for row in valid_rows
            ),
            "unmatched_or_no_read": sum(
                int(row["ground_truth_count"]) > 0
                and (row["best_ground_truth_iou"] == "" or float(row["best_ground_truth_iou"]) < .50)
                for row in valid_rows
            ),
            "mirrored_best_matched_at_iou_0.50": sum(
                row["best_source_variant"] == "horizontal_flip"
                and row["best_ground_truth_iou"] != ""
                and float(row["best_ground_truth_iou"]) >= .50
                for row in valid_rows
            ),
        }
    rendered = json.dumps(summary, indent=2)
    output_summary = Path(args.summary)
    output_summary.parent.mkdir(parents=True, exist_ok=True)
    output_summary.write_text(rendered + "\n", encoding="utf-8")
    print(rendered)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
