"""Train an end-to-end CRNN/CTC plate sequence recognizer on YOLO-labelled crops."""
from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import random
import sys
import time

import numpy as np
from PIL import Image, ImageEnhance, ImageFilter
import torch
from torch import nn
from torch.utils.data import DataLoader, Dataset


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.audit_yolo_ocr_dataset import IMAGE_SUFFIXES, load_class_names, ordered_sequence, parse_label
from scripts.evaluation_metrics import levenshtein, wilson_interval
from scripts.prepare_consensus_ocr_dataset import is_single_row


@dataclass(frozen=True)
class Sample:
    image: Path
    sequence: str


def collect_samples(root: Path, split: str, names: list[str], max_length: int = 12) -> list[Sample]:
    samples: list[Sample] = []
    for image in sorted(
        item for item in (root / split / "images").iterdir()
        if item.is_file() and item.suffix.lower() in IMAGE_SUFFIXES
    ):
        characters, errors = parse_label(root / split / "labels" / f"{image.stem}.txt", names)
        if errors or not is_single_row(characters):
            continue
        sequence = ordered_sequence(characters)
        if 4 <= len(sequence) <= max_length:
            samples.append(Sample(image, sequence))
    return samples


def plate_tensor(image: Image.Image, training: bool, width: int = 160, height: int = 32) -> torch.Tensor:
    image = image.convert("L")
    if training:
        image = ImageEnhance.Brightness(image).enhance(random.uniform(0.75, 1.25))
        image = ImageEnhance.Contrast(image).enhance(random.uniform(0.75, 1.35))
        if random.random() < 0.25:
            image = image.filter(ImageFilter.GaussianBlur(random.uniform(0.2, 1.0)))
    scale = min(width / image.width, height / image.height)
    resized = image.resize(
        (max(1, round(image.width * scale)), max(1, round(image.height * scale))),
        Image.Resampling.BILINEAR,
    )
    canvas = Image.new("L", (width, height), color=127)
    canvas.paste(resized, ((width - resized.width) // 2, (height - resized.height) // 2))
    array = np.asarray(canvas, dtype=np.float32) / 127.5 - 1.0
    return torch.from_numpy(array).unsqueeze(0)


class PlateDataset(Dataset):
    def __init__(self, samples: list[Sample], alphabet: list[str], training: bool):
        self.samples = samples
        self.training = training
        self.ids = {char: index + 1 for index, char in enumerate(alphabet)}

    def __len__(self) -> int:
        return len(self.samples)

    def __getitem__(self, index: int):
        sample = self.samples[index]
        with Image.open(sample.image) as image:
            tensor = plate_tensor(image, self.training)
        target = torch.tensor([self.ids[char] for char in sample.sequence], dtype=torch.long)
        return tensor, target, sample.sequence


def collate(batch):
    images, targets, sequences = zip(*batch)
    return torch.stack(images), torch.cat(targets), torch.tensor([len(item) for item in targets]), sequences


class PlateCRNN(nn.Module):
    def __init__(self, classes: int):
        super().__init__()
        self.features = nn.Sequential(
            nn.Conv2d(1, 64, 3, padding=1), nn.ReLU(True), nn.MaxPool2d(2, 2),
            nn.Conv2d(64, 128, 3, padding=1), nn.ReLU(True), nn.MaxPool2d(2, 2),
            nn.Conv2d(128, 256, 3, padding=1), nn.BatchNorm2d(256), nn.ReLU(True),
            nn.Conv2d(256, 256, 3, padding=1), nn.ReLU(True), nn.MaxPool2d((2, 1)),
            nn.Conv2d(256, 384, 3, padding=1), nn.BatchNorm2d(384), nn.ReLU(True),
            nn.MaxPool2d((2, 1)), nn.Conv2d(384, 256, (2, 1)), nn.ReLU(True),
        )
        self.sequence = nn.LSTM(256, 128, num_layers=2, bidirectional=True, dropout=0.2)
        self.classifier = nn.Linear(256, classes + 1)

    def forward(self, images: torch.Tensor) -> torch.Tensor:
        features = self.features(images).squeeze(2).permute(2, 0, 1)
        features, _ = self.sequence(features)
        return self.classifier(features).log_softmax(2)


def greedy_decode(log_probs: torch.Tensor, alphabet: list[str]) -> list[str]:
    results: list[str] = []
    for encoded in log_probs.argmax(2).transpose(0, 1).tolist():
        previous = 0
        output: list[str] = []
        for token in encoded:
            if token and token != previous:
                output.append(alphabet[token - 1])
            previous = token
        results.append("".join(output))
    return results


def evaluate(model: nn.Module, loader: DataLoader, alphabet: list[str]) -> dict:
    model.eval()
    expected: list[str] = []
    observed: list[str] = []
    with torch.inference_mode():
        for images, _, _, sequences in loader:
            observed.extend(greedy_decode(model(images), alphabet))
            expected.extend(sequences)
    exact = sum(a == b for a, b in zip(expected, observed))
    characters = sum(len(item) for item in expected)
    edits = sum(levenshtein(a, b) for a, b in zip(expected, observed))
    return {
        "plates": len(expected), "exact_matches": exact,
        "exact_plate_accuracy": exact / len(expected) if expected else 0.0,
        "exact_plate_accuracy_wilson_95": wilson_interval(exact, len(expected)),
        "ground_truth_characters": characters, "character_edits": edits,
        "character_accuracy": 1.0 - edits / characters if characters else 0.0,
    }


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(4 * 1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--epochs", type=int, default=30)
    parser.add_argument("--batch", type=int, default=32)
    parser.add_argument("--learning-rate", type=float, default=0.001)
    parser.add_argument("--seed", type=int, default=0)
    args = parser.parse_args()
    random.seed(args.seed); np.random.seed(args.seed); torch.manual_seed(args.seed)
    alphabet = load_class_names(args.dataset / "data.yaml")
    train_samples = collect_samples(args.dataset, "train", alphabet)
    valid_samples = collect_samples(args.dataset, "valid", alphabet)
    if not train_samples or not valid_samples:
        raise SystemExit("No eligible train/validation samples")
    train_loader = DataLoader(
        PlateDataset(train_samples, alphabet, True), batch_size=args.batch,
        shuffle=True, collate_fn=collate, num_workers=0,
    )
    valid_loader = DataLoader(
        PlateDataset(valid_samples, alphabet, False), batch_size=args.batch,
        shuffle=False, collate_fn=collate, num_workers=0,
    )
    model = PlateCRNN(len(alphabet))
    optimizer = torch.optim.AdamW(model.parameters(), lr=args.learning_rate, weight_decay=1e-4)
    scheduler = torch.optim.lr_scheduler.CosineAnnealingLR(optimizer, T_max=args.epochs)
    criterion = nn.CTCLoss(blank=0, zero_infinity=True)
    args.output.mkdir(parents=True, exist_ok=True)
    best_key = (-1.0, -1.0)
    history = []
    started = time.perf_counter()
    for epoch in range(1, args.epochs + 1):
        model.train(); total_loss = 0.0
        for images, targets, lengths, _ in train_loader:
            optimizer.zero_grad(set_to_none=True)
            log_probs = model(images)
            input_lengths = torch.full((images.size(0),), log_probs.size(0), dtype=torch.long)
            loss = criterion(log_probs, targets, input_lengths, lengths)
            loss.backward()
            nn.utils.clip_grad_norm_(model.parameters(), 5.0)
            optimizer.step(); total_loss += float(loss.detach())
        scheduler.step()
        metrics = evaluate(model, valid_loader, alphabet)
        row = {"epoch": epoch, "train_loss": total_loss / len(train_loader), **metrics}
        history.append(row); print(json.dumps(row), flush=True)
        key = (metrics["exact_plate_accuracy"], metrics["character_accuracy"])
        if key > best_key:
            best_key = key
            torch.save({"state_dict": model.state_dict(), "alphabet": alphabet}, args.output / "best.pt")
    elapsed = time.perf_counter() - started
    report = {
        "schema_version": 1, "generated_at": datetime.now(timezone.utc).isoformat(),
        "dataset": str(args.dataset.resolve()), "train_samples": len(train_samples),
        "validation_samples": len(valid_samples), "alphabet": alphabet,
        "architecture": "CRNN with CTC sequence loss", "seed": args.seed,
        "epochs": args.epochs, "batch": args.batch, "elapsed_seconds": elapsed,
        "history": history, "best_validation": max(
            history, key=lambda row: (row["exact_plate_accuracy"], row["character_accuracy"]),
        ),
    }
    report["checkpoint_sha256"] = sha256(args.output / "best.pt")
    (args.output / "training_report.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
