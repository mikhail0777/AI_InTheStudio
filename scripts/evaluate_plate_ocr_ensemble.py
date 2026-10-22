"""Evaluate a transparent YOLO/PARSeq plate-sequence ranking experiment."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.evaluation_metrics import levenshtein, wilson_interval


def canonical_file(name: str) -> str:
    for prefix in ("primary__", "supplemental__"):
        if name.startswith(prefix):
            return name[len(prefix):]
    return name


def evaluate(yolo_rows: list[dict], parseq_rows: list[dict], plate_length: int, threshold: float) -> dict:
    parseq_by_file = {canonical_file(row["file"]): row for row in parseq_rows}
    rows = []; exact = edits = characters = overrides = 0
    for yolo in yolo_rows:
        parseq = parseq_by_file.get(canonical_file(yolo["file"]))
        observed = yolo["observed"]
        source = "yolo"
        if (parseq and len(observed) != plate_length and len(parseq["observed"]) == plate_length
                and float(parseq["confidence"]) >= threshold):
            observed = parseq["observed"]
            source = "parseq_length_ranked_alternative"
            overrides += 1
        expected = yolo["expected"]
        exact += int(observed == expected)
        edits += levenshtein(observed, expected); characters += len(expected)
        rows.append({
            "file": yolo["file"], "expected": expected, "observed": observed, "source": source,
            "yolo_observed": yolo["observed"],
            "parseq_observed": parseq["observed"] if parseq else None,
            "parseq_confidence": parseq["confidence"] if parseq else None,
        })
    total = len(rows)
    return {
        "threshold": threshold, "plate_length": plate_length, "plates": total,
        "exact_matches": exact, "exact_plate_accuracy": exact / total if total else 0.0,
        "exact_plate_accuracy_wilson_95": wilson_interval(exact, total),
        "character_accuracy": 1 - edits / characters if characters else 0.0,
        "overrides": overrides, "rows": rows,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--yolo-report", required=True, type=Path)
    parser.add_argument("--parseq-report", required=True, type=Path)
    parser.add_argument("--split", choices=["valid", "test"], required=True)
    parser.add_argument("--plate-length", required=True, type=int)
    parser.add_argument("--threshold", type=float)
    parser.add_argument("--thresholds", default="0.8,0.85,0.9,0.925,0.95,0.975,0.99,0.995")
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    if args.split == "test" and args.threshold is None:
        raise SystemExit("Test evaluation requires a validation-selected --threshold")
    yolo = json.loads(args.yolo_report.read_text(encoding="utf-8"))["rows"]
    parseq = json.loads(args.parseq_report.read_text(encoding="utf-8"))["rows"]
    thresholds = [args.threshold] if args.threshold is not None else [float(x) for x in args.thresholds.split(",")]
    results = [evaluate(yolo, parseq, args.plate_length, threshold) for threshold in thresholds]
    selected = max(results, key=lambda row: (
        row["exact_plate_accuracy"], row["character_accuracy"], -row["overrides"], row["threshold"],
    ))
    report = {
        "schema_version": 1, "generated_at": datetime.now(timezone.utc).isoformat(), "split": args.split,
        "policy": {
            "description": "Prefer PARSeq only when YOLO has the wrong configured length, PARSeq has that length, and its confidence passes the validation-selected threshold.",
            "plate_length": args.plate_length, "selected_parseq_threshold": selected["threshold"],
            "format_constraint_is_region_specific": True,
        },
        "metrics_by_threshold": [{k: v for k, v in row.items() if k != "rows"} for row in results],
        "selected_metrics": {k: v for k, v in selected.items() if k != "rows"},
        "rows": selected["rows"],
        "limitations": [
            "This is an evaluation experiment and is not wired into production identity confirmation.",
            "The seven-character constraint is valid only when explicitly configured for the camera jurisdiction.",
            "The 37-image regression split has been inspected repeatedly and is not a pristine final test set.",
            "Single-crop results do not measure dealership-video event performance.",
        ],
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report["selected_metrics"], indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
