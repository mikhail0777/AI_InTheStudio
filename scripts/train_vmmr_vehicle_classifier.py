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
from torch.utils.data import DataLoader, Dataset, WeightedRandomSampler
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
        if item.get("path"):
            path = Path(item["path"]).resolve()
            if not path.is_file():
                raise FileNotFoundError(f"Manifest image does not exist: {path}")
            with Image.open(path) as image:
                value = self.transform(image.convert("RGB"))
        elif self.extracted_root:
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
            transforms.RandomErasing(p=.2, scale=(.02, .18), ratio=(.4, 2.5)),
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


def initialize_from_export(model, export_path: Path) -> int:
    """Load a compatible backbone and copy the old classifier rows in order."""
    source = torch.export.load(str(export_path)).module().state_dict()
    target = model.state_dict()
    classifier_weight = "classifier.1.weight"
    classifier_bias = "classifier.1.bias"
    if classifier_weight not in source or classifier_weight not in target:
        raise ValueError("Export and target must use the expected torchvision classifier")
    compatible = {
        key: value for key, value in source.items()
        if key in target and target[key].shape == value.shape
        and key not in (classifier_weight, classifier_bias)
    }
    model.load_state_dict(compatible, strict=False)
    old_classes = source[classifier_weight].shape[0]
    if old_classes > target[classifier_weight].shape[0]:
        raise ValueError("Initial export has more classes than the expanded model")
    with torch.no_grad():
        model.classifier[-1].weight[:old_classes].copy_(source[classifier_weight])
        model.classifier[-1].bias[:old_classes].copy_(source[classifier_bias])
    return old_classes


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("manifest", type=Path)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--epochs", type=int, default=8)
    parser.add_argument("--batch-size", type=int, default=32)
    parser.add_argument("--learning-rate", type=float, default=3e-4)
    parser.add_argument("--architecture", choices=("mobilenet_v3_small", "efficientnet_b0"),
                        default="mobilenet_v3_small")
    parser.add_argument("--input-size", type=int, default=224)
    parser.add_argument("--label-smoothing", type=float, default=0.0)
    parser.add_argument("--seed", type=int, default=20261022)
    parser.add_argument("--device", choices=("cpu", "cuda"))
    parser.add_argument("--cpu-threads", type=int, default=4)
    parser.add_argument("--sample-limit", type=int)
    parser.add_argument("--extracted-root", type=Path,
                        help="Optional ignored cache containing manifest member paths.")
    parser.add_argument("--pretrained", action="store_true",
                        help="Initialize the selected backbone from ImageNet weights.")
    parser.add_argument("--initial-export-model", type=Path,
                        help="Expand an existing export whose classes are the manifest's leading classes.")
    parser.add_argument("--freeze-backbone-epochs", type=int, default=0,
                        help="Train only the classifier for this many initial epochs.")
    parser.add_argument("--balanced-sampling", action="store_true",
                        help="Sample training classes uniformly despite unequal class sizes.")
    parser.add_argument("--metadata-only", action="store_true",
                        help="Write labels for an already-created compatible checkpoint and exit.")
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
    args.output_dir.mkdir(parents=True, exist_ok=True)
    label_manifest = {
        "schema_version": 1, "input_size": args.input_size, "classes": classes,
        "dataset": manifest["dataset"], "training_manifest": str(args.manifest.resolve()),
        "result_scope": "research_only_not_production_accuracy",
        "model_architecture": args.architecture,
        "pretrained_imagenet": args.pretrained,
        "architecture": args.architecture,
        "label_smoothing": args.label_smoothing,
        "balanced_sampling": args.balanced_sampling,
    }
    (args.output_dir / "labels.json").write_text(json.dumps(label_manifest, indent=2) + "\n", encoding="utf-8")
    if args.metadata_only:
        return
    transforms_by_split = make_transforms(args.input_size)
    train_sampler = None
    if args.balanced_sampling:
        counts: dict[int, int] = {}
        for item in split_samples["train"]:
            class_id = int(item["class_id"])
            counts[class_id] = counts.get(class_id, 0) + 1
        weights = [1.0 / counts[int(item["class_id"])] for item in split_samples["train"]]
        generator = torch.Generator().manual_seed(args.seed)
        train_sampler = WeightedRandomSampler(
            weights, num_samples=len(weights), replacement=True, generator=generator,
        )
    loaders = {}
    for name, values in split_samples.items():
        loaders[name] = DataLoader(
            ZipVehicleDataset(
                Path(manifest["archive"]["path"]), values,
                transforms_by_split[name], args.extracted_root,
            ),
            batch_size=args.batch_size,
            shuffle=name == "train" and train_sampler is None,
            sampler=train_sampler if name == "train" else None,
            num_workers=0,
        )
    if args.architecture == "efficientnet_b0":
        weights = models.EfficientNet_B0_Weights.DEFAULT if args.pretrained else None
        model = models.efficientnet_b0(weights=weights)
    else:
        weights = models.MobileNet_V3_Small_Weights.DEFAULT if args.pretrained else None
        model = models.mobilenet_v3_small(weights=weights)
    model.classifier[-1] = torch.nn.Linear(model.classifier[-1].in_features, len(classes))
    initialized_classes = 0
    if args.initial_export_model:
        initialized_classes = initialize_from_export(model, args.initial_export_model)
    if args.freeze_backbone_epochs:
        for parameter in model.features.parameters():
            parameter.requires_grad = False
    model = model.to(device)
    optimizer = torch.optim.AdamW(
        (item for item in model.parameters() if item.requires_grad),
        lr=args.learning_rate,
        weight_decay=.01,
    )
    loss_function = torch.nn.CrossEntropyLoss(label_smoothing=args.label_smoothing)
    history, best = [], -1.0
    started = time.perf_counter()
    for epoch in range(1, args.epochs + 1):
        if args.freeze_backbone_epochs and epoch == args.freeze_backbone_epochs + 1:
            for parameter in model.features.parameters():
                parameter.requires_grad = True
            optimizer = torch.optim.AdamW(model.parameters(), lr=args.learning_rate * .2, weight_decay=.01)
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
                cpu_model, (torch.zeros(2, 3, args.input_size, args.input_size),),
                dynamic_shapes=({0: batch_dimension},),
            )
            torch.export.save(exported, str(args.output_dir / "vehicle_attributes.pt2"))
            model = cpu_model.to(device)
    report = {
        "device": device, "epochs": args.epochs, "classes": len(classes),
        "pretrained_imagenet": args.pretrained,
        "initialized_leading_classes": initialized_classes,
        "freeze_backbone_epochs": args.freeze_backbone_epochs,
        "balanced_sampling": args.balanced_sampling,
        "train_samples": len(split_samples["train"]),
        "development_samples": len(split_samples["development"]),
        "best_development_top1": best, "history": history,
        "elapsed_seconds": time.perf_counter() - started,
        "limitation": manifest["dataset"]["limitation"],
    }
    (args.output_dir / "training_report.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
