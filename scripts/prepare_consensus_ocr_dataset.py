"""Create an audited YOLO OCR derivative from corroborated annotations."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import shutil
from statistics import median
import sys


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.audit_yolo_ocr_dataset import (
    IMAGE_SUFFIXES,
    SPLITS,
    filename_candidates,
    load_class_names,
    ordered_sequence,
    parse_label,
)


def is_single_row(characters: list[dict]) -> bool:
    if not characters:
        return False
    y_values = [float(item["y"]) for item in characters]
    typical_height = median(float(item["height"]) for item in characters)
    return max(y_values) - min(y_values) <= max(0.05, typical_height * 0.7)


def link_or_copy(source: Path, destination: Path) -> str:
    try:
        os.link(source, destination)
        return "hardlink"
    except OSError:
        shutil.copy2(source, destination)
        return "copy"


def prepare(source: Path, destination: Path) -> dict:
    class_names = load_class_names(source / "data.yaml")
    records: list[dict] = []
    split_counts: dict[str, dict[str, int]] = {}
    materialization_modes: set[str] = set()

    if destination.exists() and any(destination.iterdir()):
        raise FileExistsError(f"Destination must be empty or absent: {destination}")
    destination.mkdir(parents=True, exist_ok=True)
    (destination / "data.yaml").write_text(
        "\n".join((
            f"path: {destination.resolve().as_posix()}",
            "train: train/images",
            "val: valid/images",
            "test: test/images",
            f"nc: {len(class_names)}",
            f"names: {json.dumps(class_names)}",
            "",
        )),
        encoding="utf-8",
    )
    readme = source / "README.roboflow.txt"
    if readme.exists():
        shutil.copy2(readme, destination / readme.name)

    for split in SPLITS:
        source_images = source / split / "images"
        source_labels = source / split / "labels"
        output_images = destination / split / "images"
        output_labels = destination / split / "labels"
        output_images.mkdir(parents=True, exist_ok=True)
        output_labels.mkdir(parents=True, exist_ok=True)
        included = excluded = 0
        for image_path in sorted(
            path for path in source_images.iterdir()
            if path.is_file() and path.suffix.lower() in IMAGE_SUFFIXES
        ):
            sequence = None
            candidates = filename_candidates(image_path)
            label_path = source_labels / f"{image_path.stem}.txt"
            if not candidates or not label_path.exists():
                reason = "missing_filename_candidate_or_label"
            else:
                characters, errors = parse_label(label_path, class_names)
                sequence = ordered_sequence(characters)
                if errors:
                    reason = "invalid_label"
                elif len(characters) != 7:
                    reason = "character_count_is_not_seven"
                elif not is_single_row(characters):
                    reason = "ambiguous_multiple_rows"
                elif sequence not in candidates:
                    reason = "label_and_filename_do_not_agree"
                else:
                    reason = ""
            if reason:
                records.append({
                    "split": split, "file": image_path.name, "status": "excluded",
                    "reason": reason,
                    "filename_candidates": candidates,
                    "label_sequence": sequence,
                })
                excluded += 1
                continue

            output_label = output_labels / label_path.name
            shutil.copy2(label_path, output_label)
            output_image = output_images / image_path.name
            if output_image.exists():
                output_image.unlink()
            materialization_modes.add(link_or_copy(image_path, output_image))
            included += 1
            records.append({
                "split": split,
                "file": image_path.name,
                "status": "included",
                "filename_candidates": candidates,
                "label_sequence": sequence,
                "original_annotation_modified": False,
            })
        split_counts[split] = {"included": included, "excluded": excluded}

    split_priority = {"train": 0, "valid": 1, "test": 2}
    identity_splits: dict[str, set[str]] = {}
    for record in records:
        if record["status"] == "included":
            identity_splits.setdefault(record["label_sequence"], set()).add(record["split"])
    retained_split = {
        identity: max(splits, key=split_priority.__getitem__)
        for identity, splits in identity_splits.items()
    }
    for record in records:
        if record["status"] != "included" or retained_split[record["label_sequence"]] == record["split"]:
            continue
        split = record["split"]
        image_path = destination / split / "images" / record["file"]
        label_path = destination / split / "labels" / f"{Path(record['file']).stem}.txt"
        image_path.unlink(missing_ok=True)
        label_path.unlink(missing_ok=True)
        record["status"] = "excluded"
        record["reason"] = "identity_reserved_for_higher_priority_split"
        record["retained_split"] = retained_split[record["label_sequence"]]
        split_counts[split]["included"] -= 1
        split_counts[split]["excluded"] += 1

    manifest = {
        "schema_version": 1,
        "source": str(source.resolve()),
        "destination": str(destination.resolve()),
        "class_names": class_names,
        "policy": {
            "required_character_count": 7,
            "requires_unambiguous_single_row": True,
            "requires_original_label_sequence_to_match_a_filename_candidate": True,
            "identity_split_priority": ["test", "valid", "train"],
            "original_annotations_modified": False,
        },
        "image_materialization": sorted(materialization_modes),
        "splits": split_counts,
        "records": records,
    }
    (destination / "derivation_manifest.json").write_text(
        json.dumps(manifest, indent=2) + "\n", encoding="utf-8",
    )
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", required=True, type=Path)
    parser.add_argument("--destination", required=True, type=Path)
    args = parser.parse_args()
    manifest = prepare(args.source, args.destination)
    print(json.dumps({
        "destination": manifest["destination"],
        "splits": manifest["splits"],
        "image_materialization": manifest["image_materialization"],
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
