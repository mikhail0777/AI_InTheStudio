"""Calibrate a make/model review gate on development and score frozen test."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import torch
from torch.utils.data import DataLoader

try:
    from scripts.evaluate_grouped_vehicle_make_model import build_groups, grouped_probabilities, wilson
    from scripts.train_vmmr_vehicle_classifier import ZipVehicleDataset, make_transforms
except ModuleNotFoundError:
    from evaluate_grouped_vehicle_make_model import build_groups, grouped_probabilities, wilson
    from train_vmmr_vehicle_classifier import ZipVehicleDataset, make_transforms


def choose_threshold(confidence: list[float], correct: list[bool], minimum_precision: float) -> dict:
    candidates = sorted(set(confidence))
    valid = []
    for threshold in candidates:
        accepted = [index for index, value in enumerate(confidence) if value >= threshold]
        exact = sum(correct[index] for index in accepted)
        precision = exact / len(accepted) if accepted else 0.0
        if precision >= minimum_precision:
            valid.append({
                "threshold": threshold, "accepted": len(accepted), "exact": exact,
                "precision": precision, "coverage": len(accepted) / len(confidence),
            })
    if not valid:
        raise ValueError("No non-empty threshold reaches the requested development precision")
    return max(valid, key=lambda row: (row["coverage"], row["precision"], row["threshold"]))


def score(confidence: list[float], correct: list[bool], threshold: float) -> dict:
    accepted = [index for index, value in enumerate(confidence) if value >= threshold]
    exact = sum(correct[index] for index in accepted)
    total = len(confidence)
    return {
        "samples": total,
        "overall_make_model_accuracy": sum(correct) / total,
        "overall_exact_count": sum(correct),
        "accepted": len(accepted),
        "reviewed": total - len(accepted),
        "coverage": len(accepted) / total,
        "review_rate": (total - len(accepted)) / total,
        "accepted_make_model_accuracy": exact / len(accepted) if accepted else 0.0,
        "accepted_exact_count": exact,
        "accepted_accuracy_wilson_95": wilson(exact, len(accepted)),
        "false_accepted_assignments": len(accepted) - exact,
    }


def infer(model, loader, class_to_group: torch.Tensor, group_count: int):
    confidence, correct = [], []
    with torch.inference_mode():
        for images, class_ids in loader:
            grouped = grouped_probabilities(model(images), class_to_group, group_count)
            values, predictions = grouped.max(dim=1)
            targets = class_to_group.index_select(0, class_ids)
            confidence.extend(values.tolist())
            correct.extend((predictions.cpu() == targets).tolist())
    return confidence, correct


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("manifest", type=Path)
    parser.add_argument("model", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--minimum-development-precision", type=float, default=.95)
    parser.add_argument("--batch-size", type=int, default=64)
    parser.add_argument("--cpu-threads", type=int, default=4)
    args = parser.parse_args()
    raw = args.manifest.read_bytes(); manifest = json.loads(raw)
    groups, class_to_group = build_groups(manifest["classes"])
    torch.set_num_threads(max(1, args.cpu_threads))
    exported = torch.export.load(str(args.model)); model = exported.module()
    batch_size = args.batch_size if exported.range_constraints else 1
    results = {}
    for split in ("development", "test"):
        samples = [item for item in manifest["samples"] if item["split"] == split]
        loader = DataLoader(
            ZipVehicleDataset(Path(manifest["archive"]["path"]), samples, make_transforms()["development"]),
            batch_size=batch_size, shuffle=False, num_workers=0,
        )
        results[split] = infer(model, loader, class_to_group, len(groups))
    selected = choose_threshold(*results["development"], args.minimum_development_precision)
    report = {
        "schema_version": 1,
        "scope": "development_calibrated_make_model_review_gate_with_frozen_regression_test",
        "manifest_sha256": hashlib.sha256(raw).hexdigest(),
        "model_sha256": hashlib.sha256(args.model.read_bytes()).hexdigest(),
        "make_model_groups": len(groups),
        "calibration": {**selected, "minimum_development_precision": args.minimum_development_precision},
        "development": score(*results["development"], selected["threshold"]),
        "test": score(*results["test"], selected["threshold"]),
        "limitations": [
            manifest["dataset"]["limitation"],
            "Accuracy among accepted predictions is not accuracy across every vehicle.",
            "Rejected predictions require review and reduce automatic coverage.",
            "This is a closed-set still-image regression benchmark, not dealership video.",
        ],
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
