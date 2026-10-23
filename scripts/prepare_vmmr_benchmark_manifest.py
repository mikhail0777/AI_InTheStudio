"""Freeze a research-only VMMR make/model/year-range benchmark manifest.

The split is deterministic and stratified by visual label. It is useful for
repeatable development measurement, but VMMRdb has no vehicle/site/camera/date
identity, so this is not a production dealership-video benchmark.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
from zipfile import ZipFile

try:
    from scripts.audit_vmmr_archive import IMAGE_SUFFIXES, parse_class_label
except ModuleNotFoundError:
    from audit_vmmr_archive import IMAGE_SUFFIXES, parse_class_label


def _hash_fraction(value: str) -> float:
    return int.from_bytes(hashlib.sha256(value.encode("utf-8")).digest()[:8], "big") / 2**64


def _year_bucket(year: int, size: int) -> tuple[int, int]:
    start = year - year % size
    return start, start + size - 1


def prepare_benchmark_manifest(
    archive: Path, *, archive_sha256: str, minimum_images: int = 45,
    maximum_classes: int = 100, maximum_images_per_class: int = 120,
    development_fraction: float = .15, test_fraction: float = .15,
    year_range_size: int = 3,
) -> dict:
    if minimum_images < 10:
        raise ValueError("minimum_images must be at least 10.")
    if maximum_classes < 2 or maximum_images_per_class < minimum_images:
        raise ValueError("Class and sample limits are inconsistent.")
    if development_fraction <= 0 or test_fraction <= 0 or development_fraction + test_fraction >= .5:
        raise ValueError("Development and test fractions must be positive and total less than 0.5.")
    if year_range_size < 1 or year_range_size > 10:
        raise ValueError("year_range_size must be between 1 and 10.")

    grouped = defaultdict(list)
    with ZipFile(archive) as source:
        for item in source.infolist():
            if item.is_dir() or Path(item.filename).suffix.lower() not in IMAGE_SUFFIXES:
                continue
            parts = Path(item.filename).parts
            if len(parts) < 2:
                continue
            parsed = parse_class_label(parts[0])
            year = parsed.get("year_start")
            if not parsed.get("make") or not parsed.get("model") or year is None:
                continue
            year_start, year_end = _year_bucket(int(year), year_range_size)
            grouped[(parsed["make"], parsed["model"], year_start, year_end)].append(
                {"member": item.filename, "source_folder": parsed["folder"], "source_year": int(year)}
            )

    eligible = [(key, rows) for key, rows in grouped.items() if len(rows) >= minimum_images]
    eligible.sort(key=lambda item: (-len(item[1]), item[0]))
    eligible = eligible[:maximum_classes]
    classes, samples = [], []
    for class_id, ((make, model, year_start, year_end), rows) in enumerate(eligible):
        rows = sorted(rows, key=lambda row: hashlib.sha256(row["member"].encode("utf-8")).hexdigest())
        rows = rows[:maximum_images_per_class]
        classes.append({
            "class_id": class_id, "make": make, "model": model,
            "year_start": year_start, "year_end": year_end,
            "image_count": len(rows),
        })
        for row in rows:
            fraction = _hash_fraction("split:" + row["member"])
            split = ("test" if fraction < test_fraction else
                     "development" if fraction < test_fraction + development_fraction else "train")
            samples.append({**row, "class_id": class_id, "split": split})

    counts = Counter(row["split"] for row in samples)
    if len(classes) < 2 or any(counts[name] == 0 for name in ("train", "development", "test")):
        raise ValueError("The selected data did not produce usable train/development/test splits.")
    return {
        "schema_version": 1,
        "purpose": "frozen_research_benchmark",
        "frozen_at": datetime.now(timezone.utc).isoformat(),
        "archive": {"path": str(Path(archive).resolve()), "sha256": archive_sha256},
        "dataset": {
            "name": "VMMRdb", "commercial_use_cleared": False,
            "final_benchmark": False,
            "limitation": (
                "Research-only image rights; no vehicle/site/camera/date grouping. "
                "The frozen test split is repeatable but cannot certify production performance."
            ),
        },
        "label_policy": {
            "task": "make_model_year_range", "year_range_size": year_range_size,
            "unknown_is_required_outside_supported_classes": True,
        },
        "split_policy": {
            "method": "deterministic_member_hash_stratified_by_label",
            "development_fraction": development_fraction, "test_fraction": test_fraction,
            "test_is_frozen_before_training": True,
            "vehicle_identity_grouping_available": False,
        },
        "classes": classes, "samples": samples,
        "counts": {"classes": len(classes), "samples": len(samples), **counts},
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("archive", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--archive-sha256", required=True)
    parser.add_argument("--minimum-images", type=int, default=45)
    parser.add_argument("--maximum-classes", type=int, default=100)
    parser.add_argument("--maximum-images-per-class", type=int, default=120)
    parser.add_argument("--development-fraction", type=float, default=.15)
    parser.add_argument("--test-fraction", type=float, default=.15)
    parser.add_argument("--year-range-size", type=int, default=3)
    args = parser.parse_args()
    manifest = prepare_benchmark_manifest(
        args.archive, archive_sha256=args.archive_sha256,
        minimum_images=args.minimum_images, maximum_classes=args.maximum_classes,
        maximum_images_per_class=args.maximum_images_per_class,
        development_fraction=args.development_fraction, test_fraction=args.test_fraction,
        year_range_size=args.year_range_size,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(manifest, indent=2) + "\n"
    # Write exact UTF-8 bytes so the published checksum is identical on
    # Windows and POSIX rather than changing with newline translation.
    args.output.write_bytes(payload.encode("utf-8"))
    digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()
    args.output.with_suffix(args.output.suffix + ".sha256").write_text(
        f"{digest}  {args.output.name}\n", encoding="utf-8",
    )
    print(json.dumps({**manifest["counts"], "manifest_sha256": digest}, indent=2))


if __name__ == "__main__":
    main()
