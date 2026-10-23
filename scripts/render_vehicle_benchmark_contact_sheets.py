"""Render deterministic labelled contact sheets for vehicle benchmark QA."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from PIL import Image, ImageDraw, ImageOps


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("manifest", type=Path)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--per-class", type=int, default=6)
    parser.add_argument("--columns", type=int, default=5)
    parser.add_argument("--rows", type=int, default=4)
    parser.add_argument("--split", choices=("train", "development", "test"))
    args = parser.parse_args()
    manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
    classes = {row["class_id"]: row for row in manifest["classes"]}
    selected = []
    for class_id in sorted(classes):
        values = [
            sample for sample in manifest["samples"]
            if sample["class_id"] == class_id
            and (not args.split or sample["split"] == args.split)
        ]
        values.sort(key=lambda row: hashlib.sha256(row["sample_id"].encode()).hexdigest())
        selected.extend(values[:args.per_class])
    args.output_dir.mkdir(parents=True, exist_ok=True)
    page_size = args.columns * args.rows
    for page_number, start in enumerate(range(0, len(selected), page_size), 1):
        canvas = Image.new("RGB", (args.columns * 240, args.rows * 210), "white")
        draw = ImageDraw.Draw(canvas)
        for offset, sample in enumerate(selected[start:start + page_size]):
            label = classes[sample["class_id"]]
            with Image.open(sample["path"]) as source:
                tile = ImageOps.contain(source.convert("RGB"), (228, 170))
            column, row = offset % args.columns, offset // args.columns
            x, y = column * 240 + 6, row * 210 + 6
            canvas.paste(tile, (x + (228 - tile.width) // 2, y))
            draw.text((x, y + 174), f"{sample['sample_id']}  {label['make']} {label['model']}", fill="black")
            draw.text((x, y + 188), f"{label['year_start']}-{label['year_end']}  {sample['split']}", fill="black")
        canvas.save(args.output_dir / f"contact_{page_number:02d}.jpg", quality=92)
    print(f"Rendered {len(selected)} samples across {page_number} contact sheets.")


if __name__ == "__main__":
    main()
