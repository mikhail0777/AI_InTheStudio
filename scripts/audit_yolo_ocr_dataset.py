"""Audit a YOLO character-detection dataset before training or evaluation."""
from __future__ import annotations

import argparse
import ast
from collections import Counter, defaultdict
import hashlib
import json
from pathlib import Path
import re
from statistics import median
from typing import Iterable


IMAGE_SUFFIXES = {".bmp", ".jpeg", ".jpg", ".png", ".webp"}
SPLITS = ("train", "valid", "test")
ROBOFLOW_SUFFIX = re.compile(r"_(?:bmp|jpeg|jpg|png|webp)\.rf\.[0-9a-f]+$", re.IGNORECASE)


def load_class_names(data_yaml: Path) -> list[str]:
    for line in data_yaml.read_text(encoding="utf-8-sig").splitlines():
        if line.lstrip().startswith("names:"):
            value = line.split(":", 1)[1].strip()
            names = ast.literal_eval(value)
            if not isinstance(names, list) or not all(isinstance(item, str) for item in names):
                break
            return names
    raise ValueError(f"Could not read a names list from {data_yaml}")


def parse_label(path: Path, class_names: list[str]) -> tuple[list[dict], list[str]]:
    characters: list[dict] = []
    errors: list[str] = []
    for line_number, line in enumerate(path.read_text(encoding="utf-8-sig").splitlines(), start=1):
        fields = line.split()
        if len(fields) != 5:
            errors.append(f"line {line_number}: expected 5 fields")
            continue
        try:
            class_id = int(fields[0])
            center_x, center_y, width, height = map(float, fields[1:])
        except ValueError:
            errors.append(f"line {line_number}: non-numeric field")
            continue
        if not 0 <= class_id < len(class_names):
            errors.append(f"line {line_number}: class {class_id} is outside the declared range")
            continue
        if not all(0.0 <= value <= 1.0 for value in (center_x, center_y, width, height)):
            errors.append(f"line {line_number}: coordinates are not normalized")
            continue
        if width <= 0.0 or height <= 0.0:
            errors.append(f"line {line_number}: box has no area")
            continue
        characters.append({
            "class_id": class_id,
            "character": class_names[class_id],
            "x": center_x,
            "y": center_y,
            "width": width,
            "height": height,
        })
    return characters, errors


def ordered_sequence(characters: Iterable[dict]) -> str:
    """Order character boxes by visual row and then from left to right."""
    boxes = list(characters)
    if not boxes:
        return ""
    typical_height = median(float(box["height"]) for box in boxes)
    row_tolerance = max(0.04, typical_height * 0.55)
    rows: list[list[dict]] = []
    for box in sorted(boxes, key=lambda item: (float(item["y"]), float(item["x"]))):
        nearest = min(
            rows,
            key=lambda row: abs(float(box["y"]) - sum(float(item["y"]) for item in row) / len(row)),
            default=None,
        )
        if nearest is None:
            rows.append([box])
            continue
        row_y = sum(float(item["y"]) for item in nearest) / len(nearest)
        if abs(float(box["y"]) - row_y) <= row_tolerance:
            nearest.append(box)
        else:
            rows.append([box])
    rows.sort(key=lambda row: sum(float(item["y"]) for item in row) / len(row))
    return "".join(
        str(box["character"])
        for row in rows
        for box in sorted(row, key=lambda item: float(item["x"]))
    )


def filename_truth(image_path: Path) -> str | None:
    """Return an apparent leading plate token without assuming it is correct."""
    candidates = filename_candidates(image_path)
    return candidates[0] if candidates else None


def filename_candidates(image_path: Path) -> list[str]:
    """Return plausible plate tokens that precede UUID/timestamp metadata."""
    source_stem = ROBOFLOW_SUFFIX.sub("", image_path.stem)
    output = []
    for token in source_stem.split("_")[:2]:
        candidate = token.upper()
        if 4 <= len(candidate) <= 10 and candidate.isalnum() and any(char.isalpha() for char in candidate) and any(char.isdigit() for char in candidate):
            output.append(candidate)
    return list(dict.fromkeys(output))


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def audit(root: Path, compare_filename_truth: bool = False) -> dict:
    class_names = load_class_names(root / "data.yaml")
    split_reports: dict[str, dict] = {}
    hashes: dict[str, list[tuple[str, str]]] = defaultdict(list)
    identities: dict[str, set[str]] = defaultdict(set)
    all_errors: list[dict[str, str]] = []

    for split in SPLITS:
        images_dir = root / split / "images"
        labels_dir = root / split / "labels"
        images = sorted(
            path for path in images_dir.iterdir()
            if path.is_file() and path.suffix.lower() in IMAGE_SUFFIXES
        ) if images_dir.exists() else []
        labels = {path.stem: path for path in labels_dir.glob("*.txt")} if labels_dir.exists() else {}
        image_stems = {path.stem for path in images}
        class_counts: Counter[str] = Counter()
        sequence_lengths: Counter[int] = Counter()
        empty_labels = 0
        filename_comparable = 0
        filename_exact = 0
        filename_mismatches: list[dict[str, str]] = []

        for image_path in images:
            label_path = labels.get(image_path.stem)
            if label_path is None:
                all_errors.append({"file": str(image_path.relative_to(root)), "error": "missing label"})
                continue
            characters, errors = parse_label(label_path, class_names)
            for error in errors:
                all_errors.append({"file": str(label_path.relative_to(root)), "error": error})
            sequence = ordered_sequence(characters)
            sequence_lengths[len(sequence)] += 1
            class_counts.update(box["character"] for box in characters)
            empty_labels += int(not characters)
            image_hash = sha256(image_path)
            hashes[image_hash].append((split, str(image_path.relative_to(root))))
            if compare_filename_truth:
                candidates = filename_candidates(image_path)
                if candidates:
                    filename_comparable += 1
                    identity = sequence if sequence in candidates else candidates[0]
                    identities[identity].add(split)
                    if sequence in candidates:
                        filename_exact += 1
                    elif len(filename_mismatches) < 25:
                        filename_mismatches.append({
                            "file": str(image_path.relative_to(root)),
                            "filename_truth": candidates[0],
                            "filename_candidates": candidates,
                            "label_sequence": sequence,
                        })

        split_reports[split] = {
            "images": len(images),
            "labels": len(labels),
            "images_without_labels": len(image_stems - labels.keys()),
            "labels_without_images": len(labels.keys() - image_stems),
            "empty_labels": empty_labels,
            "character_instances": sum(class_counts.values()),
            "class_counts": dict(sorted(class_counts.items())),
            "sequence_length_counts": {str(key): value for key, value in sorted(sequence_lengths.items())},
            "filename_truth": {
                "enabled": compare_filename_truth,
                "comparable_images": filename_comparable,
                "exact_matches": filename_exact,
                "exact_match_rate": filename_exact / filename_comparable if filename_comparable else None,
                "sample_mismatches": filename_mismatches,
                "warning": "Filename-derived text is an audit cross-check, not authoritative ground truth.",
            },
        }

    duplicate_groups = [
        {"sha256": digest, "files": [{"split": split, "file": name} for split, name in files]}
        for digest, files in hashes.items()
        if len({split for split, _ in files}) > 1
    ]
    identity_leaks = {
        identity: sorted(splits) for identity, splits in identities.items() if len(splits) > 1
    }
    character_detection_eligible = not all_errors and not duplicate_groups
    filename_totals = [
        split_reports[split]["filename_truth"] for split in SPLITS
    ]
    exact_sequence_eligible = bool(compare_filename_truth) and character_detection_eligible
    exact_sequence_eligible = exact_sequence_eligible and not identity_leaks and all(
        item["comparable_images"] == split_reports[split]["images"]
        and item["exact_matches"] == item["comparable_images"]
        for split, item in zip(SPLITS, filename_totals)
    )
    return {
        "schema_version": 1,
        "dataset_root": str(root.resolve()),
        "class_names": class_names,
        "splits": split_reports,
        "invalid_label_count": len(all_errors),
        "invalid_label_samples": all_errors[:100],
        "cross_split_exact_duplicate_groups": duplicate_groups,
        "cross_split_filename_identity_count": len(identity_leaks),
        "cross_split_filename_identity_samples": dict(list(sorted(identity_leaks.items()))[:100]),
        "character_detection_evaluation_eligible": character_detection_eligible,
        "exact_plate_sequence_evaluation_eligible": exact_sequence_eligible,
        "limitations": [
            "Character sequences are reconstructed from spatially ordered detection boxes.",
            "Human annotation provenance cannot be established from YOLO files alone.",
            "An official split is not automatically site-, camera-, vehicle-, and date-separated.",
            "Exact sequence evaluation requires independently verified full-plate text and character grouping.",
        ],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--compare-filename-truth", action="store_true")
    args = parser.parse_args()
    report = audit(args.dataset, compare_filename_truth=args.compare_filename_truth)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    rendered = json.dumps(report, indent=2)
    args.output.write_text(rendered + "\n", encoding="utf-8")
    print(rendered)
    return 0 if report["character_detection_evaluation_eligible"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
