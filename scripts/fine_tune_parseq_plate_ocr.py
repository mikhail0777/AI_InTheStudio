"""Fine-tune official pretrained PARSeq on permitted plate-sequence training data."""
from __future__ import annotations

import argparse
from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
import random
import string
import sys
import time

from PIL import Image, ImageDraw, ImageEnhance, ImageFilter, ImageFont
import torch
import torch.nn.functional as F
from torch.utils.data import DataLoader, Dataset
from torchvision import transforms as T


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.audit_yolo_ocr_dataset import load_class_names
from scripts.train_ctc_plate_ocr import collect_samples


SYNTHETIC_PATTERNS = (
    "LLLLDDD",  # Ontario-style passenger layout
    "LDDLLL",   # Quebec-style passenger layout
    "DDDLLL",
    "LLLDDD",
    "DLLLDDD",  # common North-American alternating layouts
    "LLDDDDD",
    "LLLLDD",
    "AAAAAAA",  # vanity/general alphanumeric
)


@dataclass(frozen=True)
class SyntheticPlateSample:
    seed: int
    sequence: str


def synthetic_sequence(seed: int) -> str:
    rng = random.Random(seed)
    pattern = rng.choice(SYNTHETIC_PATTERNS)
    return "".join(
        rng.choice(string.ascii_uppercase) if token == "L"
        else rng.choice(string.digits) if token == "D"
        else rng.choice(string.ascii_uppercase + string.digits)
        for token in pattern
    )


def render_synthetic_plate(sample: SyntheticPlateSample, font_paths: list[Path]) -> Image.Image:
    """Render deterministic training data; never use synthetic plates as test truth."""
    if not font_paths:
        raise ValueError("At least one permitted TrueType font is required for synthetic training.")
    rng = random.Random(sample.seed)
    width, height = rng.randint(210, 300), rng.randint(62, 94)
    backgrounds = ((244, 244, 238), (235, 239, 244), (245, 235, 158), (232, 238, 220))
    inks = ((20, 35, 75), (18, 18, 18), (28, 62, 96), (38, 48, 38))
    image = Image.new("RGB", (width, height), rng.choice(backgrounds))
    draw = ImageDraw.Draw(image)
    border = rng.randint(2, 4)
    draw.rounded_rectangle(
        (border, border, width - border - 1, height - border - 1),
        radius=rng.randint(5, 11), outline=rng.choice(inks), width=border,
    )
    font_size = int(height * rng.uniform(.53, .70))
    font = ImageFont.truetype(str(rng.choice(font_paths)), font_size)
    text_box = draw.textbbox((0, 0), sample.sequence, font=font, stroke_width=0)
    text_width, text_height = text_box[2] - text_box[0], text_box[3] - text_box[1]
    if text_width > width * .88:
        font_size = max(16, int(font_size * width * .88 / text_width))
        font = ImageFont.truetype(str(rng.choice(font_paths)), font_size)
        text_box = draw.textbbox((0, 0), sample.sequence, font=font)
        text_width, text_height = text_box[2] - text_box[0], text_box[3] - text_box[1]
    x = (width - text_width) // 2 - text_box[0] + rng.randint(-2, 2)
    y = (height - text_height) // 2 - text_box[1] + rng.randint(-2, 2)
    draw.text((x, y), sample.sequence, font=font, fill=rng.choice(inks))
    bolt_color = (125, 125, 120)
    bolt_radius = max(1, height // 34)
    for bx in (int(width * .08), int(width * .92)):
        by = int(height * rng.choice((.18, .5, .82)))
        draw.ellipse((bx - bolt_radius, by - bolt_radius, bx + bolt_radius, by + bolt_radius), fill=bolt_color)
    # Sparse dirt/sensor noise without changing the ground-truth string.
    for _ in range(rng.randint(0, 18)):
        px, py = rng.randrange(width), rng.randrange(height)
        shade = rng.randint(75, 205)
        draw.point((px, py), fill=(shade, shade, shade))
    return image


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(4 * 1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


class PARSeqPlateDataset(Dataset):
    def __init__(self, samples, transform, training: bool, font_paths: list[Path] | None = None):
        self.samples = samples; self.transform = transform; self.training = training
        self.font_paths = font_paths or []

    def __len__(self): return len(self.samples)

    def __getitem__(self, index):
        sample = self.samples[index]
        if isinstance(sample, SyntheticPlateSample):
            image = render_synthetic_plate(sample, self.font_paths)
        else:
            with Image.open(sample.image) as raw:
                image = raw.convert("RGB")
        try:
            if self.training:
                image = ImageEnhance.Brightness(image).enhance(random.uniform(.8, 1.2))
                image = ImageEnhance.Contrast(image).enhance(random.uniform(.8, 1.25))
                if random.random() < .2:
                    image = image.filter(ImageFilter.GaussianBlur(random.uniform(.1, .8)))
                if random.random() < .12:
                    # A short horizontal exposure approximates mild motion blur
                    # while retaining the original image on disk unchanged.
                    kernel = [0.] * 10 + [.2] * 5 + [0.] * 10
                    image = image.filter(ImageFilter.Kernel((5, 5), kernel, scale=1))
                if random.random() < .2:
                    image = T.RandomPerspective(
                        distortion_scale=.12, p=1.0,
                        interpolation=T.InterpolationMode.BICUBIC,
                    )(image)
                if random.random() < .2:
                    image = T.functional.rotate(
                        image, random.uniform(-2., 2.),
                        interpolation=T.InterpolationMode.BICUBIC,
                    )
            return self.transform(image), sample.sequence
        finally:
            image.close()


def canonical_loss(model, images, labels):
    target = model.tokenizer.encode(labels, images.device)
    memory = model.model.encode(images)
    target_in, target_out = target[:, :-1], target[:, 1:]
    padding = (target_in == model.pad_id) | (target_in == model.eos_id)
    permutation = torch.arange(target.shape[1], device=images.device)
    target_mask, query_mask = model.generate_attn_masks(permutation)
    decoded = model.model.decode(target_in, memory, target_mask, padding, tgt_query_mask=query_mask)
    logits = model.model.head(decoded).flatten(end_dim=1)
    return F.cross_entropy(logits, target_out.flatten(), ignore_index=model.pad_id)


def validation_metrics(model, loader):
    exact = edits = characters = total = 0
    from scripts.evaluation_metrics import levenshtein
    model.eval()
    with torch.inference_mode():
        for images, labels in loader:
            probabilities = model(images).softmax(-1)
            observed, _ = model.tokenizer.decode(probabilities)
            total += len(labels)
            exact += sum(a.upper() == b for a, b in zip(observed, labels))
            edits += sum(levenshtein(a.upper(), b) for a, b in zip(observed, labels))
            characters += sum(len(item) for item in labels)
    return {"plates": total, "exact_matches": exact, "exact_plate_accuracy": exact / total,
            "character_accuracy": 1 - edits / characters}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--epochs", type=int, default=5)
    parser.add_argument("--batch", type=int, default=16)
    parser.add_argument("--learning-rate", type=float, default=1e-5)
    parser.add_argument("--initial-checkpoint", type=Path)
    parser.add_argument("--synthetic-samples", type=int, default=0)
    parser.add_argument("--synthetic-seed", type=int, default=20261022)
    parser.add_argument("--font-dir", type=Path, help="Directory containing permitted .ttf fonts.")
    parser.add_argument("--font-pattern", default="DejaVuSans*.ttf")
    parser.add_argument("--font-license", type=Path)
    parser.add_argument("--torch-home", type=Path, default=ROOT / "backend" / "data" / "torch")
    args = parser.parse_args(); random.seed(0); torch.manual_seed(0)
    os.environ["TORCH_HOME"] = str(args.torch_home.resolve())
    model = torch.hub.load("baudm/parseq", "parseq", pretrained=True, trust_repo=True)
    if args.initial_checkpoint:
        state = torch.load(args.initial_checkpoint, map_location="cpu", weights_only=True)
        model.load_state_dict(state["state_dict"])
    transform = T.Compose([T.Resize(tuple(model.hparams.img_size), T.InterpolationMode.BICUBIC),
                           T.ToTensor(), T.Normalize(.5, .5)])
    names = load_class_names(args.dataset / "data.yaml")
    train = collect_samples(args.dataset, "train", names, max_length=model.hparams.max_label_length)
    valid = collect_samples(args.dataset, "valid", names, max_length=model.hparams.max_label_length)
    if args.synthetic_samples < 0:
        parser.error("--synthetic-samples must be non-negative")
    font_paths = sorted(args.font_dir.glob(args.font_pattern)) if args.font_dir else []
    if args.synthetic_samples and not font_paths:
        parser.error("--synthetic-samples requires --font-dir/--font-pattern matching a .ttf font")
    if args.synthetic_samples and (not args.font_license or not args.font_license.is_file()):
        parser.error("--synthetic-samples requires an existing --font-license file")
    synthetic = [
        SyntheticPlateSample(seed=args.synthetic_seed + index,
                             sequence=synthetic_sequence(args.synthetic_seed + index))
        for index in range(args.synthetic_samples)
    ]
    train = list(train) + synthetic
    train_loader = DataLoader(PARSeqPlateDataset(train, transform, True, font_paths), batch_size=args.batch,
                              shuffle=True, num_workers=0)
    valid_loader = DataLoader(PARSeqPlateDataset(valid, transform, False), batch_size=args.batch,
                              shuffle=False, num_workers=0)
    optimizer = torch.optim.AdamW(model.parameters(), lr=args.learning_rate, weight_decay=1e-4)
    args.output.mkdir(parents=True, exist_ok=True); best = (-1., -1.); history = []; started = time.perf_counter()
    for epoch in range(1, args.epochs + 1):
        model.train(); loss_sum = 0.
        for images, labels in train_loader:
            optimizer.zero_grad(set_to_none=True); loss = canonical_loss(model, images, list(labels))
            loss.backward(); torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0); optimizer.step()
            loss_sum += float(loss.detach())
        metrics = validation_metrics(model, valid_loader)
        row = {"epoch": epoch, "train_loss": loss_sum / len(train_loader), **metrics}
        history.append(row); print(json.dumps(row), flush=True)
        key = (metrics["exact_plate_accuracy"], metrics["character_accuracy"])
        if key > best:
            best = key; torch.save({"state_dict": model.state_dict()}, args.output / "best.pt")
    best_path = args.output / "best.pt"
    (args.output / "training_report.json").write_text(json.dumps({
        "architecture": "official pretrained PARSeq, canonical-order fine-tune", "train_samples": len(train),
        "validation_samples": len(valid), "epochs": args.epochs, "learning_rate": args.learning_rate,
        "initial_checkpoint": str(args.initial_checkpoint.resolve()) if args.initial_checkpoint else None,
        "synthetic_samples": args.synthetic_samples,
        "synthetic_seed": args.synthetic_seed if args.synthetic_samples else None,
        "synthetic_patterns": list(SYNTHETIC_PATTERNS) if args.synthetic_samples else [],
        "synthetic_fonts": [str(path.resolve()) for path in font_paths],
        "synthetic_font_license": str(args.font_license.resolve()) if args.font_license else None,
        "synthetic_data_policy": "training only; never accuracy or benchmark evidence",
        "training_augmentations": [
            "brightness 0.8-1.2", "contrast 0.8-1.25", "mild Gaussian blur",
            "mild horizontal motion blur", "mild perspective distortion", "rotation +/-2 degrees",
        ],
        "elapsed_seconds": time.perf_counter() - started, "history": history,
        "best_validation": max(history, key=lambda r: (r["exact_plate_accuracy"], r["character_accuracy"])),
        "best_checkpoint_sha256": file_sha256(best_path),
    }, indent=2) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__": raise SystemExit(main())
