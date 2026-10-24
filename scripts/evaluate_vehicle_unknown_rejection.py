"""Calibrate unknown-vehicle rejection on development, then score frozen test."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from PIL import Image
import torch
from torch.utils.data import DataLoader, Dataset

try:
    from scripts.train_vmmr_vehicle_classifier import make_transforms
except ModuleNotFoundError:
    from train_vmmr_vehicle_classifier import make_transforms


class PathDataset(Dataset):
    def __init__(self, samples: list[dict], transform):
        self.samples, self.transform = samples, transform

    def __len__(self):
        return len(self.samples)

    def __getitem__(self, index):
        item = self.samples[index]
        with Image.open(item["path"]) as image:
            value = self.transform(image.convert("RGB"))
        target = -1 if item.get("class_id") is None else int(item["class_id"])
        return value, target


def choose_threshold(known: list[float], unknown: list[float], minimum_known_acceptance: float) -> dict:
    if not known or not unknown:
        raise ValueError("Known and unknown development probabilities are required")
    candidates = sorted(set([0.0, 1.0, *known, *unknown]))
    rows = []
    for threshold in candidates:
        known_acceptance = sum(value >= threshold for value in known) / len(known)
        unknown_rejection = sum(value < threshold for value in unknown) / len(unknown)
        rows.append({
            "threshold": threshold,
            "known_acceptance": known_acceptance,
            "unknown_rejection": unknown_rejection,
            "balanced_accuracy": (known_acceptance + unknown_rejection) / 2,
        })
    eligible = [row for row in rows if row["known_acceptance"] >= minimum_known_acceptance]
    pool = eligible or rows
    # Prefer rejection quality, then the stricter threshold, when scores tie.
    return max(pool, key=lambda row: (row["balanced_accuracy"], row["unknown_rejection"], row["threshold"]))


def infer(model, samples: list[dict], batch_size: int) -> tuple[list[float], list[int], list[int]]:
    loader = DataLoader(PathDataset(samples, make_transforms()["development"]), batch_size=batch_size, shuffle=False)
    probabilities, predictions, targets = [], [], []
    with torch.inference_mode():
        for images, target in loader:
            values = torch.softmax(model(images), dim=1)
            confidence, prediction = values.max(dim=1)
            probabilities.extend(confidence.tolist())
            predictions.extend(prediction.tolist())
            targets.extend(target.tolist())
    return probabilities, predictions, targets


def score(known_values, known_predictions, known_targets, unknown_values, threshold) -> dict:
    accepted = [value >= threshold for value in known_values]
    known_accepted = sum(accepted)
    exact_accepted = sum(
        accept and predicted == target
        for accept, predicted, target in zip(accepted, known_predictions, known_targets)
    )
    unknown_rejected = sum(value < threshold for value in unknown_values)
    total = len(known_values) + len(unknown_values)
    reviewed = (len(known_values) - known_accepted) + unknown_rejected
    return {
        "known_samples": len(known_values),
        "known_accepted": known_accepted,
        "known_acceptance": known_accepted / len(known_values) if known_values else 0.0,
        "known_exact_and_accepted": exact_accepted,
        "known_exact_among_accepted": exact_accepted / known_accepted if known_accepted else 0.0,
        "unknown_samples": len(unknown_values),
        "unknown_rejected": unknown_rejected,
        "unknown_rejection": unknown_rejected / len(unknown_values) if unknown_values else 0.0,
        "false_exact_assignments_on_unknown": len(unknown_values) - unknown_rejected,
        "review_rate": reviewed / total if total else 0.0,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("manifest", type=Path)
    parser.add_argument("model", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--batch-size", type=int, default=64)
    parser.add_argument("--cpu-threads", type=int, default=4)
    parser.add_argument("--minimum-known-acceptance", type=float, default=.90)
    args = parser.parse_args()
    manifest_bytes = args.manifest.read_bytes()
    manifest = json.loads(manifest_bytes)
    required = ("development", "unknown_development", "test", "unknown_test")
    splits = {name: [item for item in manifest["samples"] if item["split"] == name] for name in required}
    if not all(splits.values()):
        raise SystemExit("Known/unknown development and test splits must all be non-empty")
    torch.set_num_threads(max(1, args.cpu_threads))
    exported = torch.export.load(str(args.model))
    model = exported.module()
    batch_size = args.batch_size if exported.range_constraints else 1
    dev_known = infer(model, splits["development"], batch_size)
    dev_unknown = infer(model, splits["unknown_development"], batch_size)
    selection = choose_threshold(dev_known[0], dev_unknown[0], args.minimum_known_acceptance)
    test_known = infer(model, splits["test"], batch_size)
    test_unknown = infer(model, splits["unknown_test"], batch_size)
    report = {
        "schema_version": 1,
        "scope": "development_calibrated_unknown_rejection_with_frozen_test",
        "manifest_sha256": hashlib.sha256(manifest_bytes).hexdigest(),
        "model_sha256": hashlib.sha256(args.model.read_bytes()).hexdigest(),
        "calibration": {**selection, "minimum_known_acceptance_requested": args.minimum_known_acceptance},
        "development": score(*dev_known, dev_unknown[0], selection["threshold"]),
        "test": score(*test_known, test_unknown[0], selection["threshold"]),
        "limitations": [
            "Unsupported classes are a small curated proxy, not the open world.",
            "Still photographs do not certify dealership-video unknown rejection.",
            "Maximum softmax probability is a baseline uncertainty signal, not calibrated truth.",
        ],
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
