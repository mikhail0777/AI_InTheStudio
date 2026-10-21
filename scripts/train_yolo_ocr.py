"""Train a YOLO character detector with LotTrace's reproducible defaults."""
from __future__ import annotations

import argparse
from pathlib import Path


def validate_inputs(model: Path, dataset: Path) -> tuple[Path, Path]:
    model = model.resolve()
    data_yaml = (dataset / "data.yaml").resolve() if dataset.is_dir() else dataset.resolve()
    if not model.is_file():
        raise FileNotFoundError(f"Model checkpoint not found: {model}")
    if not data_yaml.is_file():
        raise FileNotFoundError(f"Dataset YAML not found: {data_yaml}")
    return model, data_yaml


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", required=True, type=Path)
    parser.add_argument("--dataset", required=True, type=Path)
    parser.add_argument("--project", required=True, type=Path)
    parser.add_argument("--name", required=True)
    parser.add_argument("--epochs", type=int, default=30)
    parser.add_argument("--imgsz", type=int, default=320)
    parser.add_argument("--batch", type=int, default=16)
    parser.add_argument("--patience", type=int, default=5)
    parser.add_argument("--device", default="cpu")
    parser.add_argument("--workers", type=int, default=0)
    args = parser.parse_args()
    if min(args.epochs, args.imgsz, args.batch) <= 0 or args.patience < 0 or args.workers < 0:
        parser.error("epochs, imgsz, and batch must be positive; patience and workers cannot be negative")

    model_path, data_yaml = validate_inputs(args.model, args.dataset)
    from ultralytics import YOLO

    YOLO(str(model_path)).train(
        data=str(data_yaml),
        project=str(args.project.resolve()),
        name=args.name,
        epochs=args.epochs,
        imgsz=args.imgsz,
        batch=args.batch,
        patience=args.patience,
        device=args.device,
        workers=args.workers,
        cache="ram",
        deterministic=True,
        seed=0,
        warmup_epochs=1.0,
        fliplr=0.0,
        degrees=2.0,
        translate=0.05,
        scale=0.2,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
