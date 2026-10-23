"""Audit OCR manifests for label validity, provenance, and split leakage.

Input is JSON containing ``records``.  The tool does not move, relabel, or
delete data.  It exits non-zero when train/validation/final-test isolation is
violated by an exact image, near-duplicate image, plate identity, vehicle,
recording, camera/site/date group, or event.
"""
from __future__ import annotations

import argparse
from collections import defaultdict
import json
from pathlib import Path
import re
from typing import Iterable


VALID_SPLITS = {"train", "validation", "development_regression", "final_test"}
GROUP_FIELDS = (
    "image_sha256", "plate_identity", "vehicle_id", "recording_id",
    "event_id", "camera_date_group", "site_date_group",
)
REQUIRED_PROVENANCE = ("source", "license", "checksum", "label_type", "usage_restrictions")


def hamming_distance(left: str, right: str) -> int:
    if len(left) != len(right) or not re.fullmatch(r"[0-9a-fA-F]+", left + right):
        raise ValueError("Perceptual hashes must be equal-length hexadecimal strings")
    return (int(left, 16) ^ int(right, 16)).bit_count()


def _cross_split_groups(records: list[dict], field: str) -> list[dict]:
    groups: dict[str, dict[str, list[str]]] = defaultdict(lambda: defaultdict(list))
    for record in records:
        value = record.get(field)
        if value not in (None, ""):
            groups[str(value)][record["split"]].append(str(record.get("id") or record.get("file") or ""))
    return [
        {"field": field, "value": value, "splits": dict(sorted(splits.items()))}
        for value, splits in sorted(groups.items()) if len(splits) > 1
    ]


def audit_records(records: Iterable[dict], *, near_duplicate_distance: int = 4) -> dict:
    rows = [dict(record) for record in records]
    invalid = []
    for index, record in enumerate(rows):
        record_id = str(record.get("id") or record.get("file") or index)
        missing = [field for field in REQUIRED_PROVENANCE if not record.get(field)]
        if record.get("split") not in VALID_SPLITS:
            missing.append("valid_split")
        transcription = str(record.get("transcription") or "")
        if record.get("label_type") == "full_plate_transcription":
            if not re.fullmatch(r"[A-Z0-9]{2,10}", transcription.upper()):
                missing.append("valid_full_plate_transcription")
        if "*" in transcription:
            missing.append("unmasked_full_plate_truth")
        if missing:
            invalid.append({"id": record_id, "problems": sorted(set(missing))})

    leakage = []
    for field in GROUP_FIELDS:
        leakage.extend(_cross_split_groups(rows, field))

    hashes = [
        (str(row.get("id") or row.get("file") or index), row["split"], str(row["perceptual_hash"]))
        for index, row in enumerate(rows) if row.get("perceptual_hash")
    ]
    near_duplicates = []
    for left_index, (left_id, left_split, left_hash) in enumerate(hashes):
        for right_id, right_split, right_hash in hashes[left_index + 1:]:
            if left_split == right_split or len(left_hash) != len(right_hash):
                continue
            distance = hamming_distance(left_hash, right_hash)
            if distance <= near_duplicate_distance:
                near_duplicates.append({
                    "left_id": left_id, "left_split": left_split,
                    "right_id": right_id, "right_split": right_split,
                    "hamming_distance": distance,
                })
    leakage.extend({"field": "near_duplicate", **item} for item in near_duplicates)
    return {
        "schema_version": 1,
        "records": len(rows),
        "invalid_records": invalid,
        "leakage": leakage,
        "near_duplicate_distance": near_duplicate_distance,
        "passes": not invalid and not leakage,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--near-duplicate-distance", type=int, default=4)
    args = parser.parse_args()
    source = json.loads(args.manifest.read_text(encoding="utf-8"))
    report = audit_records(source.get("records", []), near_duplicate_distance=args.near_duplicate_distance)
    report["manifest"] = str(args.manifest.resolve())
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({key: report[key] for key in ("records", "passes")}, indent=2))
    return 0 if report["passes"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
