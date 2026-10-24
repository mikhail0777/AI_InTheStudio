"""Freeze a fully reviewed Commons vehicle benchmark without capture leakage."""
from __future__ import annotations

import argparse
from collections import defaultdict
import hashlib
import json
from pathlib import Path
import re


def conservative_capture_group(sample: dict) -> str:
    source = sample["source"]
    artist = re.sub(r"\W+", " ", source.get("artist") or "unknown").strip().casefold()
    captured = (source.get("date_time_original") or "").strip()
    if captured:
        basis = f"{artist}|{captured[:10]}"
    else:
        title = source.get("title") or str(source.get("page_id"))
        stem = re.sub(r"\.(?:jpe?g|png|webp|tiff?)$", "", title, flags=re.I)
        stem = re.sub(r"\b(?:front|rear|side|left|right|view|image|img|dsc|photo)\b", " ", stem, flags=re.I)
        stem = re.sub(r"[\W_]+|\d+", " ", stem).strip().casefold()
        basis = f"{artist}|{stem or source.get('page_id')}"
    return hashlib.sha256(basis.encode()).hexdigest()[:16]


def assign_supported_splits(samples: list[dict], seed: str) -> dict[str, str]:
    groups: dict[str, list[dict]] = defaultdict(list)
    for sample in samples:
        groups[conservative_capture_group(sample)].append(sample)
    ordered = sorted(groups, key=lambda group: hashlib.sha256(f"{seed}|{group}".encode()).hexdigest())
    target = max(1, round(len(samples) * .15))
    assignment, development, test = {}, 0, 0
    for group in ordered:
        size = len(groups[group])
        if test < target:
            split, test = "test", test + size
        elif development < target:
            split, development = "development", development + size
        else:
            split = "train"
        assignment[group] = split
    return assignment


def freeze(intake: dict, review: dict, seed: str) -> dict:
    verdicts = review.get("samples") or {}
    missing = sorted(sample["sample_id"] for sample in intake["samples"] if sample["sample_id"] not in verdicts)
    if missing:
        raise ValueError(f"Every intake sample requires review; missing {len(missing)} verdicts")
    accepted = [sample for sample in intake["samples"] if verdicts[sample["sample_id"]]["accepted"]]
    supported_source_ids = sorted({
        sample["class_id"] for sample in accepted if sample.get("role", "supported") == "supported"
    })
    class_map = {source_id: index for index, source_id in enumerate(supported_source_ids)}
    source_classes = {int(item["class_id"]): item for item in intake["classes"]}
    classes = []
    for source_id in supported_source_ids:
        item = dict(source_classes[source_id])
        item["source_class_id"] = source_id
        item["class_id"] = class_map[source_id]
        classes.append(item)

    samples = []
    for source_id in supported_source_ids:
        values = [item for item in accepted if item["class_id"] == source_id]
        assignment = assign_supported_splits(values, f"{seed}|{source_id}")
        for source in values:
            item = dict(source)
            item["source_class_id"] = source_id
            item["class_id"] = class_map[source_id]
            item["path"] = source["crop_path"]
            item["capture_group_v2"] = conservative_capture_group(source)
            item["split"] = assignment[item["capture_group_v2"]]
            item["review"] = verdicts[source["sample_id"]]
            samples.append(item)

    unknown = [item for item in accepted if item.get("role") == "unknown"]
    unknown_groups: dict[str, list[dict]] = defaultdict(list)
    for item in unknown:
        unknown_groups[conservative_capture_group(item)].append(item)
    for group in sorted(unknown_groups):
        value = int(hashlib.sha256(f"{seed}|unknown|{group}".encode()).hexdigest()[:8], 16)
        split = "unknown_development" if value % 2 == 0 else "unknown_test"
        for source in unknown_groups[group]:
            item = dict(source)
            item["class_id"] = None
            item["path"] = source["crop_path"]
            item["capture_group_v2"] = group
            item["split"] = split
            item["review"] = verdicts[source["sample_id"]]
            samples.append(item)

    counts = {name: sum(item["split"] == name for item in samples) for name in (
        "train", "development", "test", "unknown_development", "unknown_test"
    )}
    return {
        "schema_version": 1,
        "purpose": "frozen_commercially_reusable_vehicle_benchmark",
        "dataset": {
            "name": "Reviewed Wikimedia Commons current-generation vehicles",
            "commercial_use_cleared": "per_file_free_license_subject_to_attribution_and_sharealike_review",
            "final_benchmark": False,
            "limitation": "Still photographs do not certify dealership video; licence compliance remains per-file.",
        },
        "split_policy": {
            "method": "deterministic_capture_group_split_after_complete_human_review",
            "test_is_frozen_before_training": True,
            "unknown_classes_never_used_for_classifier_training": True,
        },
        "classes": classes,
        "samples": samples,
        "counts": {"classes": len(classes), "accepted": len(samples), **counts},
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("intake_manifest", type=Path)
    parser.add_argument("review", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--seed", default="lottrace-commons-2026-10-23")
    args = parser.parse_args()
    intake_raw, review_raw = args.intake_manifest.read_bytes(), args.review.read_bytes()
    result = freeze(json.loads(intake_raw), json.loads(review_raw), args.seed)
    result["intake_manifest_sha256"] = hashlib.sha256(intake_raw).hexdigest()
    result["review_sha256"] = hashlib.sha256(review_raw).hexdigest()
    payload = (json.dumps(result, indent=2) + "\n").encode()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(payload)
    args.output.with_suffix(args.output.suffix + ".sha256").write_text(
        hashlib.sha256(payload).hexdigest() + "\n", encoding="ascii"
    )
    print(json.dumps(result["counts"], indent=2))


if __name__ == "__main__":
    main()
