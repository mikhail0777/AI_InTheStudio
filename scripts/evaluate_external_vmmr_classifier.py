"""Evaluate a full-VMMR EfficientNet checkpoint on a LotTrace benchmark split."""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
from pathlib import Path

from PIL import Image
import timm
import torch
from torch.utils.data import DataLoader, Dataset
from torchvision import transforms


def normalize(value: str) -> str:
    return " ".join(value.casefold().replace("_", " ").split())


def load_external_labels(path: Path) -> list[dict]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))
    maximum_id = max(int(row["global_class_id"]) for row in rows)
    labels: list[dict | None] = [None] * (maximum_id + 1)
    for row in rows:
        class_id = int(row["global_class_id"])
        name = row["class_name"].strip()
        try:
            year = int(name.rsplit(" ", 1)[1])
        except (IndexError, ValueError) as exc:
            raise ValueError(f"Class has no parseable year: {name!r}") from exc
        # The published CSV repeats class 106 once; prefer the later, correctly
        # separated "Alfa Romeo" make and "4C" model fields.
        labels[class_id] = {
            "class_id": class_id,
            "make": normalize(row["make"]),
            "model": normalize(row["model"]),
            "year": year,
            "source_label": name,
        }
    if any(label is None for label in labels):
        raise ValueError("External class mapping IDs must be contiguous.")
    return labels  # type: ignore[return-value]


def benchmark_class_for_prediction(label: dict, classes: list[dict]) -> int | None:
    for benchmark in classes:
        if (
            normalize(benchmark["make"]) == label["make"]
            and normalize(benchmark["model"]) == label["model"]
            and benchmark["year_start"] <= label["year"] <= benchmark["year_end"]
        ):
            return int(benchmark["class_id"])
    return None


class ExtractedDataset(Dataset):
    def __init__(self, root: Path, samples: list[dict], transform):
        self.root, self.samples, self.transform = root, samples, transform

    def __len__(self):
        return len(self.samples)

    def __getitem__(self, index):
        sample = self.samples[index]
        with Image.open(self.root / sample["member"]) as image:
            tensor = self.transform(image.convert("RGB"))
        return tensor, int(sample["class_id"]), int(sample["source_year"])


def wilson(correct: int, total: int, z: float = 1.959963984540054) -> list[float]:
    if not total:
        return [0.0, 0.0]
    value = correct / total
    denominator = 1 + z * z / total
    centre = (value + z * z / (2 * total)) / denominator
    margin = z * math.sqrt(value * (1 - value) / total + z * z / (4 * total * total)) / denominator
    return [max(0.0, centre - margin), min(1.0, centre + margin)]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("manifest", type=Path)
    parser.add_argument("checkpoint", type=Path)
    parser.add_argument("class_mapping", type=Path)
    parser.add_argument("--extracted-root", type=Path, required=True)
    parser.add_argument("--split", choices=("development", "test"), default="development")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--batch-size", type=int, default=8)
    parser.add_argument("--cpu-threads", type=int, default=8)
    args = parser.parse_args()

    manifest_bytes = args.manifest.read_bytes()
    manifest = json.loads(manifest_bytes)
    if manifest.get("purpose") != "frozen_research_benchmark":
        raise SystemExit("A frozen research benchmark manifest is required.")
    samples = [sample for sample in manifest["samples"] if sample["split"] == args.split]
    labels = load_external_labels(args.class_mapping)
    checkpoint = torch.load(args.checkpoint, map_location="cpu", weights_only=True)
    if checkpoint.get("architecture") != "efficientnet_b4":
        raise SystemExit("Unsupported external checkpoint architecture.")
    if int(checkpoint.get("num_classes", 0)) != len(labels):
        raise SystemExit("Checkpoint and class mapping disagree.")

    torch.set_num_threads(max(1, args.cpu_threads))
    model = timm.create_model("efficientnet_b4", pretrained=False, num_classes=len(labels))
    model.load_state_dict(checkpoint["model_state"])
    model.eval()
    transform = transforms.Compose([
        transforms.Resize(400),
        transforms.CenterCrop(380),
        transforms.ToTensor(),
        transforms.Normalize([.485, .456, .406], [.229, .224, .225]),
    ])
    loader = DataLoader(
        ExtractedDataset(args.extracted_root, samples, transform),
        batch_size=args.batch_size,
        shuffle=False,
        num_workers=0,
    )

    exact_range_1 = exact_range_5 = exact_year_1 = make_model_1 = make_1 = 0
    with torch.inference_mode():
        for images, truth_ids, source_years in loader:
            top = model(images).topk(5, dim=1).indices.tolist()
            for truth_id, source_year, predicted_ids in zip(truth_ids.tolist(), source_years.tolist(), top):
                truth = manifest["classes"][truth_id]
                truth_make, truth_model = normalize(truth["make"]), normalize(truth["model"])
                predictions = [labels[index] for index in predicted_ids]
                mapped = [benchmark_class_for_prediction(label, manifest["classes"]) for label in predictions]
                exact_range_1 += mapped[0] == truth_id
                exact_range_5 += truth_id in mapped
                exact_year_1 += (
                    predictions[0]["make"] == truth_make
                    and predictions[0]["model"] == truth_model
                    and predictions[0]["year"] == source_year
                )
                make_model_1 += predictions[0]["make"] == truth_make and predictions[0]["model"] == truth_model
                make_1 += predictions[0]["make"] == truth_make

    total = len(samples)
    metrics = {
        "samples": total,
        "exact_make_model_year_range_top1": exact_range_1 / total,
        "exact_make_model_year_range_top1_count": exact_range_1,
        "exact_top1_wilson_95": wilson(exact_range_1, total),
        "exact_make_model_year_range_top5": exact_range_5 / total,
        "exact_make_model_source_year_top1": exact_year_1 / total,
        "make_model_top1": make_model_1 / total,
        "make_top1": make_1 / total,
    }
    report = {
        "schema_version": 1,
        "scope": f"external_vmmr_candidate_{args.split}_research_only",
        "source_repository": "https://huggingface.co/Jordo23/vehicle-classifier",
        "manifest_sha256": hashlib.sha256(manifest_bytes).hexdigest(),
        "model_sha256": hashlib.sha256(args.checkpoint.read_bytes()).hexdigest(),
        "mapping_sha256": hashlib.sha256(args.class_mapping.read_bytes()).hexdigest(),
        "architecture": checkpoint["architecture"],
        "external_classes": len(labels),
        "metrics": metrics,
        "limitations": [
            manifest["dataset"]["limitation"],
            "The checkpoint was trained on VMMRdb, so this is not cross-dataset evidence.",
            "Development results select candidates; only the frozen test can measure the selected candidate.",
        ],
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
