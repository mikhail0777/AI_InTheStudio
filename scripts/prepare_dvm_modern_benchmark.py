"""Build a quality-gated late-2010s DVM-Car benchmark without listing leakage."""
from __future__ import annotations

import argparse
from collections import defaultdict
import hashlib
import json
from pathlib import Path, PurePosixPath
from zipfile import ZipFile

import cv2
import numpy as np


def parse_member(member: str) -> dict:
    parts = PurePosixPath(member).stem.split("$$")
    if len(parts) != 7:
        raise ValueError(f"Unexpected DVM member name: {member}")
    make, model, year, colour, view, listing_id, image_id = parts
    return {
        "make": make.strip(), "model": model.strip(), "year": int(year),
        "colour": colour.strip(), "view": view, "listing_id": listing_id,
        "image_id": image_id,
    }


def dhash(image: np.ndarray) -> str:
    gray = cv2.cvtColor(cv2.resize(image, (9, 8)), cv2.COLOR_BGR2GRAY)
    bits = gray[:, 1:] > gray[:, :-1]
    return f"{sum(int(bit) << index for index, bit in enumerate(bits.flat)):016x}"


def split_for(group: str, seed: str) -> str:
    value = int(hashlib.sha256(f"{seed}|{group}".encode()).hexdigest()[:8], 16) / 0xFFFFFFFF
    return "test" if value < .15 else "development" if value < .30 else "train"


def file_md5(path: Path) -> str:
    digest = hashlib.md5()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("archive", type=Path)
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--class-count", type=int, default=40)
    parser.add_argument("--max-per-class", type=int, default=120)
    parser.add_argument("--year-start", type=int, default=2016)
    parser.add_argument("--year-end", type=int, default=2018)
    parser.add_argument("--seed", default="lottrace-dvm-2026-10-23")
    parser.add_argument("--min-sharpness", type=float, default=35.0)
    args = parser.parse_args()

    args.output_root.mkdir(parents=True, exist_ok=True)
    image_root = args.output_root / "images"
    image_root.mkdir(exist_ok=True)
    archive_md5 = file_md5(args.archive)
    if archive_md5 != "c103301f316fe9e59d1b3621c644a88c":
        raise SystemExit(f"Unexpected DVM archive MD5: {archive_md5}")

    grouped: dict[tuple[str, str], dict[str, list[str]]] = defaultdict(lambda: defaultdict(list))
    with ZipFile(args.archive) as source:
        for member in source.namelist():
            if member.endswith("/"):
                continue
            label = parse_member(member)
            if args.year_start <= label["year"] <= args.year_end:
                grouped[(label["make"], label["model"])][label["listing_id"]].append(member)

    selected_classes = sorted(
        grouped,
        key=lambda key: (-len(grouped[key]), key[0].casefold(), key[1].casefold()),
    )[:args.class_count]
    classes = [{
        "class_id": index, "make": make, "model": model,
        "year_start": args.year_start, "year_end": args.year_end,
        "available_listing_groups": len(grouped[(make, model)]),
    } for index, (make, model) in enumerate(selected_classes)]

    samples, rejected = [], []
    seen_sha256, seen_dhash = set(), set()
    with ZipFile(args.archive) as source:
        for class_row in classes:
            key = (class_row["make"], class_row["model"])
            candidates = []
            for listing_id, members in grouped[key].items():
                member = min(members, key=lambda value: hashlib.sha256(f"{args.seed}|{value}".encode()).hexdigest())
                candidates.append((listing_id, member))
            candidates.sort(key=lambda value: hashlib.sha256(f"{args.seed}|{key}|{value[0]}".encode()).hexdigest())
            accepted = 0
            for listing_id, member in candidates:
                payload = source.read(member)
                digest = hashlib.sha256(payload).hexdigest()
                image = cv2.imdecode(np.frombuffer(payload, np.uint8), cv2.IMREAD_COLOR)
                if image is None or image.size == 0:
                    rejected.append({"member": member, "reason": "decode_failed"}); continue
                gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
                quality = {
                    "width": image.shape[1], "height": image.shape[0],
                    "sharpness": round(float(cv2.Laplacian(gray, cv2.CV_64F).var()), 3),
                    "mean_luma": round(float(gray.mean()), 3),
                    "luma_stddev": round(float(gray.std()), 3), "dhash": dhash(image),
                }
                if min(image.shape[:2]) < 224 or quality["sharpness"] < args.min_sharpness or quality["luma_stddev"] < 20 or not 20 <= quality["mean_luma"] <= 235:
                    rejected.append({"member": member, "reason": "quality", "quality": quality}); continue
                if digest in seen_sha256 or quality["dhash"] in seen_dhash:
                    rejected.append({"member": member, "reason": "duplicate", "quality": quality}); continue
                sample_id = hashlib.sha256(f"dvm:{member}".encode()).hexdigest()[:20]
                output_path = image_root / f"{sample_id}.jpg"
                if not cv2.imwrite(str(output_path), image, [cv2.IMWRITE_JPEG_QUALITY, 96]):
                    raise OSError(f"Could not write {output_path}")
                parsed = parse_member(member)
                samples.append({
                    "sample_id": sample_id, "path": str(output_path.resolve()),
                    "source_member": member, "source_sha256": digest,
                    "source_year": parsed["year"], "source_colour": parsed["colour"],
                    "listing_group": listing_id, "class_id": class_row["class_id"],
                    "split": split_for(f"{key[0]}|{key[1]}|{listing_id}", args.seed),
                    "quality": quality,
                })
                seen_sha256.add(digest); seen_dhash.add(quality["dhash"]); accepted += 1
                if accepted >= args.max_per_class:
                    break
            class_row["image_count"] = accepted
            if accepted < 60:
                raise SystemExit(f"Insufficient quality images for {key}: {accepted}")

    counts = {name: sum(sample["split"] == name for sample in samples) for name in ("train", "development", "test")}
    manifest = {
        "schema_version": 1,
        "purpose": "frozen_research_benchmark",
        "dataset": {
            "name": "DVM-Car Confirmed Fronts late-2010s subset",
            "source_url": "https://deepvisualmarketing.github.io/",
            "figshare_url": "https://figshare.com/articles/figure/DVM-CAR_Dataset/19586296/1",
            "commercial_use_cleared": False,
            "final_benchmark": False,
            "limitation": "DVM site restricts use to non-commercial research; Figshare metadata says CC BY 4.0. Rights conflict requires resolution before production.",
        },
        "archive": {"path": str(args.archive.resolve()), "md5": archive_md5},
        "label_policy": {"task": "make_model_year_range", "year_start": args.year_start, "year_end": args.year_end},
        "split_policy": {
            "method": "deterministic_hash_grouped_by_make_model_and_listing_id",
            "train_fraction": .70, "development_fraction": .15, "test_fraction": .15,
            "one_image_per_listing": True, "test_is_frozen_before_training": True,
        },
        "quality_policy": {
            "publisher_confirmed_front_views": True, "minimum_dimension": 224,
            "minimum_sharpness": args.min_sharpness, "minimum_luma_stddev": 20,
            "accepted_luma_range": [20, 235], "exact_sha256_deduplication": True,
            "exact_dhash_deduplication": True, "anonymous_output_filenames": True,
        },
        "classes": classes, "samples": samples, "rejected": rejected,
        "counts": {"classes": len(classes), "samples": len(samples), **counts, "rejected": len(rejected)},
    }
    manifest_path = args.output_root / "manifest.json"
    payload = (json.dumps(manifest, indent=2) + "\n").encode()
    manifest_path.write_bytes(payload)
    (args.output_root / "manifest.sha256").write_text(hashlib.sha256(payload).hexdigest() + "\n", encoding="ascii")
    print(json.dumps(manifest["counts"], indent=2))
    print(f"manifest_sha256={hashlib.sha256(payload).hexdigest()}")


if __name__ == "__main__":
    main()
