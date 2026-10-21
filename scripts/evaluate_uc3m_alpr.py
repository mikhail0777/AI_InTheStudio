"""Evaluate LotTrace plate localization and OCR on labelled UC3M-LP images.

The default ``production`` mode exercises ``LicensePlateReader.read_frame``
(full frame, overlapping tiles, de-duplication, and guarded mirror fallback).
UC3M masks two privacy-sensitive characters in every plate with ``*``. The
script therefore reports accuracy on published character positions and never
mislabels that result as exact full-plate accuracy.
"""
from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import platform
import sys
import time

import cv2

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "backend"))

from app.services.license_plate_reader import LicensePlateReader, normalize_plate
from scripts.evaluation_metrics import greedy_match, levenshtein, precision_recall_f1, wilson_interval


def annotation(path: Path) -> tuple[list[dict], str]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    plates = []
    for item in payload.get("lps", []):
        coordinates = item["poly_coord"]
        x_values = [float(point[0]) for point in coordinates]
        y_values = [float(point[1]) for point in coordinates]
        identifier = str(item.get("lp_id", ""))
        code, _, labelled_text = identifier.partition("-")
        template = "".join(char for char in labelled_text.upper() if char.isalnum() or char == "*")
        plates.append({
            "bbox": [min(x_values), min(y_values), max(x_values), max(y_values)],
            "text": normalize_plate(labelled_text.replace("*", "")),
            "template": template,
            "published_characters": sum(char != "*" for char in template),
            "fully_readable": bool(labelled_text) and "*" not in labelled_text,
            "plate_type": code[:1] or "unknown",
            "lighting": code[1:2] or "unknown",
            "label": identifier,
        })
    return plates, str(payload.get("imagePath", path.with_suffix(".jpg").name))


def masked_edit_distance(template: str, observed: str) -> int:
    """Levenshtein distance where a published ``*`` matches any one character."""
    previous = list(range(len(observed) + 1))
    for row, expected in enumerate(template, start=1):
        deletion_cost = 0 if expected == "*" else 1
        current = [previous[0] + deletion_cost]
        for column, actual in enumerate(observed, start=1):
            substitution = 0 if expected == "*" or expected == actual else 1
            current.append(min(
                current[-1] + 1,
                previous[column] + deletion_cost,
                previous[column - 1] + substitution,
            ))
        previous = current
    return previous[-1]


def summarize_ocr(rows: list[dict]) -> dict:
    eligible = [row for row in rows if row["template"]]
    visible_exact = sum(masked_edit_distance(row["template"], row["observed"]) == 0
                        for row in eligible)
    localized = sum(bool(row["observed"]) for row in eligible)
    edits = sum(masked_edit_distance(row["template"], row["observed"]) for row in eligible)
    characters = sum(sum(char != "*" for char in row["template"]) for row in eligible)
    return {
        "plates_with_published_partial_transcription": len(eligible),
        "localized_and_read": localized,
        "read_coverage": localized / len(eligible) if eligible else 0.0,
        "published_position_exact_matches": visible_exact,
        "published_position_plate_accuracy": visible_exact / len(eligible) if eligible else 0.0,
        "published_position_plate_accuracy_wilson_95": wilson_interval(visible_exact, len(eligible)),
        "published_character_edits": edits,
        "published_ground_truth_characters": characters,
        "published_character_error_rate": edits / characters if characters else 0.0,
        "published_normalized_edit_similarity": 1 - edits / characters if characters else 0.0,
        "full_exact_plate_accuracy": None,
        "full_exact_plate_accuracy_reason": "UC3M-LP masks two characters in every published plate string.",
        "top_k_full_plate_accuracy": None,
    }


def search_metrics(images: list[dict], partial_length: int = 2) -> dict:
    templates = sorted({template for image in images for template in image["templates"]})
    partial_queries = sorted({
        template[start:start + partial_length]
        for template in templates if len(template) >= partial_length
        for start in range(len(template) - partial_length + 1)
        if "*" not in template[start:start + partial_length]
    })

    def measure(queries: list[str], partial: bool) -> dict:
        tp = fp = fn = 0
        for query in queries:
            relevant = {
                image["key"] for image in images
                if any(query in template if partial else query == template for template in image["templates"])
            }
            retrieved = {
                image["key"] for image in images
                if any(query in observed if partial else query == observed for observed in image["observed"])
            }
            tp += len(relevant & retrieved)
            fp += len(retrieved - relevant)
            fn += len(relevant - retrieved)
        return {"queries": len(queries), **precision_recall_f1(tp, fp, fn)}

    return {
        "exact": {"available": False, "reason": "Every UC3M-LP plate transcription masks two characters."},
        f"partial_{partial_length}_character": measure(partial_queries, True),
    }


def model_files() -> list[dict]:
    output = []
    for cache in (Path.home() / ".cache" / "fast-plate-ocr",
                  Path.home() / ".cache" / "open-image-models"):
        if not cache.exists():
            continue
        for path in sorted(cache.rglob("*")):
            if path.is_file():
                hasher = hashlib.sha256()
                with path.open("rb") as handle:
                    for block in iter(lambda: handle.read(4 * 1024 * 1024), b""):
                        hasher.update(block)
                output.append({
                    "path": f"~/.cache/{path.relative_to(Path.home() / '.cache').as_posix()}",
                    "bytes": path.stat().st_size,
                    "sha256": hasher.hexdigest(),
                })
    return output


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("dataset", type=Path, help="Extracted UC3M-LP root")
    parser.add_argument("--split", choices=["train", "test", "all"], default="all")
    parser.add_argument("--mode", choices=["production", "full-frame"], default="production")
    parser.add_argument("--output", type=Path, default=ROOT / "evaluation" / "uc3m_alpr_results.json")
    parser.add_argument("--limit", type=int)
    args = parser.parse_args()
    split_names = ["train", "test"] if args.split == "all" else [args.split]
    samples = []
    for split_name in split_names:
        directory = args.dataset.resolve() / split_name
        if not directory.is_dir():
            raise SystemExit(f"Missing UC3M split: {directory}")
        for label_path in sorted(directory.glob("*.json")):
            truth, _declared_image_name = annotation(label_path)
            # The published JSON imagePath is systematically offset by one.
            # UC3M's documented on-disk contract pairs same-stem JPG/JSON sidecars.
            image_path = label_path.with_suffix(".jpg")
            samples.append((split_name, image_path, truth))
    if args.limit:
        samples = samples[:args.limit]
    reader = LicensePlateReader()
    totals = {threshold: {"tp": 0, "fp": 0, "fn": 0, "ious": []} for threshold in (.5, .7)}
    ocr_rows: list[dict] = []
    search_images: list[dict] = []
    per_split: dict[str, list[dict]] = {name: [] for name in split_names}
    confusion = Counter()
    invalid = 0
    started = time.perf_counter()
    for index, (split_name, image_path, truths) in enumerate(samples, start=1):
        frame = cv2.imread(str(image_path))
        if frame is None or frame.size == 0:
            invalid += 1
            continue
        if args.mode == "production":
            readings = reader.read_frame(frame)
            predictions = [{"bbox": item.bbox, "text": item.text, "confidence": item.confidence}
                           for item in readings]
        else:
            predictions = []
            for result in reader.reader.predict(frame):
                box = result.detection.bounding_box
                predictions.append({
                    "bbox": [box.x1, box.y1, box.x2, box.y2],
                    "text": normalize_plate(result.ocr.text) if result.ocr else "",
                    "confidence": float(result.detection.confidence),
                })
        predicted_boxes = [item["bbox"] for item in predictions]
        truth_boxes = [item["bbox"] for item in truths]
        search_images.append({
            "key": f"{split_name}/{image_path.name}",
            "templates": [item["template"] for item in truths],
            "observed": [item["text"] for item in predictions if item["text"]],
        })
        for threshold, counts in totals.items():
            matches, unmatched_predictions, unmatched_truths = greedy_match(
                predicted_boxes, truth_boxes, threshold,
            )
            counts["tp"] += len(matches)
            counts["fp"] += len(unmatched_predictions)
            counts["fn"] += len(unmatched_truths)
            counts["ious"].extend(match[2] for match in matches)
        matches, _, unmatched_truths = greedy_match(predicted_boxes, truth_boxes, .5)
        matched_truths = set()
        for pred_index, truth_index, overlap in matches:
            truth = truths[truth_index]
            observed = predictions[pred_index]["text"]
            row = {
                "split": split_name, "image": image_path.name,
                "expected": truth["text"], "observed": observed,
                "template": truth["template"], "eligible": True, "iou": overlap,
                "lighting": truth["lighting"], "plate_type": truth["plate_type"],
            }
            ocr_rows.append(row)
            per_split[split_name].append(row)
            matched_truths.add(truth_index)
            if masked_edit_distance(truth["template"], observed):
                for expected_char, observed_char in zip(truth["template"], observed):
                    if expected_char != "*" and expected_char != observed_char:
                        confusion[(expected_char, observed_char)] += 1
        for truth_index in unmatched_truths:
            truth = truths[truth_index]
            row = {
                "split": split_name, "image": image_path.name,
                "expected": truth["text"], "observed": "",
                "template": truth["template"], "eligible": True, "iou": 0.0,
                "lighting": truth["lighting"], "plate_type": truth["plate_type"],
            }
            ocr_rows.append(row)
            per_split[split_name].append(row)
        if index % 25 == 0:
            elapsed = time.perf_counter() - started
            print(f"UC3M {index}/{len(samples)} ({index / elapsed:.2f} images/s)", file=sys.stderr, flush=True)
    elapsed = time.perf_counter() - started
    localization = {}
    for threshold, counts in totals.items():
        metrics = precision_recall_f1(counts["tp"], counts["fp"], counts["fn"])
        metrics["mean_matched_iou"] = (sum(counts["ious"]) / len(counts["ious"])
                                        if counts["ious"] else 0.0)
        localization[f"iou_{threshold:.2f}"] = metrics
    report = {
        "schema_version": 1,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "dataset": {
            "name": "UC3M-LP", "version": "Zenodo record 17152029",
            "root": args.dataset.resolve().relative_to(ROOT).as_posix(), "split": args.split,
            "license": "ODbL-1.0", "images_selected": len(samples),
            "images_evaluated": len(samples) - invalid, "invalid_images": invalid,
            "ground_truth_plates": len(ocr_rows),
            "image_pairing_policy": "Same-stem JPG/JSON sidecars; embedded imagePath is ignored because it is systematically offset by one.",
        },
        "runtime": {
            "python": sys.version, "platform": platform.platform(), "device": "cpu",
            "elapsed_seconds": elapsed,
            "images_per_second": (len(samples) - invalid) / elapsed if elapsed else 0.0,
        },
        "model": reader.provenance.model_dump(mode="json"),
        "model_files": model_files(),
        "inference_mode": args.mode,
        "localization": localization,
        "ocr": summarize_ocr(ocr_rows),
        "ocr_by_split": {name: summarize_ocr(rows) for name, rows in per_split.items()},
        "ocr_by_lighting": {
            label: summarize_ocr([row for row in ocr_rows if row["lighting"] == label])
            for label in sorted({row["lighting"] for row in ocr_rows})
        },
        "search": search_metrics(search_images),
        "common_substitutions": [
            {"expected": pair[0], "observed": pair[1], "count": count}
            for pair, count in confusion.most_common(20)
        ],
        "limitations": [
            "UC3M-LP contains Spanish/European plates, not a dealership deployment sample.",
            "UC3M-LP masks two privacy-sensitive characters in every plate; full exact-plate accuracy and full-plate top-k accuracy cannot be calculated.",
            "Published-position accuracy and character error rate score only the characters UC3M-LP releases; they are not full OCR accuracy.",
            "Production mode ranks/deduplicates with OCR confidence; localization metrics are operating-point metrics, not COCO AP.",
        ],
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
