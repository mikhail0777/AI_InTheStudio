"""Measure confidence/coverage trade-offs for routing plate reads to review."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.evaluation_metrics import wilson_interval


def row_confidence(row: dict, detector_threshold: float = 0.0) -> float | None:
    if row.get("confidence") is not None:
        return float(row["confidence"])
    selected = [
        float(item["confidence"]) for item in row.get("predictions", [])
        if float(item["confidence"]) >= detector_threshold
    ]
    # Minimum character confidence is intentionally conservative: one weak
    # character can make the complete plate wrong.
    return min(selected) if selected else None


def calibrate(report: dict, thresholds: list[float], target_precision: float, minimum_accepts: int) -> dict:
    detector_threshold = float((report.get("selected_metrics") or {}).get("confidence_threshold", 0.0))
    source_rows = []
    for row in report.get("rows", []):
        confidence = row_confidence(row, detector_threshold)
        if confidence is not None:
            source_rows.append((row, confidence))
    table = []
    for threshold in thresholds:
        accepted = [(row, confidence) for row, confidence in source_rows if confidence >= threshold]
        correct = sum(row.get("observed") == row.get("expected") for row, _ in accepted)
        lower, upper = wilson_interval(correct, len(accepted))
        table.append({
            "threshold": threshold, "accepted": len(accepted), "correct": correct,
            "incorrect_auto_accepts": len(accepted) - correct,
            "coverage": len(accepted) / len(report.get("rows", [])) if report.get("rows") else 0.0,
            "exact_precision": correct / len(accepted) if accepted else 0.0,
            "exact_precision_wilson_95": [lower, upper],
        })
    eligible = [
        row for row in table
        if row["accepted"] >= minimum_accepts and row["exact_precision_wilson_95"][0] >= target_precision
    ]
    selected = max(eligible, key=lambda row: (row["coverage"], row["exact_precision"], row["threshold"])) if eligible else None
    return {
        "schema_version": 1, "generated_at": datetime.now(timezone.utc).isoformat(),
        "target_exact_precision": target_precision, "minimum_accepted_samples": minimum_accepts,
        "confidence_definition": "reported sequence confidence, or minimum selected YOLO character confidence",
        "rows_with_confidence": len(source_rows), "tradeoff": table, "selected_policy": selected,
        "release_gate_met": selected is not None,
        "limitations": [
            "This calibrates a review threshold on one labelled split; an untouched target-domain set is still required.",
            "A model score is not measured accuracy; only the labelled accepted subset supplies precision.",
            "No threshold is selected unless the 95% Wilson lower bound meets the requested exact-plate precision.",
        ],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--target-precision", type=float, default=.99)
    parser.add_argument("--minimum-accepts", type=int, default=20)
    parser.add_argument("--thresholds", default="0.5,0.6,0.7,0.8,0.85,0.9,0.925,0.95,0.975,0.99")
    args = parser.parse_args()
    report = json.loads(args.input.read_text(encoding="utf-8"))
    result = calibrate(report, [float(item) for item in args.thresholds.split(",")],
                       args.target_precision, args.minimum_accepts)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"release_gate_met": result["release_gate_met"],
                      "selected_policy": result["selected_policy"],
                      "tradeoff": result["tradeoff"]}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
