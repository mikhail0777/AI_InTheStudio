"""Measure production vehicle association for previously evaluated plate readings."""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import csv
import json
from pathlib import Path
import statistics
import sys
import tempfile
import time


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.services.generic_detector import CandidateFrame, YoloDetectionProvider
from app.services.vehicle_recognizer import VehicleRecognizer, _contains_plate


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--images", required=True, help="Directory containing test images")
    parser.add_argument("--readings", required=True, help="Per-image plate-reading CSV")
    parser.add_argument("--csv", required=True, help="Per-image association CSV output path")
    parser.add_argument("--summary", required=True, help="JSON summary output path")
    args = parser.parse_args()

    images_dir = Path(args.images)
    with Path(args.readings).open(newline="", encoding="utf-8") as handle:
        reading_rows = list(csv.DictReader(handle))
    frames = [
        CandidateFrame(
            frame_id=f"vehicle_{index}", frame_idx=index, timestamp_seconds=float(index),
            image_path=str(images_dir / row["file"]), semantic_similarity=1.0,
        )
        for index, row in enumerate(reading_rows)
    ]

    started = time.perf_counter()
    with tempfile.TemporaryDirectory(prefix="lottrace-vehicle-evaluation-") as evidence_root:
        provider = YoloDetectionProvider(evidence_root)
        detections = provider.detect(frames, ["vehicle"], "dataset", min_confidence=.25)
        provenance = provider.provenance.model_dump(mode="json")
    elapsed = time.perf_counter() - started

    by_frame = defaultdict(list)
    for detection in detections:
        by_frame[detection.frame_idx].append(detection)

    rows = []
    associated_confidences = []
    categories = Counter()
    colors = Counter()
    for index, reading_row in enumerate(reading_rows):
        candidates = by_frame[index]
        serialized_readings = json.loads(reading_row["readings_json"])
        best_plate = max(serialized_readings, key=lambda item: item["confidence"], default=None)
        associated = [] if best_plate is None else [
            item for item in candidates if _contains_plate(item.bbox, best_plate["bbox"])
        ]
        observation = None
        if associated:
            detection = min(
                associated,
                key=lambda item: (
                    (item.bbox[2] - item.bbox[0]) * (item.bbox[3] - item.bbox[1]),
                    -item.confidence,
                ),
            )
            observation = VehicleRecognizer._observation(detection)
            associated_confidences.append(observation.confidence)
            categories[observation.category] += 1
            if observation.color:
                colors[observation.color] += 1
        rows.append({
            "file": reading_row["file"],
            "plate_status": reading_row["status"],
            "vehicle_detection_count": len(candidates),
            "associated": observation is not None,
            "category": observation.category if observation else "",
            "vehicle_confidence": round(observation.confidence, 6) if observation else "",
            "color": observation.color if observation and observation.color else "",
            "color_confidence": round(observation.color_confidence, 6) if observation else "",
        })

    output_csv = Path(args.csv)
    output_csv.parent.mkdir(parents=True, exist_ok=True)
    with output_csv.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)

    read_rows = [row for row in rows if row["plate_status"] == "read"]
    associated_rows = [row for row in read_rows if row["associated"]]
    summary = {
        "images_considered": len(rows),
        "images_with_any_vehicle_detection": sum(bool(by_frame[index]) for index in range(len(rows))),
        "total_vehicle_detections": len(detections),
        "images_with_plate_reading": len(read_rows),
        "plate_readings_associated_with_vehicle": len(associated_rows),
        "association_rate_for_plate_readings": round(
            len(associated_rows) / max(1, len(read_rows)), 4
        ),
        "associated_categories": dict(categories),
        "associated_dominant_colors": dict(colors),
        "mean_associated_vehicle_confidence": round(
            statistics.fmean(associated_confidences), 4
        ) if associated_confidences else 0.0,
        "elapsed_seconds": round(elapsed, 3),
        "images_per_second": round(len(rows) / max(elapsed, 1e-9), 3),
        "model": provenance,
        "limitation": (
            "This plate-focused dataset does not label vehicles; association is measured as "
            "production-path coverage, not vehicle-detection accuracy."
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
