"""Export excluded OCR samples into a human-review queue without changing originals."""
from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.prepare_consensus_ocr_dataset import link_or_copy


REVIEW_REASONS = {
    "label_and_filename_do_not_agree",
    "ambiguous_multiple_rows",
    "character_count_is_not_seven",
}


def export_queue(source: Path, manifest_path: Path, destination: Path) -> dict:
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if destination.exists() and any(destination.iterdir()):
        raise FileExistsError(f"Destination must be empty or absent: {destination}")
    images_dir = destination / "images"
    images_dir.mkdir(parents=True, exist_ok=True)
    rows: list[dict[str, str]] = []
    modes: set[str] = set()
    for record in manifest["records"]:
        if record.get("status") != "excluded" or record.get("reason") not in REVIEW_REASONS:
            continue
        split = record["split"]
        filename = record["file"]
        original = source / split / "images" / filename
        review_name = f"{split}__{filename}"
        modes.add(link_or_copy(original, images_dir / review_name))
        rows.append({
            "review_file": review_name,
            "source_split": split,
            "source_file": filename,
            "exclusion_reason": record["reason"],
            "filename_candidates": "|".join(record.get("filename_candidates") or []),
            "box_label_sequence": record.get("label_sequence") or "",
            "human_verified_sequence": "",
            "decision": "pending",
            "reviewer": "",
            "reviewed_at": "",
            "notes": "",
        })
    fieldnames = list(rows[0]) if rows else [
        "review_file", "source_split", "source_file", "exclusion_reason",
        "filename_candidates", "box_label_sequence", "human_verified_sequence",
        "decision", "reviewer", "reviewed_at", "notes",
    ]
    with (destination / "review_queue.csv").open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
    summary = {
        "schema_version": 1,
        "source": str(source.resolve()),
        "derivation_manifest": str(manifest_path.resolve()),
        "review_items": len(rows),
        "materialization": sorted(modes),
        "policy": "Only an independent human may fill human_verified_sequence and reviewer fields.",
    }
    (destination / "queue_manifest.json").write_text(
        json.dumps(summary, indent=2) + "\n", encoding="utf-8",
    )
    return summary


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", required=True, type=Path)
    parser.add_argument("--manifest", required=True, type=Path)
    parser.add_argument("--destination", required=True, type=Path)
    args = parser.parse_args()
    print(json.dumps(export_queue(args.source, args.manifest, args.destination), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
