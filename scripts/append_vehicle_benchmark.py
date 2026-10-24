"""Append a reviewed vehicle benchmark without changing existing class IDs."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


def ranges_overlap(left: dict, right: dict) -> bool:
    return max(int(left["year_start"]), int(right["year_start"])) <= min(
        int(left["year_end"]), int(right["year_end"])
    )


def merge(base: dict, addon: dict) -> dict:
    if base.get("purpose") != "frozen_research_benchmark":
        raise ValueError("Base manifest must be a frozen research benchmark")
    if addon.get("purpose") != "frozen_commercially_reusable_vehicle_benchmark":
        raise ValueError("Add-on manifest must be a frozen reviewed Commons benchmark")
    base_classes = [dict(item) for item in base.get("classes", [])]
    addon_classes = addon.get("classes", [])
    for candidate in addon_classes:
        for existing in base_classes:
            same_name = (
                existing["make"].strip().casefold() == candidate["make"].strip().casefold()
                and existing["model"].strip().casefold() == candidate["model"].strip().casefold()
            )
            if same_name and ranges_overlap(existing, candidate):
                raise ValueError(
                    f"Overlapping year labels for {candidate['make']} {candidate['model']}: "
                    f"{existing['year_start']}-{existing['year_end']} and "
                    f"{candidate['year_start']}-{candidate['year_end']}"
                )

    class_offset = len(base_classes)
    addon_id_map: dict[int, int] = {}
    classes = base_classes
    for item in addon_classes:
        source_id = int(item["class_id"])
        class_id = class_offset + len(addon_id_map)
        addon_id_map[source_id] = class_id
        value = dict(item)
        value["source_class_id"] = source_id
        value["class_id"] = class_id
        value["source_dataset"] = "Wikimedia Commons reviewed current-generation vehicles"
        classes.append(value)

    samples = [dict(item) for item in base.get("samples", [])]
    for item in addon.get("samples", []):
        value = dict(item)
        if item.get("class_id") is not None:
            value["source_class_id"] = int(item["class_id"])
            value["class_id"] = addon_id_map[int(item["class_id"])]
        value["source_dataset"] = "Wikimedia Commons reviewed current-generation vehicles"
        samples.append(value)

    split_names = sorted({item["split"] for item in samples})
    counts = {name: sum(item["split"] == name for item in samples) for name in split_names}
    counts["classes"] = len(classes)
    return {
        "schema_version": 1,
        "purpose": "frozen_research_benchmark",
        "dataset": {
            "name": f"{base['dataset']['name']} plus reviewed current-generation Commons images",
            "commercial_use_cleared": False,
            "final_benchmark": False,
            "limitation": (
                "The combined benchmark inherits source restrictions. Commons files require "
                "per-file attribution/share-alike compliance. Still photographs do not certify "
                "dealership-video performance."
            ),
        },
        "archive": base["archive"],
        "sources": list(base.get("sources", [])),
        "split_policy": {
            "method": "preserve_each_frozen_source_split_without_reassignment",
            "test_is_frozen_before_training": True,
            "unknown_classes_never_used_for_classifier_training": True,
        },
        "classes": classes,
        "samples": samples,
        "counts": counts,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("base", type=Path)
    parser.add_argument("addon", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    base_raw, addon_raw = args.base.read_bytes(), args.addon.read_bytes()
    result = merge(json.loads(base_raw), json.loads(addon_raw))
    result["sources"].append({
        "manifest": str(args.addon.resolve()),
        "sha256": hashlib.sha256(addon_raw).hexdigest(),
    })
    payload = (json.dumps(result, indent=2) + "\n").encode()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(payload)
    args.output.with_suffix(args.output.suffix + ".sha256").write_text(
        hashlib.sha256(payload).hexdigest() + "\n", encoding="ascii"
    )
    print(json.dumps(result["counts"], indent=2))


if __name__ == "__main__":
    main()
