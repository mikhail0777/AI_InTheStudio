"""Score held-out dealership-video plate events without inventing missing labels.

The manifest must contain fully transcribed final-test events and documented
commercial usage rights. Predictions are produced separately so this evaluator
cannot accidentally tune the recognition pipeline while scoring the final set.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import hashlib
import json
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
sys.path.insert(0, str(ROOT / "scripts"))

from app.services.license_plate_reader import normalize_plate
from evaluation_metrics import levenshtein, wilson_interval


REQUIRED_PROVENANCE = ("name", "version", "licence", "source", "sha256", "permitted_usage")
REQUIRED_SEPARATION_KEYS = {"site_id", "camera_id", "vehicle_id", "recording_date"}


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _candidate_texts(prediction: dict) -> list[str]:
    output = []
    for item in prediction.get("candidates") or []:
        text = normalize_plate(str(item.get("text", "") if isinstance(item, dict) else item))
        if text and text not in output:
            output.append(text)
    return output


def _confusions(expected: str, observed: str) -> Counter[str]:
    """Return substitutions from one deterministic minimum-edit alignment."""
    rows, columns = len(expected) + 1, len(observed) + 1
    costs = [[0] * columns for _ in range(rows)]
    for row in range(rows):
        costs[row][0] = row
    for column in range(columns):
        costs[0][column] = column
    for row in range(1, rows):
        for column in range(1, columns):
            costs[row][column] = min(
                costs[row - 1][column] + 1,
                costs[row][column - 1] + 1,
                costs[row - 1][column - 1] + (expected[row - 1] != observed[column - 1]),
            )
    result: Counter[str] = Counter()
    row, column = len(expected), len(observed)
    while row or column:
        if row and column and costs[row][column] == costs[row - 1][column - 1] + (expected[row - 1] != observed[column - 1]):
            if expected[row - 1] != observed[column - 1]:
                result[f"{expected[row - 1]}->{observed[column - 1]}"] += 1
            row, column = row - 1, column - 1
        elif row and costs[row][column] == costs[row - 1][column] + 1:
            result[f"{expected[row - 1]}-><missing>"] += 1
            row -= 1
        else:
            result[f"<extra>->{observed[column - 1]}"] += 1
            column -= 1
    return result


def validate_manifest(manifest: dict) -> None:
    provenance = manifest.get("dataset") or {}
    missing = [field for field in REQUIRED_PROVENANCE
               if not str(provenance.get(field, "")).strip()
               or str(provenance.get(field, "")).startswith("REPLACE_WITH")]
    if missing:
        raise ValueError("Dataset provenance is missing: " + ", ".join(missing))
    events = manifest.get("events")
    if not isinstance(events, list) or not events:
        raise ValueError("Manifest must contain at least one event.")
    ids = [item.get("event_id") for item in events]
    if any(not value for value in ids) or len(ids) != len(set(ids)):
        raise ValueError("Every event_id must be present and unique.")
    if any(item.get("split") != "final_test" for item in events):
        raise ValueError("This release-gate evaluator accepts final_test events only.")
    separation = set((manifest.get("split_policy") or {}).get("separated_by") or [])
    if not REQUIRED_SEPARATION_KEYS.issubset(separation):
        raise ValueError(
            "Split policy must declare separation by site_id, camera_id, vehicle_id, and recording_date."
        )
    for item in events:
        if item.get("eligible", True) and item.get("plate") is not None:
            plate = normalize_plate(str(item["plate"]))
            if not 3 <= len(plate) <= 10:
                raise ValueError(f"Event {item['event_id']} lacks a valid full plate transcription.")
        if float(item.get("duration_seconds", 0)) < 0:
            raise ValueError(f"Event {item['event_id']} has negative duration.")
        required_event_fields = {"site_id", "camera_id", "recording_date"}
        if item.get("plate") is not None:
            required_event_fields.add("vehicle_id")
        absent = sorted(field for field in required_event_fields if not item.get(field))
        if absent:
            raise ValueError(f"Event {item['event_id']} is missing leakage-control fields: {', '.join(absent)}")


def evaluate(manifest: dict, predictions: list[dict], *, top_k: int = 5) -> dict:
    validate_manifest(manifest)
    if top_k < 1:
        raise ValueError("top_k must be at least 1.")
    by_id = {item["event_id"]: item for item in predictions}
    if len(by_id) != len(predictions):
        raise ValueError("Prediction event_id values must be unique.")
    known_ids = {item["event_id"] for item in manifest["events"]}
    extras = sorted(set(by_id) - known_ids)
    if extras:
        raise ValueError(f"Predictions contain unknown events: {', '.join(extras[:5])}")

    positives = [item for item in manifest["events"] if item.get("eligible", True) and item.get("plate") is not None]
    negatives = [item for item in manifest["events"] if item.get("plate") is None]
    exact = top_k_exact = read = false_exact = edit_errors = characters = 0
    confusion_counts: Counter[str] = Counter()
    condition_counts: dict[str, dict[str, int]] = defaultdict(lambda: {"events": 0, "read": 0, "exact": 0})
    for event in positives:
        expected = normalize_plate(str(event["plate"]))
        candidates = _candidate_texts(by_id.get(event["event_id"], {}))
        observed = candidates[0] if candidates else ""
        was_read = bool(candidates)
        was_exact = observed == expected
        read += int(was_read)
        exact += int(was_exact)
        top_k_exact += int(expected in candidates[:top_k])
        false_exact += int(was_read and not was_exact)
        distance = levenshtein(expected, observed)
        edit_errors += distance
        characters += len(expected)
        confusion_counts.update(_confusions(expected, observed))
        for condition in event.get("conditions") or ["unspecified"]:
            values = condition_counts[str(condition)]
            values["events"] += 1
            values["read"] += int(was_read)
            values["exact"] += int(was_exact)

    negative_false_sightings = sum(bool(_candidate_texts(by_id.get(item["event_id"], {}))) for item in negatives)
    negative_hours = sum(float(item.get("duration_seconds", 0)) for item in negatives) / 3600
    denominator = len(positives)
    event_recall = read / denominator if denominator else 0.0
    exact_accuracy = exact / denominator if denominator else 0.0
    top_k_accuracy = top_k_exact / denominator if denominator else 0.0
    cer = edit_errors / characters if characters else 0.0
    character_accuracy = max(0.0, 1.0 - cer)
    return {
        "decision": "pass" if denominator and event_recall >= .99 and exact_accuracy >= .99 and character_accuracy >= .99 else "fail",
        "denominators": {
            "eligible_fully_transcribed_events": denominator,
            "ground_truth_characters": characters,
            "negative_clips": len(negatives),
            "negative_video_hours": round(negative_hours, 6),
        },
        "metrics": {
            "event_read_recall": event_recall,
            "event_read_recall_wilson_95": wilson_interval(read, denominator),
            "event_exact_full_plate_accuracy": exact_accuracy,
            "event_exact_full_plate_accuracy_wilson_95": wilson_interval(exact, denominator),
            f"top_{top_k}_exact_full_plate_accuracy": top_k_accuracy,
            "character_error_rate": cer,
            "character_accuracy": character_accuracy,
            "false_exact_plate_assignments": false_exact,
            "false_sightings_on_negative_video": negative_false_sightings,
            "false_sightings_per_negative_video_hour": (
                negative_false_sightings / negative_hours if negative_hours else None
            ),
        },
        "conditions": {
            name: {
                **values,
                "event_read_recall": values["read"] / values["events"],
                "exact_full_plate_accuracy": values["exact"] / values["events"],
            } for name, values in sorted(condition_counts.items())
        },
        "ocr_confusions": dict(confusion_counts.most_common()),
        "release_targets": {
            "event_read_recall": .99,
            "character_accuracy": .99,
            "event_exact_full_plate_accuracy": .99,
        },
        "limitations": [
            "This report scores only the supplied held-out labels and predictions.",
            "Plate-to-vehicle association and eligible crossing recall require separate labelled outputs.",
        ],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", required=True)
    parser.add_argument("--predictions", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--top-k", type=int, default=5)
    args = parser.parse_args()
    manifest_path, predictions_path = Path(args.manifest), Path(args.predictions)
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    prediction_payload = json.loads(predictions_path.read_text(encoding="utf-8"))
    if not isinstance(prediction_payload, dict) or not isinstance(prediction_payload.get("predictions"), list):
        raise SystemExit("Predictions must be an object containing model_manifest and predictions.")
    model_manifest = prediction_payload.get("model_manifest")
    if not isinstance(model_manifest, dict) or not model_manifest.get("models") or not model_manifest.get("thresholds"):
        raise SystemExit("Prediction model_manifest must record models/hashes and thresholds.")
    predictions = prediction_payload["predictions"]
    report = evaluate(manifest, predictions, top_k=args.top_k)
    report["inputs"] = {
        "manifest": str(manifest_path.resolve()), "manifest_sha256": _sha256(manifest_path),
        "predictions": str(predictions_path.resolve()), "predictions_sha256": _sha256(predictions_path),
        "dataset": manifest["dataset"],
        "model_manifest": model_manifest,
    }
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))
    return 0 if report["decision"] == "pass" else 2


if __name__ == "__main__":
    raise SystemExit(main())
