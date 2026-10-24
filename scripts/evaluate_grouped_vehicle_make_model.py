"""Evaluate make/model after combining probabilities across year-range classes."""
from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
import math
from pathlib import Path
import re

import torch
from torch.utils.data import DataLoader

try:
    from scripts.train_vmmr_vehicle_classifier import ZipVehicleDataset, make_transforms
except ModuleNotFoundError:
    from train_vmmr_vehicle_classifier import ZipVehicleDataset, make_transforms


def normalized_key(label: dict) -> tuple[str, str]:
    clean = lambda value: re.sub(r"[^a-z0-9]+", "", str(value).casefold())
    return clean(label.get("make")), clean(label.get("model"))


def build_groups(classes: list[dict]) -> tuple[list[dict], torch.Tensor]:
    key_to_group: dict[tuple[str, str], int] = {}
    groups: list[dict] = []
    class_to_group = []
    for class_id, label in enumerate(classes):
        key = normalized_key(label)
        if not all(key):
            raise ValueError(f"Class {class_id} has an empty make or model")
        if key not in key_to_group:
            key_to_group[key] = len(groups)
            groups.append({
                "group_id": len(groups), "make": label["make"], "model": label["model"],
                "source_class_ids": [],
            })
        group_id = key_to_group[key]
        groups[group_id]["source_class_ids"].append(class_id)
        class_to_group.append(group_id)
    return groups, torch.tensor(class_to_group, dtype=torch.long)


def grouped_probabilities(logits: torch.Tensor, class_to_group: torch.Tensor, group_count: int) -> torch.Tensor:
    probabilities = torch.softmax(logits, dim=1)
    grouped = torch.zeros((len(logits), group_count), dtype=probabilities.dtype, device=probabilities.device)
    grouped.scatter_add_(1, class_to_group.to(probabilities.device).expand(len(logits), -1), probabilities)
    return grouped


def wilson(correct: int, total: int, z: float = 1.959963984540054) -> list[float]:
    if not total:
        return [0.0, 0.0]
    value = correct / total
    denominator = 1 + z * z / total
    centre = (value + z * z / (2 * total)) / denominator
    margin = z * math.sqrt(value * (1 - value) / total + z * z / (4 * total * total)) / denominator
    return [max(0.0, centre - margin), min(1.0, centre + margin)]


def metrics(probabilities: torch.Tensor, targets: torch.Tensor, groups: list[dict]) -> dict:
    top = probabilities.topk(min(5, len(groups)), dim=1).indices.cpu()
    targets = targets.cpu()
    exact1 = int((top[:, 0] == targets).sum())
    exact5 = int((top == targets[:, None]).any(dim=1).sum())
    make1 = sum(groups[predicted[0]]["make"].casefold() == groups[truth]["make"].casefold()
                for truth, predicted in zip(targets.tolist(), top.tolist()))
    support = Counter(targets.tolist()); predicted_counts = Counter(top[:, 0].tolist())
    true_positive = Counter(
        truth for truth, predicted in zip(targets.tolist(), top[:, 0].tolist()) if truth == predicted
    )
    f1 = []
    for group_id in support:
        precision = true_positive[group_id] / predicted_counts[group_id] if predicted_counts[group_id] else 0.0
        recall = true_positive[group_id] / support[group_id]
        f1.append(2 * precision * recall / (precision + recall) if precision + recall else 0.0)
    return {
        "samples": len(targets),
        "make_model_top1": exact1 / len(targets),
        "make_model_top1_count": exact1,
        "make_model_top1_wilson_95": wilson(exact1, len(targets)),
        "make_model_top5": exact5 / len(targets),
        "make_top1": make1 / len(targets),
        "macro_f1_make_model": sum(f1) / len(f1),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("manifest", type=Path)
    parser.add_argument("model", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--split", choices=("development", "test"), default="development")
    parser.add_argument("--batch-size", type=int, default=64)
    parser.add_argument("--cpu-threads", type=int, default=4)
    args = parser.parse_args()
    manifest_bytes = args.manifest.read_bytes()
    manifest = json.loads(manifest_bytes)
    samples = [item for item in manifest["samples"] if item["split"] == args.split]
    if not samples:
        raise SystemExit(f"No {args.split} samples")
    groups, class_to_group = build_groups(manifest["classes"])
    torch.set_num_threads(max(1, args.cpu_threads))
    exported = torch.export.load(str(args.model)); model = exported.module()
    batch_size = args.batch_size if exported.range_constraints else 1
    loader = DataLoader(
        ZipVehicleDataset(Path(manifest["archive"]["path"]), samples, make_transforms()["development"]),
        batch_size=batch_size, shuffle=False, num_workers=0,
    )
    values, targets = [], []
    with torch.inference_mode():
        for images, class_ids in loader:
            values.append(grouped_probabilities(model(images), class_to_group, len(groups)))
            targets.append(class_to_group.index_select(0, class_ids))
    probabilities, target_groups = torch.cat(values), torch.cat(targets)
    report = {
        "schema_version": 1,
        "scope": "grouped_make_model_development" if args.split == "development" else "grouped_make_model_frozen_regression_test",
        "split": args.split,
        "manifest_sha256": hashlib.sha256(manifest_bytes).hexdigest(),
        "model_sha256": hashlib.sha256(args.model.read_bytes()).hexdigest(),
        "source_classes": len(manifest["classes"]), "make_model_groups": len(groups),
        "aggregation": "sum_softmax_probability_across_year_range_classes_with_same_normalized_make_model",
        "metrics": metrics(probabilities, target_groups, groups),
        "source_metrics": {},
        "limitations": [manifest["dataset"]["limitation"], "This is a closed-set make/model benchmark."],
    }
    source_names = [item.get("source_dataset", manifest["dataset"]["name"]) for item in samples]
    for source in sorted(set(source_names)):
        indices = torch.tensor([index for index, value in enumerate(source_names) if value == source])
        report["source_metrics"][source] = metrics(
            probabilities.index_select(0, indices), target_groups.index_select(0, indices), groups,
        )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
