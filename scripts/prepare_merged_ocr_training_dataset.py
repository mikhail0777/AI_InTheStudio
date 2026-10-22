"""Merge a permitted supplemental YOLO OCR train split into a 36-class dataset."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import shutil
import sys


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.audit_yolo_ocr_dataset import IMAGE_SUFFIXES, load_class_names
from scripts.prepare_consensus_ocr_dataset import link_or_copy


def remap_label(source: Path, destination: Path, class_map: dict[int, int]) -> int:
    output: list[str] = []
    for line_number, raw in enumerate(source.read_text(encoding="utf-8").splitlines(), 1):
        fields = raw.split()
        if len(fields) != 5:
            raise ValueError(f"{source}:{line_number}: expected 5 YOLO fields")
        source_id = int(fields[0])
        if source_id not in class_map:
            raise ValueError(f"{source}:{line_number}: unmapped class {source_id}")
        output.append(" ".join((str(class_map[source_id]), *fields[1:])))
    destination.write_text("\n".join(output) + ("\n" if output else ""), encoding="utf-8")
    return len(output)


def _materialize_split(
    source: Path,
    destination: Path,
    split: str,
    prefix: str,
    class_map: dict[int, int],
) -> dict:
    output_images = destination / split / "images"
    output_labels = destination / split / "labels"
    output_images.mkdir(parents=True, exist_ok=True)
    output_labels.mkdir(parents=True, exist_ok=True)
    images = characters = 0
    modes: set[str] = set()
    for image in sorted(
        item for item in (source / split / "images").iterdir()
        if item.is_file() and item.suffix.lower() in IMAGE_SUFFIXES
    ):
        label = source / split / "labels" / f"{image.stem}.txt"
        if not label.is_file():
            raise FileNotFoundError(f"Missing label for {image}")
        output_stem = f"{prefix}__{image.stem}"
        modes.add(link_or_copy(image, output_images / f"{output_stem}{image.suffix.lower()}"))
        characters += remap_label(label, output_labels / f"{output_stem}.txt", class_map)
        images += 1
    return {"images": images, "character_instances": characters, "materialization": sorted(modes)}


def prepare(primary: Path, supplemental: Path, destination: Path, permission: str) -> dict:
    if destination.exists() and any(destination.iterdir()):
        raise FileExistsError(f"Destination must be empty or absent: {destination}")
    primary_names = load_class_names(primary / "data.yaml")
    supplemental_names = load_class_names(supplemental / "data.yaml")
    target_ids = {name: index for index, name in enumerate(primary_names)}
    missing = sorted(set(supplemental_names) - set(primary_names))
    if missing:
        raise ValueError(f"Supplemental classes absent from primary alphabet: {missing}")
    primary_map = {index: index for index in range(len(primary_names))}
    supplemental_map = {index: target_ids[name] for index, name in enumerate(supplemental_names)}

    destination.mkdir(parents=True, exist_ok=True)
    (destination / "data.yaml").write_text(
        "\n".join((
            f"path: {destination.resolve().as_posix()}",
            "train: train/images",
            "val: valid/images",
            "test: test/images",
            f"nc: {len(primary_names)}",
            f"names: {json.dumps(primary_names)}",
            "",
        )), encoding="utf-8",
    )
    manifest = {
        "schema_version": 1,
        "permission": permission,
        "target_class_names": primary_names,
        "supplemental_classes_missing_from_target": missing,
        "sources": {
            "primary": str(primary.resolve()),
            "supplemental": str(supplemental.resolve()),
        },
        "policy": {
            "primary_train_included": True,
            "supplemental_train_included": True,
            "supplemental_validation_and_test_reserved": True,
            "validation_and_test_source": "primary_only",
            "class_mapping": "by exact character name",
        },
        "splits": {},
    }
    primary_train = _materialize_split(primary, destination, "train", "primary", primary_map)
    supplemental_train = _materialize_split(
        supplemental, destination, "train", "supplemental", supplemental_map,
    )
    manifest["splits"]["train"] = {
        "images": primary_train["images"] + supplemental_train["images"],
        "character_instances": primary_train["character_instances"] + supplemental_train["character_instances"],
        "sources": {"primary": primary_train, "supplemental": supplemental_train},
    }
    for split in ("valid", "test"):
        manifest["splits"][split] = _materialize_split(
            primary, destination, split, "primary", primary_map,
        )
    (destination / "derivation_manifest.json").write_text(
        json.dumps(manifest, indent=2) + "\n", encoding="utf-8",
    )
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--primary", required=True, type=Path)
    parser.add_argument("--supplemental", required=True, type=Path)
    parser.add_argument("--destination", required=True, type=Path)
    parser.add_argument("--permission", required=True)
    args = parser.parse_args()
    manifest = prepare(args.primary, args.supplemental, args.destination, args.permission)
    print(json.dumps({"destination": str(args.destination), "splits": manifest["splits"]}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
