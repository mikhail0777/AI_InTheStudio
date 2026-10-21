"""Evaluate LotTrace's production COCO vehicle detector on all COCO val2017 images."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import platform
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ.setdefault("YOLO_CONFIG_DIR", str(ROOT / "backend" / "data" / "ultralytics"))

from scripts.evaluation_metrics import detection_ap, greedy_match, precision_recall_f1, wilson_interval

VEHICLE_CLASSES = {3: "car", 4: "motorcycle", 6: "bus", 8: "truck"}


def sha256(path: Path) -> str:
    hasher = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(8 * 1024 * 1024), b""):
            hasher.update(block)
    return hasher.hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("dataset", type=Path, help="Extracted COCO dataset root")
    parser.add_argument("--model", type=Path, default=ROOT / "backend" / "models" / "yolo11s-seg.pt")
    parser.add_argument("--image-size", type=int, default=1280)
    parser.add_argument("--prediction-confidence", type=float, default=.001,
                        help="Low floor used to construct the precision/recall curve")
    parser.add_argument("--operating-confidence", type=float, default=.25,
                        help="Production confidence threshold used for P/R/F1")
    parser.add_argument("--iou", type=float, default=.5, help="Model NMS IoU")
    parser.add_argument("--batch-size", type=int, default=2)
    parser.add_argument("--limit", type=int)
    parser.add_argument("--output", type=Path, default=ROOT / "evaluation" / "coco_vehicle_results.json")
    parser.add_argument("--checkpoint", type=Path)
    args = parser.parse_args()
    image_root = args.dataset.resolve() / "val2017"
    annotation_path = args.dataset.resolve() / "annotations" / "instances_val2017.json"
    if not image_root.is_dir() or not annotation_path.is_file():
        raise SystemExit(f"Expected val2017 and annotations/instances_val2017.json below {args.dataset}")
    payload = json.loads(annotation_path.read_text(encoding="utf-8"))
    images = sorted(payload["images"], key=lambda item: item["id"])
    if args.limit:
        images = images[:args.limit]
    selected_ids = {item["id"] for item in images}
    truths: dict[int, list[dict]] = {item["id"]: [] for item in images}
    for item in payload["annotations"]:
        if item["image_id"] not in selected_ids or item["category_id"] not in VEHICLE_CLASSES:
            continue
        if item.get("iscrowd", 0):
            continue
        x, y, width, height = item["bbox"]
        area = float(item.get("area", width * height))
        size = "small" if area < 32 ** 2 else "medium" if area < 96 ** 2 else "large"
        truths[item["image_id"]].append({
            "bbox": [x, y, x + width, y + height],
            "class": VEHICLE_CLASSES[item["category_id"]],
            "area": area, "size": size,
        })
    checkpoint = args.checkpoint or args.output.with_suffix(".predictions.jsonl")
    predictions: dict[int, list[dict]] = {}
    if checkpoint.exists():
        for line in checkpoint.read_text(encoding="utf-8").splitlines():
            if line.strip():
                row = json.loads(line)
                image_id = int(row["image_id"])
                if image_id in selected_ids:
                    predictions[image_id] = row["predictions"]
    remaining = [item for item in images if item["id"] not in predictions]
    import torch
    from ultralytics import YOLO
    torch.set_num_threads(max(1, int(os.environ.get("AIEYE_CPU_THREADS", "4"))))
    model = YOLO(str(args.model.resolve()))
    names = {int(key): str(value).lower() for key, value in model.names.items()}
    class_ids = [key for key, value in names.items() if value in set(VEHICLE_CLASSES.values())]
    checkpoint.parent.mkdir(parents=True, exist_ok=True)
    started = time.perf_counter()
    processed = 0
    with checkpoint.open("a", encoding="utf-8") as checkpoint_file:
        for start in range(0, len(remaining), args.batch_size):
            batch = remaining[start:start + args.batch_size]
            paths = [str(image_root / item["file_name"]) for item in batch]
            results = model.predict(
                paths, verbose=False, save=False, classes=class_ids, conf=args.prediction_confidence,
                iou=args.iou, imgsz=args.image_size, device="cpu",
            )
            for image, result in zip(batch, results):
                rows = []
                for box in result.boxes:
                    class_id = int(box.cls.item())
                    rows.append({
                        "bbox": [float(value) for value in box.xyxy[0].cpu().tolist()],
                        "confidence": float(box.conf.item()), "class": names[class_id],
                    })
                predictions[image["id"]] = rows
                checkpoint_file.write(json.dumps({"image_id": image["id"], "predictions": rows}) + "\n")
                checkpoint_file.flush()
            processed += len(batch)
            if processed % 50 == 0 or processed == len(remaining):
                elapsed = time.perf_counter() - started
                print(f"COCO {len(predictions)}/{len(images)} ({processed / elapsed:.2f} new images/s)",
                      file=sys.stderr, flush=True)
    elapsed = time.perf_counter() - started
    per_class = {}
    ap_grid = []
    totals = {label: {"tp": 0, "fp": 0, "fn": 0} for label in VEHICLE_CLASSES.values()}
    for label in VEHICLE_CLASSES.values():
        ap50, ground_truth_count = detection_ap(predictions, truths, .5, label)
        thresholds = [index / 100 for index in range(50, 100, 5)]
        aps = [detection_ap(predictions, truths, threshold, label)[0] for threshold in thresholds]
        ap_grid.extend(aps)
        for image in images:
            image_id = image["id"]
            predicted_boxes = [
                item["bbox"] for item in predictions.get(image_id, [])
                if item["class"] == label and item["confidence"] >= args.operating_confidence
            ]
            truth_boxes = [item["bbox"] for item in truths[image_id] if item["class"] == label]
            matches, unmatched_predictions, unmatched_truths = greedy_match(predicted_boxes, truth_boxes, .5)
            totals[label]["tp"] += len(matches)
            totals[label]["fp"] += len(unmatched_predictions)
            totals[label]["fn"] += len(unmatched_truths)
        per_class[label] = {
            "ground_truth_instances": ground_truth_count,
            "ap_iou_0.50": ap50,
            "ap_iou_0.50_0.95": sum(aps) / len(aps),
            "operating_point_iou_0.50": precision_recall_f1(**totals[label]),
        }
    all_tp = sum(item["tp"] for item in totals.values())
    all_fp = sum(item["fp"] for item in totals.values())
    all_fn = sum(item["fn"] for item in totals.values())
    size_counts = {size: {"matched": 0, "ground_truth": 0} for size in ("small", "medium", "large")}
    for label in VEHICLE_CLASSES.values():
        for image in images:
            image_id = image["id"]
            predicted_boxes = [
                item["bbox"] for item in predictions.get(image_id, [])
                if item["class"] == label and item["confidence"] >= args.operating_confidence
            ]
            selected_truths = [item for item in truths[image_id] if item["class"] == label]
            matches, _, _ = greedy_match(
                predicted_boxes, [item["bbox"] for item in selected_truths], .5,
            )
            matched_truths = {truth_index for _, truth_index, _ in matches}
            for truth_index, truth in enumerate(selected_truths):
                size_counts[truth["size"]]["ground_truth"] += 1
                size_counts[truth["size"]]["matched"] += int(truth_index in matched_truths)
    size_recall = {
        size: {
            **counts,
            "recall": counts["matched"] / counts["ground_truth"] if counts["ground_truth"] else 0.0,
            "recall_wilson_95": wilson_interval(counts["matched"], counts["ground_truth"]),
        }
        for size, counts in size_counts.items()
    }
    negative_ids = [image["id"] for image in images if not truths[image["id"]]]
    negative_false_detections = sum(
        sum(item["confidence"] >= args.operating_confidence for item in predictions.get(image_id, []))
        for image_id in negative_ids
    )
    report = {
        "schema_version": 1,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "dataset": {
            "name": "COCO 2017 val", "images_evaluated": len(images),
            "annotation_file": annotation_path.relative_to(ROOT).as_posix(),
            "annotation_sha256": sha256(annotation_path),
            "ground_truth_vehicle_instances": sum(len(items) for items in truths.values()),
            "negative_images": len(negative_ids),
        },
        "model": {
            "path": args.model.resolve().relative_to(ROOT).as_posix(), "sha256": sha256(args.model),
            "task": model.task, "classes": list(VEHICLE_CLASSES.values()),
            "image_size": args.image_size,
            "prediction_confidence_floor": args.prediction_confidence,
            "operating_confidence_threshold": args.operating_confidence,
            "nms_iou": args.iou, "device": "cpu",
        },
        "runtime": {
            "python": sys.version, "platform": platform.platform(),
            "new_images_processed": processed, "elapsed_seconds": elapsed,
            "new_images_per_second": processed / elapsed if elapsed else 0.0,
        },
        "metrics": {
            "mean_ap_iou_0.50": sum(item["ap_iou_0.50"] for item in per_class.values()) / len(per_class),
            "mean_ap_iou_0.50_0.95": sum(ap_grid) / len(ap_grid),
            "operating_point_iou_0.50": precision_recall_f1(all_tp, all_fp, all_fn),
            "per_class": per_class,
            "recall_by_coco_object_size_at_operating_threshold": size_recall,
            "false_detections_on_negative_images": negative_false_detections,
            "false_detections_per_negative_image": (
                negative_false_detections / len(negative_ids) if negative_ids else 0.0
            ),
        },
        "limitations": [
            "COCO is a general still-image benchmark, not dealership CCTV footage.",
            "This benchmark does not measure tracking, plate-to-vehicle association, colour, make/model/year, or false sightings per hour.",
            "AP uses a 0.001 prediction floor; operating-point precision/recall/F1 use the production 0.25 threshold.",
            "COCO image licensing is image-specific; annotations are CC BY 4.0.",
        ],
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
