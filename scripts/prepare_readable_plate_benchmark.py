"""Prepare and freeze a blinded, human-transcribed plate OCR benchmark.

The preparation step uses *ground-truth* YOLO plate boxes, never detector or
OCR predictions.  It writes anonymous crops plus a blank review CSV.  The
freeze step validates the completed human review and creates a checksummed
manifest that downstream evaluation can consume.
"""
from __future__ import annotations

import argparse
import csv
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import random
import re
from typing import Iterable

import cv2
import numpy as np


IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png", ".bmp", ".webp"}
READABILITY = {"readable", "challenging", "unreadable", "out_of_scope"}
PLATE_TEXT = re.compile(r"[A-Z0-9]{2,10}")


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def dhash(image: np.ndarray, hash_size: int = 8) -> str:
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY) if image.ndim == 3 else image
    resized = cv2.resize(gray, (hash_size + 1, hash_size), interpolation=cv2.INTER_AREA)
    bits = resized[:, 1:] > resized[:, :-1]
    value = 0
    for bit in bits.flatten():
        value = (value << 1) | int(bit)
    return f"{value:0{hash_size * hash_size // 4}x}"


def hamming(left: str, right: str) -> int:
    return (int(left, 16) ^ int(right, 16)).bit_count()


def yolo_boxes(path: Path, width: int, height: int) -> list[list[int]]:
    boxes: list[list[int]] = []
    for raw in path.read_text(encoding="utf-8").splitlines():
        fields = raw.split()
        if len(fields) != 5 or fields[0] != "0":
            continue
        center_x, center_y, box_width, box_height = map(float, fields[1:])
        x1 = round((center_x - box_width / 2) * width)
        y1 = round((center_y - box_height / 2) * height)
        x2 = round((center_x + box_width / 2) * width)
        y2 = round((center_y + box_height / 2) * height)
        boxes.append([max(0, x1), max(0, y1), min(width, x2), min(height, y2)])
    return boxes


def padded_crop(image: np.ndarray, box: list[int], padding: float) -> tuple[np.ndarray, list[int]]:
    height, width = image.shape[:2]
    x1, y1, x2, y2 = box
    pad_x = round((x2 - x1) * padding)
    pad_y = round((y2 - y1) * padding)
    padded = [max(0, x1 - pad_x), max(0, y1 - pad_y), min(width, x2 + pad_x), min(height, y2 + pad_y)]
    px1, py1, px2, py2 = padded
    return image[py1:py2, px1:px2].copy(), padded


def iter_reference_hashes(directories: Iterable[Path]) -> list[tuple[str, str]]:
    hashes: list[tuple[str, str]] = []
    for directory in directories:
        if not directory.exists():
            continue
        for path in sorted(directory.rglob("*")):
            if not path.is_file() or path.suffix.lower() not in IMAGE_SUFFIXES:
                continue
            image = cv2.imread(str(path))
            if image is not None and image.size:
                hashes.append((sha256_file(path), dhash(image)))
    return hashes


def collect_candidates(dataset: Path, min_short_side: int, padding: float) -> list[dict]:
    images_dir = dataset / "test" / "images"
    labels_dir = dataset / "test" / "labels"
    candidates: list[dict] = []
    for image_path in sorted(path for path in images_dir.iterdir() if path.suffix.lower() in IMAGE_SUFFIXES):
        label_path = labels_dir / f"{image_path.stem}.txt"
        if not label_path.exists():
            continue
        frame = cv2.imread(str(image_path))
        if frame is None or not frame.size:
            continue
        height, width = frame.shape[:2]
        for box_index, box in enumerate(yolo_boxes(label_path, width, height)):
            if min(box[2] - box[0], box[3] - box[1]) < min_short_side:
                continue
            crop, padded_box = padded_crop(frame, box, padding)
            if crop.size:
                candidates.append({
                    "source_path": image_path,
                    "source_sha256": sha256_file(image_path),
                    "source_box_index": box_index,
                    "ground_truth_box_xyxy": box,
                    "crop_box_xyxy": padded_box,
                    "crop": crop,
                    "crop_dhash": dhash(crop),
                    "crop_short_side": min(crop.shape[:2]),
                })
    return candidates


def select_candidates(
    candidates: list[dict], count: int, seed: int,
    reference_hashes: list[tuple[str, str]], near_duplicate_distance: int,
) -> tuple[list[dict], dict]:
    rng = random.Random(seed)
    shuffled = list(candidates)
    rng.shuffle(shuffled)
    selected: list[dict] = []
    rejected_reference = rejected_selected = 0
    for candidate in shuffled:
        encoded_ok, encoded = cv2.imencode(".png", candidate["crop"])
        if not encoded_ok:
            continue
        candidate["crop_sha256"] = sha256_bytes(encoded.tobytes())
        if any(
            candidate["crop_sha256"] == exact or
            hamming(candidate["crop_dhash"], perceptual) <= near_duplicate_distance
            for exact, perceptual in reference_hashes
        ):
            rejected_reference += 1
            continue
        if any(hamming(candidate["crop_dhash"], item["crop_dhash"]) <= near_duplicate_distance for item in selected):
            rejected_selected += 1
            continue
        selected.append(candidate)
        if len(selected) == count:
            break
    if len(selected) < count:
        raise ValueError(f"Only {len(selected)} eligible non-duplicate crops remain; requested {count}")
    return selected, {
        "candidate_pool": len(candidates),
        "rejected_against_reference": rejected_reference,
        "rejected_within_selection": rejected_selected,
    }


def write_contact_sheets(images_dir: Path, output_dir: Path, *, columns: int = 5, rows: int = 5) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    paths = sorted(images_dir.glob("plate_*.png"))
    cell_width, cell_height = 320, 160
    per_sheet = columns * rows
    for sheet_index in range(0, len(paths), per_sheet):
        canvas = np.full((rows * cell_height, columns * cell_width, 3), 245, dtype=np.uint8)
        for offset, path in enumerate(paths[sheet_index:sheet_index + per_sheet]):
            image = cv2.imread(str(path))
            if image is None:
                continue
            max_w, max_h = cell_width - 20, cell_height - 38
            scale = min(max_w / image.shape[1], max_h / image.shape[0])
            resized = cv2.resize(image, None, fx=scale, fy=scale, interpolation=cv2.INTER_CUBIC)
            row, column = divmod(offset, columns)
            x = column * cell_width + (cell_width - resized.shape[1]) // 2
            y = row * cell_height + 24 + (max_h - resized.shape[0]) // 2
            canvas[y:y + resized.shape[0], x:x + resized.shape[1]] = resized
            cv2.putText(canvas, path.stem, (column * cell_width + 8, row * cell_height + 18),
                        cv2.FONT_HERSHEY_SIMPLEX, .45, (20, 20, 20), 1, cv2.LINE_AA)
        cv2.imwrite(str(output_dir / f"sheet_{sheet_index // per_sheet + 1:02d}.jpg"), canvas)


def prepare(args: argparse.Namespace) -> dict:
    if args.output.exists() and any(args.output.iterdir()):
        raise FileExistsError(f"Output must be empty or absent: {args.output}")
    images_dir = args.output / "images"
    images_dir.mkdir(parents=True, exist_ok=True)
    references = iter_reference_hashes(args.exclude_images)
    candidates = collect_candidates(args.dataset, args.min_short_side, args.padding)
    selected, selection_stats = select_candidates(
        candidates, args.count, args.seed, references, args.near_duplicate_distance,
    )
    provenance_records = []
    review_rows = []
    for index, candidate in enumerate(selected, 1):
        sample_id = f"plate_{index:04d}"
        destination = images_dir / f"{sample_id}.png"
        if not cv2.imwrite(str(destination), candidate.pop("crop")):
            raise OSError(f"Could not write {destination}")
        candidate["crop_sha256"] = sha256_file(destination)
        provenance_records.append({
            "sample_id": sample_id,
            "source_file": str(candidate.pop("source_path").resolve()),
            **candidate,
        })
        review_rows.append({
            "sample_id": sample_id,
            "transcription": "",
            "readability": "",
            "vehicle_group_id": "",
            "reviewer": "",
            "notes": "",
        })
    with (args.output / "review.csv").open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(review_rows[0]))
        writer.writeheader()
        writer.writerows(review_rows)
    provenance = {
        "schema_version": 1,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "status": "candidate_human_review_required",
        "source_dataset": str(args.dataset.resolve()),
        "source_license": args.license,
        "selection": {
            "seed": args.seed, "requested": args.count,
            "min_ground_truth_box_short_side": args.min_short_side,
            "padding_fraction": args.padding,
            "near_duplicate_hamming_distance": args.near_duplicate_distance,
            "excluded_reference_directories": [str(path.resolve()) for path in args.exclude_images],
            "reference_images_hashed": len(references),
            **selection_stats,
        },
        "records": provenance_records,
    }
    (args.output / "private_provenance.json").write_text(json.dumps(provenance, indent=2) + "\n", encoding="utf-8")
    write_contact_sheets(images_dir, args.output / "contact_sheets")
    (args.output / "README.txt").write_text(
        "Blinded plate OCR benchmark review\n\n"
        "1. Review images or contact sheets without running OCR.\n"
        "2. Fill review.csv: transcription (A-Z/0-9), readability "
            "(readable/challenging/unreadable/out_of_scope), vehicle_group_id, reviewer, notes.\n"
        "3. Leave transcription blank for unreadable and out-of-scope images.\n"
        "4. Run this script with the freeze command only after every row is reviewed.\n",
        encoding="utf-8",
    )
    return provenance


def freeze(args: argparse.Namespace) -> dict:
    provenance_path = args.benchmark / "private_provenance.json"
    review_path = args.benchmark / "review.csv"
    provenance = json.loads(provenance_path.read_text(encoding="utf-8"))
    private_by_id = {row["sample_id"]: row for row in provenance["records"]}
    with review_path.open(encoding="utf-8-sig", newline="") as handle:
        reviews = list(csv.DictReader(handle))
    problems: list[str] = []
    records = []
    seen = set()
    for row_number, row in enumerate(reviews, 2):
        sample_id = (row.get("sample_id") or "").strip()
        readability = (row.get("readability") or "").strip().lower()
        transcription = re.sub(r"[^A-Z0-9]", "", (row.get("transcription") or "").upper())
        if sample_id not in private_by_id or sample_id in seen:
            problems.append(f"row {row_number}: unknown or duplicate sample_id {sample_id!r}")
            continue
        seen.add(sample_id)
        if readability not in READABILITY:
            problems.append(
                f"{sample_id}: readability must be readable, challenging, unreadable, or out_of_scope"
            )
        if readability in {"readable", "challenging"} and not PLATE_TEXT.fullmatch(transcription):
            problems.append(f"{sample_id}: readable/challenging rows require a 2-10 character transcription")
        if readability in {"unreadable", "out_of_scope"} and transcription:
            problems.append(f"{sample_id}: unreadable/out-of-scope rows must not contain transcription")
        image_path = args.benchmark / "images" / f"{sample_id}.png"
        if not image_path.is_file() or sha256_file(image_path) != private_by_id[sample_id]["crop_sha256"]:
            problems.append(f"{sample_id}: crop missing or changed after preparation")
        records.append({
            "sample_id": sample_id,
            "image": f"images/{sample_id}.png",
            "image_sha256": private_by_id[sample_id]["crop_sha256"],
            "transcription": transcription,
            "readability": readability,
            "vehicle_group_id": (row.get("vehicle_group_id") or "").strip() or sample_id,
            "reviewer": (row.get("reviewer") or "").strip(),
            "notes": (row.get("notes") or "").strip(),
        })
    missing = sorted(set(private_by_id) - seen)
    if missing:
        problems.append(f"review is missing {len(missing)} samples; first is {missing[0]}")
    if problems:
        raise ValueError("Cannot freeze benchmark:\n- " + "\n- ".join(problems[:25]))
    counts = {name: sum(row["readability"] == name for row in records) for name in sorted(READABILITY)}
    manifest = {
        "schema_version": 1,
        "frozen_at": datetime.now(timezone.utc).isoformat(),
        "status": "frozen_before_ocr_evaluation",
        "split": "final_test",
        "ground_truth_source": "manual human transcription completed while blinded to OCR predictions",
        "normal_readable_denominator": counts["readable"],
        "counts": counts,
        "records": records,
    }
    manifest_path = args.benchmark / "frozen_manifest.json"
    encoded = (json.dumps(manifest, indent=2) + "\n").encode("utf-8")
    manifest_path.write_bytes(encoded)
    (args.benchmark / "FROZEN.sha256").write_text(f"{sha256_bytes(encoded)}  frozen_manifest.json\n", encoding="ascii")
    return manifest


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    create = subparsers.add_parser("prepare", help="Create anonymous crops and blank review sheet")
    create.add_argument("--dataset", required=True, type=Path)
    create.add_argument("--output", required=True, type=Path)
    create.add_argument("--count", type=int, default=300)
    create.add_argument("--seed", type=int, default=20261022)
    create.add_argument("--min-short-side", type=int, default=30)
    create.add_argument("--padding", type=float, default=.08)
    create.add_argument("--near-duplicate-distance", type=int, default=1)
    create.add_argument("--exclude-images", action="append", type=Path, default=[])
    create.add_argument("--license", default="CC BY 4.0")
    finalize = subparsers.add_parser("freeze", help="Validate human review and freeze ground truth")
    finalize.add_argument("--benchmark", required=True, type=Path)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    result = prepare(args) if args.command == "prepare" else freeze(args)
    summary = result.get("selection") or result.get("counts")
    print(json.dumps({"status": result["status"], "summary": summary}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
