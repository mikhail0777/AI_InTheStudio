"""Create a development-only VMMRdb manifest without extracting the archive."""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import hashlib
import json
from pathlib import Path
from zipfile import ZipFile

try:
    from scripts.audit_vmmr_archive import IMAGE_SUFFIXES, parse_class_label
except ModuleNotFoundError:  # Direct ``python scripts/...`` execution.
    from audit_vmmr_archive import IMAGE_SUFFIXES, parse_class_label


def _split(member: str, development_fraction: float) -> str:
    value = int.from_bytes(hashlib.sha256(member.encode("utf-8")).digest()[:8], "big") / 2**64
    return "development" if value < development_fraction else "train"


def prepare_manifest(
    archive: Path, *, minimum_images: int = 20, maximum_classes: int | None = None,
    maximum_images_per_class: int | None = None,
    development_fraction: float = .15, archive_sha256: str | None = None,
) -> dict:
    if minimum_images < 2:
        raise ValueError("minimum_images must be at least 2.")
    if not 0 < development_fraction < .5:
        raise ValueError("development_fraction must be between 0 and 0.5.")
    if maximum_images_per_class is not None and maximum_images_per_class < 2:
        raise ValueError("maximum_images_per_class must be at least 2.")
    by_label = defaultdict(list)
    with ZipFile(archive) as source:
        for item in source.infolist():
            if item.is_dir() or Path(item.filename).suffix.lower() not in IMAGE_SUFFIXES:
                continue
            parts = Path(item.filename).parts
            if len(parts) < 2:
                continue
            parsed = parse_class_label(parts[0])
            if not parsed["make"] or not parsed["model"]:
                continue
            by_label[(parsed["make"], parsed["model"])].append((item.filename, parsed))
    eligible = [(key, values) for key, values in by_label.items() if len(values) >= minimum_images]
    eligible.sort(key=lambda item: (-len(item[1]), item[0]))
    if maximum_classes is not None:
        if maximum_classes < 2:
            raise ValueError("maximum_classes must be at least 2.")
        eligible = eligible[:maximum_classes]
    classes, samples = [], []
    for class_id, ((make, model), values) in enumerate(eligible):
        values = sorted(values, key=lambda item: item[0])
        if maximum_images_per_class is not None:
            values = values[:maximum_images_per_class]
        years = sorted({item[1]["year_start"] for item in values if item[1]["year_start"]})
        classes.append({
            "class_id": class_id, "make": make, "model": model,
            "year_start": min(years) if years else None,
            "year_end": max(years) if years else None,
            "image_count": len(values),
        })
        for member, parsed in values:
            samples.append({
                "member": member, "class_id": class_id,
                "source_folder": parsed["folder"], "source_year": parsed["year_start"],
                "split": _split(member, development_fraction),
            })
    split_counts = Counter(item["split"] for item in samples)
    return {
        "schema_version": 1,
        "purpose": "research_development_only",
        "archive": {"path": str(Path(archive).resolve()), "sha256": archive_sha256},
        "dataset": {
            "name": "VMMRdb", "commercial_use_cleared": False,
            "final_benchmark": False,
            "limitation": "No vehicle/site/camera/date grouping; split is unsuitable for final accuracy claims.",
        },
        "split_policy": {
            "method": "deterministic_member_name_hash",
            "development_fraction": development_fraction,
            "contains_final_split": False,
        },
        "minimum_images_per_make_model": minimum_images,
        "classes": classes,
        "samples": samples,
        "counts": {"classes": len(classes), "samples": len(samples), **split_counts},
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("archive", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--minimum-images", type=int, default=20)
    parser.add_argument("--maximum-classes", type=int)
    parser.add_argument("--maximum-images-per-class", type=int)
    parser.add_argument("--development-fraction", type=float, default=.15)
    parser.add_argument("--archive-sha256")
    args = parser.parse_args()
    manifest = prepare_manifest(
        args.archive, minimum_images=args.minimum_images,
        maximum_classes=args.maximum_classes,
        maximum_images_per_class=args.maximum_images_per_class,
        development_fraction=args.development_fraction,
        archive_sha256=args.archive_sha256,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(manifest["counts"], indent=2))


if __name__ == "__main__":
    main()
