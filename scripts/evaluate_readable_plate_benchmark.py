"""Evaluate OCR only after a blinded readable-plate benchmark is frozen."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import platform
import sys
import time

import cv2


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "backend"))

from app.services.license_plate_reader import LicensePlateReader, normalize_plate
from scripts.evaluation_metrics import levenshtein, wilson_interval
from scripts.prepare_readable_plate_benchmark import sha256_file


def summarize(rows: list[dict]) -> dict:
    eligible = [row for row in rows if row["expected"]]
    exact = sum(row["predicted"] == row["expected"] for row in eligible)
    characters = sum(len(row["expected"]) for row in eligible)
    edits = sum(levenshtein(row["predicted"], row["expected"]) for row in eligible)
    return {
        "plates": len(eligible),
        "exact_matches": exact,
        "exact_plate_accuracy": exact / len(eligible) if eligible else None,
        "exact_plate_accuracy_wilson_95": wilson_interval(exact, len(eligible)) if eligible else None,
        "ground_truth_characters": characters,
        "character_edits": edits,
        "character_error_rate": edits / characters if characters else None,
        "character_accuracy": 1 - edits / characters if characters else None,
    }


def verify_frozen(benchmark: Path) -> dict:
    manifest_path = benchmark / "frozen_manifest.json"
    checksum_line = (benchmark / "FROZEN.sha256").read_text(encoding="ascii").split()[0]
    actual = hashlib.sha256(manifest_path.read_bytes()).hexdigest()
    if actual != checksum_line:
        raise ValueError("Frozen manifest checksum mismatch")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("status") != "frozen_before_ocr_evaluation":
        raise ValueError("Benchmark is not marked frozen-before-evaluation")
    for record in manifest["records"]:
        path = benchmark / record["image"]
        if not path.is_file() or sha256_file(path) != record["image_sha256"]:
            raise ValueError(f"Missing or changed benchmark image: {record['sample_id']}")
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--benchmark", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    manifest = verify_frozen(args.benchmark)
    reader = LicensePlateReader()
    rows = []
    started = time.perf_counter()
    for index, record in enumerate(manifest["records"], 1):
        image = cv2.imread(str(args.benchmark / record["image"]))
        readings = reader.read_crop(image, source_variant="ground_truth_crop")
        predicted = normalize_plate(readings[0].text) if readings else ""
        rows.append({
            "sample_id": record["sample_id"],
            "readability": record["readability"],
            "expected": record["transcription"],
            "predicted": predicted,
            "exact": bool(record["transcription"]) and predicted == record["transcription"],
            "confidence": readings[0].confidence if readings else None,
        })
        if index % 25 == 0:
            print(f"OCR {index}/{len(manifest['records'])}", file=sys.stderr, flush=True)
    elapsed = time.perf_counter() - started
    readable = [row for row in rows if row["readability"] == "readable"]
    challenging = [row for row in rows if row["readability"] == "challenging"]
    unreadable = [row for row in rows if row["readability"] == "unreadable"]
    out_of_scope = [row for row in rows if row["readability"] == "out_of_scope"]
    report = {
        "schema_version": 1,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "benchmark": str(args.benchmark.resolve()),
        "primary_metric": {"name": "normal_readable_exact_plate_accuracy", **summarize(readable)},
        "challenging_metric": summarize(challenging),
        "readable_plus_challenging": summarize(readable + challenging),
        "unreadable_behavior": {
            "plates": len(unreadable),
            "no_read": sum(not row["predicted"] for row in unreadable),
            "no_read_rate": sum(not row["predicted"] for row in unreadable) / len(unreadable) if unreadable else None,
            "note": "No-read is only a provisional abstention measure; confidence-policy review is separate.",
        },
        "out_of_scope": {
            "plates": len(out_of_scope),
            "note": "Excluded before OCR scoring because the alphabet or layout is outside the declared benchmark scope.",
        },
        "runtime": {"python": sys.version, "platform": platform.platform(), "elapsed_seconds": elapsed},
        "model": reader.provenance.model_dump(mode="json"),
        "rows": rows,
        "limitations": [
            "OCR is measured on ground-truth crops, separately from plate localization.",
            "This still-image benchmark does not measure tracking or multi-frame event consensus.",
        ],
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({
        "primary_metric": report["primary_metric"],
        "challenging_metric": report["challenging_metric"],
        "unreadable_behavior": report["unreadable_behavior"],
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
