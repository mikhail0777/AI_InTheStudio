"""Audit a VMMRdb ZIP without extracting or silently declaring it production-safe."""
from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import re
from zipfile import ZipFile


IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png", ".webp"}
PUBLISHED_IMAGES = 291_752
PUBLISHED_CLASSES = 9_170
MULTIWORD_MAKES = (
    "alfa romeo", "aston martin", "land rover", "mercedes benz", "rolls royce",
)


def parse_class_label(folder: str) -> dict:
    normalized = re.sub(r"\s+", " ", folder.replace("_", " ")).strip()
    match = re.search(r"(?:^|\s)((?:19|20)\d{2})$", normalized)
    year = int(match.group(1)) if match else None
    name = normalized[:match.start()].strip() if match else normalized
    lowered = name.casefold()
    make = next((value for value in MULTIWORD_MAKES if lowered.startswith(value + " ")), None)
    if make is None:
        make = name.split(" ", 1)[0] if name else ""
    model = name[len(make):].strip() if make else name
    return {
        "folder": folder, "make": make.title(), "model": model,
        "year_start": year, "year_end": year,
    }


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        while chunk := source.read(8 * 1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def audit_archive(path: Path, *, include_sha256=False) -> dict:
    path = path.resolve()
    counts = Counter()
    invalid_root_images = []
    duplicate_names = []
    seen = set()
    with ZipFile(path) as archive:
        for item in archive.infolist():
            if item.is_dir() or Path(item.filename).suffix.lower() not in IMAGE_SUFFIXES:
                continue
            parts = Path(item.filename).parts
            if len(parts) < 2:
                invalid_root_images.append(item.filename)
                continue
            folder = parts[0]
            counts[folder] += 1
            folded = item.filename.casefold()
            if folded in seen:
                duplicate_names.append(item.filename)
            seen.add(folded)
    labels = [parse_class_label(folder) for folder in sorted(counts)]
    years = [item["year_start"] for item in labels if item["year_start"]]
    makes = Counter(item["make"] for item in labels if item["make"])
    image_total = sum(counts.values())
    warnings = []
    if image_total != PUBLISHED_IMAGES:
        warnings.append(
            f"Archive contains {image_total} images, not the publisher's stated {PUBLISHED_IMAGES}."
        )
    if len(counts) != PUBLISHED_CLASSES:
        warnings.append(
            f"Archive contains {len(counts)} classes, not the publisher's stated {PUBLISHED_CLASSES}."
        )
    if any(value < 2 for value in counts.values()):
        warnings.append("At least one class has fewer than two images and cannot support an independent split.")
    warnings.extend([
        "Folder labels do not identify vehicle identity, camera, site, or capture date; leakage-safe final splitting is not proven.",
        "Repository MIT wording does not establish ownership of the crawled third-party sale images; commercial training use is not cleared.",
        "The archive has no declared coverage after 2017, so recent dealership inventory is unsupported.",
    ])
    return {
        "schema_version": 1,
        "archive": {
            "path": str(path), "bytes": path.stat().st_size,
            "sha256": sha256_file(path) if include_sha256 else None,
        },
        "source": {
            "name": "VMMRdb", "repository": "https://github.com/faezetta/VMMRdb",
            "paper": "A Large and Diverse Dataset for Improved Vehicle Make and Model Recognition (CVPR Workshops 2017)",
            "repository_license": "MIT",
            "image_origin": "Publisher reports crawling vehicle-sale pages, mainly Craigslist and Amazon.",
            "commercial_use_cleared": False,
            "permitted_role": "research/prototyping pending documented image rights",
        },
        "inventory": {
            "images": image_total, "classes": len(counts), "parsed_makes": len(makes),
            "earliest_year": min(years) if years else None,
            "latest_year": max(years) if years else None,
            "minimum_images_per_class": min(counts.values()) if counts else 0,
            "maximum_images_per_class": max(counts.values()) if counts else 0,
            "classes_with_fewer_than_2_images": sum(value < 2 for value in counts.values()),
            "classes_with_fewer_than_5_images": sum(value < 5 for value in counts.values()),
            "classes_with_at_least_20_images": sum(value >= 20 for value in counts.values()),
            "duplicate_archive_names_case_insensitive": len(duplicate_names),
            "images_outside_class_folders": len(invalid_root_images),
        },
        "largest_makes_by_class_count": [
            {"make": make, "classes": count} for make, count in makes.most_common(20)
        ],
        "class_manifest": [
            {**label, "image_count": counts[label["folder"]]} for label in labels
        ],
        "split_readiness": {
            "frozen": False,
            "vehicle_identity_groups_available": False,
            "camera_site_date_groups_available": False,
            "eligible_as_final_dealership_benchmark": False,
        },
        "warnings": warnings,
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("archive", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--sha256", action="store_true")
    args = parser.parse_args()
    report = audit_archive(args.archive, include_sha256=args.sha256)
    rendered = json.dumps(report, indent=2)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered + "\n", encoding="utf-8")
    print(json.dumps({
        "archive": report["archive"], "inventory": report["inventory"],
        "split_readiness": report["split_readiness"], "warnings": report["warnings"],
    }, indent=2))


if __name__ == "__main__":
    main()
