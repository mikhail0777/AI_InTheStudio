"""Evaluate a frozen VMMR research test split exactly once."""
from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
import math
from pathlib import Path

import torch
from torch.utils.data import DataLoader

try:
    from scripts.train_vmmr_vehicle_classifier import ZipVehicleDataset, make_transforms
except ModuleNotFoundError:
    from train_vmmr_vehicle_classifier import ZipVehicleDataset, make_transforms


def _wilson(correct: int, total: int, z: float = 1.959963984540054) -> list[float]:
    if not total:
        return [0.0, 0.0]
    value = correct / total
    denominator = 1 + z * z / total
    centre = (value + z * z / (2 * total)) / denominator
    margin = z * math.sqrt(value * (1 - value) / total + z * z / (4 * total * total)) / denominator
    return [max(0.0, centre - margin), min(1.0, centre + margin)]


def calculate_metrics(logits: torch.Tensor, targets: torch.Tensor, classes: list[dict]) -> dict:
    top = logits.topk(min(5, logits.shape[1]), dim=1).indices.cpu()
    targets = targets.cpu()
    total = len(targets)
    exact1 = int((top[:, 0] == targets).sum())
    exact5 = int((top == targets[:, None]).any(dim=1).sum())
    make1 = model1 = year1 = 0
    true_positive = Counter(); predicted = Counter(); support = Counter()
    confusions = Counter()
    for truth_id, predicted_ids in zip(targets.tolist(), top.tolist()):
        truth, prediction = classes[truth_id], classes[predicted_ids[0]]
        truth_key = (truth["make"], truth["model"])
        prediction_key = (prediction["make"], prediction["model"])
        make1 += prediction["make"] == truth["make"]
        model1 += prediction_key == truth_key
        year1 += (
            prediction["year_start"] == truth["year_start"]
            and prediction["year_end"] == truth["year_end"]
        )
        support[truth_id] += 1; predicted[predicted_ids[0]] += 1
        if truth_id == predicted_ids[0]:
            true_positive[truth_id] += 1
        else:
            confusions[(truth_id, predicted_ids[0])] += 1
    f1_values = []
    for class_id in sorted(support):
        precision = true_positive[class_id] / predicted[class_id] if predicted[class_id] else 0.0
        recall = true_positive[class_id] / support[class_id] if support[class_id] else 0.0
        f1_values.append(2 * precision * recall / (precision + recall) if precision + recall else 0.0)
    distinct_year_ranges = {
        (classes[class_id]["year_start"], classes[class_id]["year_end"])
        for class_id in targets.tolist()
    }
    return {
        "samples": total,
        "exact_make_model_year_range_top1": exact1 / total if total else 0.0,
        "exact_make_model_year_range_top1_count": exact1,
        "exact_top1_wilson_95": _wilson(exact1, total),
        "exact_make_model_year_range_top5": exact5 / total if total else 0.0,
        "make_top1": make1 / total if total else 0.0,
        "make_model_top1": model1 / total if total else 0.0,
        "year_range_top1": year1 / total if total else 0.0,
        "year_range_distinct_label_count": len(distinct_year_ranges),
        "year_range_discrimination_measured": len(distinct_year_ranges) > 1,
        "macro_f1_exact_class": sum(f1_values) / len(f1_values) if f1_values else 0.0,
        "largest_confusions": [{
            "truth": classes[truth], "predicted": classes[prediction], "count": count,
        } for (truth, prediction), count in confusions.most_common(30)],
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("manifest", type=Path)
    parser.add_argument("model", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--batch-size", type=int, default=64)
    parser.add_argument("--cpu-threads", type=int, default=4)
    parser.add_argument("--extracted-root", type=Path)
    parser.add_argument("--split", choices=("development", "test"), default="test")
    parser.add_argument("--quiet", action="store_true")
    args = parser.parse_args()
    manifest_bytes = args.manifest.read_bytes()
    manifest = json.loads(manifest_bytes)
    if manifest.get("purpose") != "frozen_research_benchmark":
        raise SystemExit("Evaluation requires a frozen research benchmark manifest.")
    samples = [item for item in manifest["samples"] if item["split"] == args.split]
    if not samples:
        raise SystemExit(f"The frozen manifest has no {args.split} samples.")
    torch.set_num_threads(max(1, args.cpu_threads))
    exported = torch.export.load(str(args.model))
    # ExportedProgram preserves the source model's evaluation graph. Calling
    # ``eval`` on the exported module is not supported by current PyTorch.
    model = exported.module()
    effective_batch_size = args.batch_size if exported.range_constraints else 1
    loader = DataLoader(
        ZipVehicleDataset(Path(manifest["archive"]["path"]), samples, make_transforms()["development"], args.extracted_root),
        batch_size=effective_batch_size, shuffle=False, num_workers=0,
    )
    logits_values, targets_values = [], []
    with torch.inference_mode():
        for images, targets in loader:
            logits_values.append(model(images))
            targets_values.append(targets)
    all_logits, all_targets = torch.cat(logits_values), torch.cat(targets_values)
    metrics = calculate_metrics(all_logits, all_targets, manifest["classes"])
    source_metrics = {}
    source_names = [item.get("source_dataset", manifest["dataset"]["name"]) for item in samples]
    for source_name in sorted(set(source_names)):
        indices = torch.tensor([index for index, name in enumerate(source_names) if name == source_name])
        source_metrics[source_name] = calculate_metrics(
            all_logits.index_select(0, indices),
            all_targets.index_select(0, indices),
            manifest["classes"],
        )
    predicted_ids = all_logits.argmax(dim=1).tolist()
    target_ids = all_targets.tolist()
    misclassified_samples = []
    for sample, truth_id, prediction_id in zip(samples, target_ids, predicted_ids):
        if truth_id != prediction_id:
            misclassified_samples.append({
                "sample_id": sample.get("sample_id", sample.get("member")),
                "source_dataset": sample.get("source_dataset", manifest["dataset"]["name"]),
                "truth": manifest["classes"][truth_id],
                "predicted": manifest["classes"][prediction_id],
            })
    report = {
        "schema_version": 1,
        "scope": (
            "frozen_vehicle_research_test_not_production_accuracy"
            if args.split == "test" else "vehicle_development_selection_not_test_accuracy"
        ),
        "split": args.split,
        "manifest_sha256": hashlib.sha256(manifest_bytes).hexdigest(),
        "model_sha256": hashlib.sha256(args.model.read_bytes()).hexdigest(),
        "dataset": manifest["dataset"], "classes": len(manifest["classes"]),
        "metrics": metrics,
        "source_metrics": source_metrics,
        "misclassified_samples": misclassified_samples,
        "limitations": [
            manifest["dataset"]["limitation"],
            "Closed-set results do not measure unknown or unsupported vehicle rejection.",
            "Web-sale photographs differ from fixed dealership entrance/exit video.",
        ],
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    if not args.quiet:
        print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
