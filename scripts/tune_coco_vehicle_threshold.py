"""Tune the COCO vehicle confidence threshold on one split and confirm on another."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path

from evaluation_metrics import greedy_match, precision_recall_f1

ROOT = Path(__file__).resolve().parents[1]
VEHICLE_CLASSES = {3: "car", 4: "motorcycle", 6: "bus", 8: "truck"}


def load_inputs(annotation_path: Path, prediction_path: Path):
    annotations = json.loads(annotation_path.read_text(encoding="utf-8"))
    image_ids = sorted(item["id"] for item in annotations["images"])
    truths = {image_id: [] for image_id in image_ids}
    for item in annotations["annotations"]:
        if item.get("iscrowd", 0) or item["category_id"] not in VEHICLE_CLASSES:
            continue
        x, y, width, height = item["bbox"]
        truths[item["image_id"]].append({
            "class": VEHICLE_CLASSES[item["category_id"]],
            "bbox": [x, y, x + width, y + height],
        })
    predictions = {}
    for line in prediction_path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            row = json.loads(line)
            predictions[int(row["image_id"])] = row["predictions"]
    missing = [image_id for image_id in image_ids if image_id not in predictions]
    if missing:
        raise SystemExit(f"Prediction checkpoint is missing {len(missing)} COCO images")
    return image_ids, truths, predictions


def score(image_ids, truths, predictions, confidence):
    per_class = {}
    total_tp = total_fp = total_fn = 0
    for label in VEHICLE_CLASSES.values():
        tp = fp = fn = 0
        for image_id in image_ids:
            predicted = [
                item["bbox"] for item in predictions[image_id]
                if item["class"] == label and item["confidence"] >= confidence
            ]
            actual = [item["bbox"] for item in truths[image_id] if item["class"] == label]
            matches, unmatched_predictions, unmatched_truths = greedy_match(predicted, actual, .5)
            tp += len(matches)
            fp += len(unmatched_predictions)
            fn += len(unmatched_truths)
        per_class[label] = precision_recall_f1(tp, fp, fn)
        total_tp += tp
        total_fp += fp
        total_fn += fn
    return {
        "micro": precision_recall_f1(total_tp, total_fp, total_fn),
        "per_class": per_class,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--annotations", type=Path, default=(
        ROOT / "evaluation" / "datasets" / "coco" / "annotations" / "instances_val2017.json"
    ))
    parser.add_argument("--predictions", type=Path, default=(
        ROOT / "evaluation" / "coco_vehicle_predictions.jsonl"
    ))
    parser.add_argument("--output", type=Path, default=(
        ROOT / "evaluation" / "coco_vehicle_threshold_calibration.json"
    ))
    args = parser.parse_args()
    image_ids, truths, predictions = load_inputs(args.annotations, args.predictions)
    # Interleaving the official sorted IDs gives two fixed, equally sized splits.
    tuning_ids = image_ids[::2]
    confirmation_ids = image_ids[1::2]
    thresholds = [round(value / 100, 2) for value in range(5, 51, 5)]
    curve = [{"confidence": threshold, **score(tuning_ids, truths, predictions, threshold)}
             for threshold in thresholds]
    selected = max(curve, key=lambda item: (item["micro"]["f1"], item["confidence"]))
    report = {
        "schema_version": 1,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "selection_policy": "Maximum micro F1 at IoU 0.50 on alternating sorted COCO image IDs.",
        "integrity_note": (
            "This deterministic split was defined after the aggregate full-set baseline had been inspected; "
            "confirmation is useful regression evidence but is not a pristine pre-registered holdout."
        ),
        "tuning_images": len(tuning_ids),
        "confirmation_images": len(confirmation_ids),
        "threshold_curve": curve,
        "selected_confidence": selected["confidence"],
        "tuning_result": {"micro": selected["micro"], "per_class": selected["per_class"]},
        "confirmation_result": score(
            confirmation_ids, truths, predictions, selected["confidence"]
        ),
        "confirmation_at_previous_0.25": score(confirmation_ids, truths, predictions, .25),
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
