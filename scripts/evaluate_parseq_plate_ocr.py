"""Evaluate the official pretrained PARSeq reader on labelled plate crops."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import sys
import time

from PIL import Image
import torch
from torchvision import transforms as T


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.audit_yolo_ocr_dataset import IMAGE_SUFFIXES, load_class_names, ordered_sequence, parse_label
from scripts.evaluation_metrics import levenshtein, wilson_interval


def confidence_bins(rows: list[dict], bins: int = 10) -> list[dict]:
    output = []
    for index in range(bins):
        low, high = index / bins, (index + 1) / bins
        selected = [r for r in rows if low <= r["confidence"] < high or (index == bins - 1 and r["confidence"] == 1)]
        if selected:
            output.append({
                "low": low, "high": high, "count": len(selected),
                "mean_confidence": sum(r["confidence"] for r in selected) / len(selected),
                "exact_accuracy": sum(r["observed"] == r["expected"] for r in selected) / len(selected),
            })
    return output


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", required=True, type=Path)
    parser.add_argument("--split", choices=["valid", "test"], required=True)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--torch-home", type=Path, default=ROOT / "backend" / "data" / "torch")
    parser.add_argument("--model", default="parseq", choices=["parseq", "parseq_tiny"])
    parser.add_argument("--checkpoint", type=Path)
    args = parser.parse_args()
    os.environ["TORCH_HOME"] = str(args.torch_home.resolve())
    model = torch.hub.load("baudm/parseq", args.model, pretrained=True, trust_repo=True).eval()
    if args.checkpoint:
        model.load_state_dict(torch.load(args.checkpoint, map_location="cpu", weights_only=True)["state_dict"])
    transform = T.Compose([
        T.Resize(tuple(model.hparams.img_size), T.InterpolationMode.BICUBIC),
        T.ToTensor(), T.Normalize(0.5, 0.5),
    ])

    names = load_class_names(args.dataset / "data.yaml")
    images = sorted(
        item for item in (args.dataset / args.split / "images").iterdir()
        if item.is_file() and item.suffix.lower() in IMAGE_SUFFIXES
    )
    rows = []; started = time.perf_counter()
    with torch.inference_mode():
        for offset in range(0, len(images), 16):
            batch_paths = images[offset:offset + 16]
            tensors = []
            for path in batch_paths:
                with Image.open(path) as image:
                    tensors.append(transform(image.convert("RGB")))
            probabilities = model(torch.stack(tensors)).softmax(-1)
            texts, token_probabilities = model.tokenizer.decode(probabilities)
            for path, observed, token_probs in zip(batch_paths, texts, token_probabilities):
                characters, errors = parse_label(
                    args.dataset / args.split / "labels" / f"{path.stem}.txt", names,
                )
                if errors:
                    raise ValueError(errors[0])
                expected = ordered_sequence(characters)
                confidence = float(token_probs.clamp_min(1e-9).log().mean().exp()) if len(token_probs) else 0.0
                rows.append({
                    "file": path.name, "expected": expected, "observed": observed.upper(),
                    "confidence": confidence,
                })
    elapsed = time.perf_counter() - started
    exact = sum(row["observed"] == row["expected"] for row in rows)
    characters = sum(len(row["expected"]) for row in rows)
    edits = sum(levenshtein(row["observed"], row["expected"]) for row in rows)
    report = {
        "schema_version": 1, "generated_at": datetime.now(timezone.utc).isoformat(),
        "model": f"baudm/parseq:{args.model}", "checkpoint": str(args.checkpoint.resolve()) if args.checkpoint else None,
        "licence": "Apache-2.0",
        "dataset": str(args.dataset.resolve()), "split": args.split,
        "metrics": {
            "plates": len(rows), "exact_matches": exact,
            "exact_plate_accuracy": exact / len(rows) if rows else 0.0,
            "exact_plate_accuracy_wilson_95": wilson_interval(exact, len(rows)),
            "character_edits": edits, "ground_truth_characters": characters,
            "character_accuracy": 1.0 - edits / characters if characters else 0.0,
            "elapsed_seconds": elapsed, "images_per_second": len(rows) / elapsed if elapsed else 0.0,
        },
        "confidence_bins": confidence_bins(rows), "rows": rows,
        "limitations": [
            "Greedy pretrained PARSeq evaluation; domain-specific fine-tuning and top-k decoding are separate experiments.",
            "Cropped plate accuracy does not measure full-frame localization or video event accuracy.",
        ],
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"output": str(args.output), "metrics": report["metrics"]}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
