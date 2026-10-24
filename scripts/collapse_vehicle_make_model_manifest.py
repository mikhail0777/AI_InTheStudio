"""Collapse frozen make/model/year classes into make/model-only classes."""
from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path

try:
    from scripts.evaluate_grouped_vehicle_make_model import normalized_key
except ModuleNotFoundError:
    from evaluate_grouped_vehicle_make_model import normalized_key


def collapse(manifest: dict) -> dict:
    if manifest.get("purpose") != "frozen_research_benchmark":
        raise ValueError("Input must be a frozen research benchmark")
    key_to_id: dict[tuple[str, str], int] = {}
    classes: list[dict] = []
    source_to_group: dict[int, int] = {}
    for source in manifest["classes"]:
        key = normalized_key(source)
        if key not in key_to_id:
            group_id = len(classes)
            key_to_id[key] = group_id
            classes.append({
                "class_id": group_id,
                "make": source["make"],
                "model": source["model"],
                "source_class_ids": [],
            })
        group_id = key_to_id[key]
        source_to_group[int(source["class_id"])] = group_id
        classes[group_id]["source_class_ids"].append(int(source["class_id"]))

    samples = []
    for source in manifest["samples"]:
        item = dict(source)
        item["source_class_id"] = int(source["class_id"])
        item["class_id"] = source_to_group[int(source["class_id"])]
        samples.append(item)
    counts = Counter(item["split"] for item in samples)
    return {
        "schema_version": 1,
        "purpose": "frozen_research_benchmark",
        "prediction_task": "vehicle_make_model",
        "dataset": {
            **manifest["dataset"],
            "name": manifest["dataset"]["name"] + " collapsed to make/model",
        },
        "archive": manifest["archive"],
        "sources": manifest.get("sources", []),
        "split_policy": {
            **manifest.get("split_policy", {}),
            "class_mapping": "normalized_make_model_without_year",
            "source_splits_preserved": True,
        },
        "classes": classes,
        "samples": samples,
        "counts": {"classes": len(classes), **dict(counts)},
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("manifest", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    raw = args.manifest.read_bytes()
    result = collapse(json.loads(raw))
    result["source_manifest_sha256"] = hashlib.sha256(raw).hexdigest()
    payload = (json.dumps(result, indent=2) + "\n").encode()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(payload)
    args.output.with_suffix(args.output.suffix + ".sha256").write_text(
        hashlib.sha256(payload).hexdigest() + "\n", encoding="ascii"
    )
    print(json.dumps(result["counts"], indent=2))


if __name__ == "__main__":
    main()
