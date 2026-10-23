"""Prepare train/validation CSVs for the official FastPlateOCR workflow.

The source regression/test split is deliberately excluded.  Region labels are
accepted only from an explicit per-file mapping; otherwise no ``plate_region``
column is emitted, preventing fabricated Ontario/Quebec supervision.
"""
from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
import shutil
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.audit_yolo_ocr_dataset import IMAGE_SUFFIXES, load_class_names, ordered_sequence, parse_label
from scripts.prepare_consensus_ocr_dataset import link_or_copy


def prepare(source: Path, destination: Path, region_labels: dict[str, str] | None = None) -> dict:
    if destination.exists() and any(destination.iterdir()):
        raise FileExistsError(f"Destination must be empty or absent: {destination}")
    names = load_class_names(source / "data.yaml")
    region_labels = region_labels or {}
    manifest = {
        "schema_version": 1, "source": str(source.resolve()),
        "destination": str(destination.resolve()),
        "policy": {
            "source_test_excluded": True,
            "region_labels_are_explicit_only": True,
            "originals_modified": False,
        },
        "splits": {},
    }
    for source_split, target_split in (("train", "train"), ("valid", "val")):
        target = destination / target_split
        images_dir = target / "images"
        images_dir.mkdir(parents=True, exist_ok=True)
        rows = []
        for image in sorted(path for path in (source / source_split / "images").iterdir()
                            if path.suffix.lower() in IMAGE_SUFFIXES):
            label = source / source_split / "labels" / f"{image.stem}.txt"
            characters, errors = parse_label(label, names)
            if errors:
                raise ValueError(errors[0])
            link_or_copy(image, images_dir / image.name)
            row = {"image_path": f"images/{image.name}", "plate_text": ordered_sequence(characters)}
            if image.name in region_labels:
                row["plate_region"] = region_labels[image.name]
            rows.append(row)
        has_regions = bool(rows) and all("plate_region" in row for row in rows)
        if region_labels and not has_regions:
            raise ValueError(f"Region mapping is incomplete for {source_split}")
        fields = ["image_path", "plate_text"] + (["plate_region"] if has_regions else [])
        with (target / "annotations.csv").open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=fields)
            writer.writeheader(); writer.writerows(rows)
        manifest["splits"][target_split] = {"plates": len(rows), "has_region_labels": has_regions}
    destination.mkdir(parents=True, exist_ok=True)
    (destination / "preparation_manifest.json").write_text(
        json.dumps(manifest, indent=2) + "\n", encoding="utf-8",
    )
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", required=True, type=Path)
    parser.add_argument("--destination", required=True, type=Path)
    parser.add_argument("--region-labels", type=Path)
    args = parser.parse_args()
    labels = json.loads(args.region_labels.read_text(encoding="utf-8")) if args.region_labels else None
    print(json.dumps(prepare(args.source, args.destination, labels), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
