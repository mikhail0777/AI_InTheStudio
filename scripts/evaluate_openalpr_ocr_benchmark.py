"""Freeze and evaluate a deterministic sample of the official OpenALPR OCR benchmark."""
from __future__ import annotations

import argparse
import csv
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import platform
import random
import sys
import time

import cv2


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "backend"))

from app.services.license_plate_reader import LicensePlateReader, normalize_plate
from scripts.evaluation_metrics import levenshtein, wilson_interval
from scripts.prepare_readable_plate_benchmark import dhash, hamming, iter_reference_hashes, sha256_file


# Selected once on the 300-image development split, before the final split is
# consumed. Confidence is an acceptance gate, not a replacement for accuracy.
AUTO_ACCEPT_CONFIDENCE = 0.9995


def load_ground_truth(dataset: Path) -> list[dict]:
    truth_path = dataset / "groundtruth.csv"
    images_dir = dataset / "usimages"
    rows: list[dict] = []
    with truth_path.open(encoding="utf-8-sig", newline="") as handle:
        for line_number, fields in enumerate(csv.reader(handle), 1):
            if len(fields) != 3:
                raise ValueError(f"{truth_path}:{line_number}: expected 3 fields")
            filename, state, expected = (field.strip() for field in fields)
            expected = normalize_plate(expected)
            image_path = images_dir / filename
            if not image_path.is_file():
                raise FileNotFoundError(image_path)
            if not 1 <= len(expected) <= 10:
                raise ValueError(f"{filename}: invalid ground truth {expected!r}")
            rows.append({"file": filename, "state": state, "expected": expected, "path": image_path})
    if not rows:
        raise ValueError("Ground-truth file is empty")
    return rows


def select_rows(rows: list[dict], count: int, seed: int) -> list[dict]:
    if not 1 <= count <= len(rows):
        raise ValueError(f"count must be between 1 and {len(rows)}")
    selected = list(rows)
    random.Random(seed).shuffle(selected)
    return sorted(selected[:count], key=lambda row: row["file"])


def split_rows(rows: list[dict], development_count: int, seed: int) -> tuple[list[dict], list[dict]]:
    development = select_rows(rows, development_count, seed)
    development_files = {row["file"] for row in development}
    final = sorted((row for row in rows if row["file"] not in development_files), key=lambda row: row["file"])
    return development, final


def exclude_local_training_overlap(
    rows: list[dict], reference_directories: list[Path], near_duplicate_distance: int = 1,
) -> tuple[list[dict], dict]:
    references = iter_reference_hashes(reference_directories)
    eligible: list[dict] = []
    exact_rejections = near_rejections = 0
    for row in rows:
        image = cv2.imread(str(row["path"]))
        exact = sha256_file(row["path"])
        perceptual = dhash(image)
        if any(exact == reference_exact for reference_exact, _ in references):
            exact_rejections += 1
        elif any(hamming(perceptual, reference_perceptual) <= near_duplicate_distance for _, reference_perceptual in references):
            near_rejections += 1
        else:
            eligible.append(row)
    return eligible, {
        "reference_images_hashed": len(references),
        "exact_overlap_rejections": exact_rejections,
        "near_duplicate_rejections": near_rejections,
        "near_duplicate_hamming_distance": near_duplicate_distance,
        "reference_directories": [str(path.resolve()) for path in reference_directories],
    }


def summarize(rows: list[dict], *, auto_accept_confidence: float = AUTO_ACCEPT_CONFIDENCE) -> dict:
    total = len(rows)
    exact = sum(row["predicted"] == row["expected"] for row in rows)
    topk_exact = sum(row["expected"] in row.get("candidates", [row["predicted"]]) for row in rows)
    with_read = sum(bool(row["predicted"]) for row in rows)
    characters = sum(len(row["expected"]) for row in rows)
    edits = sum(levenshtein(row["predicted"], row["expected"]) for row in rows)
    accepted = [
        row for row in rows
        if row.get("confidence") is not None
        and float(row["confidence"]) >= auto_accept_confidence
    ]
    accepted_exact = sum(row["predicted"] == row["expected"] for row in accepted)
    return {
        "plates": total,
        "plates_with_reading": with_read,
        "read_coverage": with_read / total if total else None,
        "exact_matches": exact,
        "exact_plate_accuracy": exact / total if total else None,
        "exact_plate_accuracy_wilson_95": wilson_interval(exact, total) if total else None,
        "topk_exact_matches": topk_exact,
        "topk_exact_plate_accuracy": topk_exact / total if total else None,
        "ground_truth_characters": characters,
        "character_edits": edits,
        "character_error_rate": edits / characters if characters else None,
        "character_accuracy": 1 - edits / characters if characters else None,
        "operational_acceptance": {
            "policy": "accept_at_or_above_fixed_ocr_confidence_else_review",
            "confidence_threshold": auto_accept_confidence,
            "accepted": len(accepted),
            "sent_to_review": total - len(accepted),
            "acceptance_coverage": len(accepted) / total if total else None,
            "accepted_exact_matches": accepted_exact,
            "accepted_exact_precision": accepted_exact / len(accepted) if accepted else None,
            "accepted_exact_precision_wilson_95": (
                wilson_interval(accepted_exact, len(accepted)) if accepted else None
            ),
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--count", type=int, default=300, help="Development split size; the remainder is final.")
    parser.add_argument("--seed", type=int, default=20261022)
    parser.add_argument("--split", choices=("development", "final"), default="development")
    parser.add_argument("--confirm-final", action="store_true", help="Required to consume the untouched final split.")
    parser.add_argument(
        "--exclude-images", type=Path, action="append",
        default=[
            ROOT / "datasets/extracted/plate_ocr_36_consensus/train/images",
            ROOT / "datasets/extracted/plate_ocr_31/train/images",
        ],
        help="Local OCR training directory to reject exact/perceptual overlaps against (repeatable).",
    )
    args = parser.parse_args()

    eligible, overlap_audit = exclude_local_training_overlap(load_ground_truth(args.dataset), args.exclude_images)
    development, final = split_rows(eligible, args.count, args.seed)
    if args.split == "final" and not args.confirm_final:
        raise SystemExit("Refusing to consume the final split without --confirm-final")
    selected = development if args.split == "development" else final
    records = [
        {
            "sample_id": f"openalpr_{index:04d}",
            "image": str(row["path"].resolve()),
            "image_sha256": sha256_file(row["path"]),
            "state": row["state"],
            "expected": row["expected"],
        }
        for index, row in enumerate(selected, 1)
    ]
    frozen = {
        "schema_version": 1,
        "status": "frozen_before_ocr_evaluation",
        "frozen_at": datetime.now(timezone.utc).isoformat(),
        "source": "OpenALPR/benchmarks seg_and_ocr",
        "license": "AGPL-3.0",
        "selection": {
            "available": 751,
            "eligible_after_local_training_overlap_audit": len(eligible),
            "split": args.split,
            "development_count": len(development),
            "final_count": len(final),
            "selected": len(records),
            "seed": args.seed,
            "local_training_overlap_audit": overlap_audit,
        },
        "records": records,
    }
    manifest_bytes = (json.dumps(frozen, indent=2) + "\n").encode()
    manifest_path = args.output.with_name(args.output.stem + "_frozen_manifest.json")
    checksum_path = manifest_path.with_suffix(".sha256")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_bytes(manifest_bytes)
    checksum_path.write_text(f"{hashlib.sha256(manifest_bytes).hexdigest()}  {manifest_path.name}\n", encoding="ascii")

    # Instantiate the production reader only after the selection and truth are frozen.
    reader = LicensePlateReader()
    results: list[dict] = []
    started = time.perf_counter()
    for index, record in enumerate(records, 1):
        image = cv2.imread(record["image"])
        readings = reader.read_crop(image, source_variant="ground_truth_crop")
        predicted = normalize_plate(readings[0].text) if readings else ""
        candidates = list(dict.fromkeys(normalize_plate(item.text) for item in readings if item.text))
        results.append({
            "sample_id": record["sample_id"],
            "file": Path(record["image"]).name,
            "state": record["state"],
            "expected": record["expected"],
            "predicted": predicted,
            "candidates": candidates,
            "exact": predicted == record["expected"],
            "confidence": readings[0].confidence if readings else None,
        })
        if index % 25 == 0:
            print(f"OpenALPR OCR {index}/{len(records)}", file=sys.stderr, flush=True)

    elapsed = time.perf_counter() - started
    report = {
        "schema_version": 1,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "frozen_manifest": str(manifest_path.resolve()),
        "frozen_manifest_sha256": hashlib.sha256(manifest_bytes).hexdigest(),
        "metrics": summarize(results),
        "runtime": {
            "python": sys.version,
            "platform": platform.platform(),
            "elapsed_seconds": elapsed,
            "images_per_second": len(results) / elapsed if elapsed else None,
        },
        "model": reader.provenance.model_dump(mode="json"),
        "rows": results,
        "limitations": [
            "This measures OCR on already-cropped US plates, separately from full-frame localization.",
            "The public dataset is independent of LotTrace fine-tuning data, but prior exposure during third-party base-model pretraining cannot be proven absent.",
            "This still-image benchmark does not measure tracking or multi-frame event consensus.",
        ],
    }
    args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"output": str(args.output), "metrics": report["metrics"], "runtime": report["runtime"]}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
