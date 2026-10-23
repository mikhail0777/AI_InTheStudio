"""Train a local development VMMR classifier and export a PyTorch model.

This script never treats its deterministic VMMR development split as a final
deployment benchmark.  It supports CPU execution but a GPU is strongly
recommended for more than a small smoke experiment.
"""
from __future__ import annotations

import argparse
from io import BytesIO
import json
from pathlib import Path
import random
import time
from zipfile import ZipFile

from PIL import Image
import torch
from torch.utils.data import DataLoader, Dataset
from torchvision import models, transforms


class ZipVehicleDataset(Dataset):
    def __init__(self, archive: Path, samples: list[dict], transform, extracted_root: Path | None = None):
        self.archive_path = Path(archive)
        self.samples = samples
        self.transform = transform
        self.extracted_root = Path(extracted_root) if extracted_root else None
        self._archive = None

    def __len__(self):
        return len(self.samples)

    def _source(self):
        if self._archive is None:
            self._archive = ZipFile(self.archive_path)
        return self._archive

    def __getitem__(self, index):
        item = self.samples[index]
        if self.extracted_root:
            path = (self.extracted_root / item["member"]).resolve()
            if self.extracted_root.resolve() not in path.parents:
                raise ValueError("Manifest member escapes the extracted dataset root.")
            with Image.open(path) as image:
                value = self.transform(image.convert("RGB"))
        else:
            with self._source().open(item["member"]) as source:
                with Image.open(BytesIO(source.read())) as image:
                    value = self.transform(image.convert("RGB"))
        return value, int(item["class_id"])


def make_transforms(input_size=224):
    normalize = transforms.Normalize([.485, .456, .406], [.229, .224, .225])
    return {
        "train": transforms.Compose([
            transforms.RandomResizedCrop(input_size, scale=(.72, 1.0)),
            transforms.RandomHorizontalFlip(), transforms.ColorJitter(.15, .15, .12, .04),
            transforms.ToTensor(), normalize,
        ]),
        "development": transforms.Compose([
            transforms.Resize(round(input_size * 1.14)), transforms.CenterCrop(input_size),
            transforms.ToTensor(), normalize,
        ]),
    }


def evaluate(model, loader, device):
    model.eval()
    correct1 = correct5 = total = 0
    with torch.inference_mode():
        for images, targets in loader:
            logits = model(images.to(device))
            targets = targets.to(device)
            top = logits.topk(min(5, logits.shape[1]), dim=1).indices
            total += len(targets)
            correct1 += int((top[:, 0] == targets).sum())
            correct5 += int((top == targets[:, None]).any(dim=1).sum())
    return {
        "samples": total,
        "top1_accuracy": correct1 / total if total else 0.0,
        "top5_accuracy": correct5 / total if total else 0.0,
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("manifest", type=Path)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--epochs", type=int, default=8)
    parser.add_argument("--batch-size", type=int, default=32)
    parser.add_argument("--learning-rate", type=float, default=3e-4)
    parser.add_argument("--seed", type=int, default=20261022)
    parser.add_argument("--device", choices=("cpu", "cuda"))
    parser.add_argument("--cpu-threads", type=int, default=4)
    parser.add_argument("--sample-limit", type=int)
    parser.add_argument("--extracted-root", type=Path,
                        help="Optional ignored cache containing manifest member paths.")
    parser.add_argument("--pretrained", action="store_true",
                        help="Initialize MobileNetV3 from ImageNet weights.")
    parser.add_argument("--freeze-backbone-epochs", type=int, default=0,
                        help="Train only the classifier for this many initial epochs.")
    args = parser.parse_args()
    if args.epochs < 1 or args.batch_size < 1:
        raise SystemExit("epochs and batch size must be positive")
    random.seed(args.seed); torch.manual_seed(args.seed)
    torch.set_num_threads(max(1, args.cpu_threads))
    manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
    if manifest.get("purpose") not in ("research_development_only", "frozen_research_benchmark"):
        raise SystemExit("Refusing a manifest without a research-only designation.")
    classes = manifest.get("classes") or []
    if len(classes) < 2:
        raise SystemExit("At least two classes are required.")
    samples = list(manifest.get("samples") or [])
    if args.sample_limit:
        samples = samples[:args.sample_limit]
    split_samples = {name: [item for item in samples if item["split"] == name]
                     for name in ("train", "development")}
    if not all(split_samples.values()):
        raise SystemExit("Both train and development samples are required.")
    device = args.device or ("cuda" if torch.cuda.is_available() else "cpu")
    transforms_by_split = make_transforms()
    loaders = {
        name: DataLoader(
            ZipVehicleDataset(Path(manifest["archive"]["path"]), values, transforms_by_split[name], args.extracted_root),
            batch_size=args.batch_size, shuffle=name == "train", num_workers=0,
        ) for name, values in split_samples.items()
    }
    weights = models.MobileNet_V3_Small_Weights.DEFAULT if args.pretrained else None
    model = models.mobilenet_v3_small(weights=weights)
    model.classifier[-1] = torch.nn.Linear(model.classifier[-1].in_features, len(classes))
    if args.freeze_backbone_epochs:
        for parameter in model.features.parameters():
            parameter.requires_grad = False
    model = model.to(device)
    optimizer = torch.optim.AdamW((item for item in model.parameters() if item.requires_grad), lr=args.learning_rate)
    loss_function = torch.nn.CrossEntropyLoss()
    history, best = [], -1.0
    args.output_dir.mkdir(parents=True, exist_ok=True)
    started = time.perf_counter()
    for epoch in range(1, args.epochs + 1):
        if args.freeze_backbone_epochs and epoch == args.freeze_backbone_epochs + 1:
            for parameter in model.features.parameters():
                parameter.requires_grad = True
            optimizer = torch.optim.AdamW(model.parameters(), lr=args.learning_rate * .2)
        model.train(); total_loss = total = 0
        for images, targets in loaders["train"]:
            images, targets = images.to(device), targets.to(device)
            optimizer.zero_grad(set_to_none=True)
            loss = loss_function(model(images), targets)
            loss.backward(); optimizer.step()
            total_loss += float(loss.detach()) * len(targets); total += len(targets)
        metrics = evaluate(model, loaders["development"], device)
        record = {"epoch": epoch, "train_loss": total_loss / max(1, total), **metrics}
        history.append(record); print(json.dumps(record))
        if metrics["top1_accuracy"] > best:
            best = metrics["top1_accuracy"]
            cpu_model = model.to("cpu").eval()
            batch_dimension = torch.export.Dim("batch", min=1, max=128)
            # A batch larger than one prevents torch.export from specializing
            # the example input to a fixed singleton batch.
            exported = torch.export.export(
                cpu_model, (torch.zeros(2, 3, 224, 224),),
                dynamic_shapes=({0: batch_dimension},),
            )
            torch.export.save(exported, str(args.output_dir / "vehicle_attributes.pt2"))
            model = cpu_model.to(device)
    label_manifest = {
        "schema_version": 1, "input_size": 224, "classes": classes,
        "dataset": manifest["dataset"], "training_manifest": str(args.manifest.resolve()),
        "result_scope": "research_only_not_production_accuracy",
        "model_architecture": "mobilenet_v3_small",
        "pretrained_imagenet": args.pretrained,
    }
    (args.output_dir / "labels.json").write_text(json.dumps(label_manifest, indent=2) + "\n", encoding="utf-8")
    report = {
        "device": device, "epochs": args.epochs, "classes": len(classes),
        "pretrained_imagenet": args.pretrained,
        "freeze_backbone_epochs": args.freeze_backbone_epochs,
        "train_samples": len(split_samples["train"]),
        "development_samples": len(split_samples["development"]),
        "best_development_top1": best, "history": history,
        "elapsed_seconds": time.perf_counter() - started,
        "limitation": manifest["dataset"]["limitation"],
    }
    (args.output_dir / "training_report.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
