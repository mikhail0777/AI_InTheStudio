"""Combine frozen vehicle benchmarks without changing any source split.

The output keeps the older VMMR classes first so an existing 100-class model
can later be used as an initialization without changing its class indices.
No test image is moved into train or development.
"""
from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path


def _load(path: Path) -> tuple[dict, bytes]:
    raw = path.read_bytes()
    manifest = json.loads(raw)
    if manifest.get("purpose") != "frozen_research_benchmark":
        raise ValueError(f"Not a frozen research benchmark: {path}")
    return manifest, raw


def combine_manifests(
    legacy_manifest: Path,
    legacy_images: Path,
    modern_manifest: Path,
) -> dict:
    legacy, legacy_raw = _load(legacy_manifest)
    modern, modern_raw = _load(modern_manifest)
    legacy_images = legacy_images.resolve()

    classes: list[dict] = []
    class_maps: list[dict[int, int]] = []
    for manifest in (legacy, modern):
        mapping = {}
        for source in manifest["classes"]:
            new_id = len(classes)
            mapping[int(source["class_id"])] = new_id
            item = dict(source)
            item["class_id"] = new_id
            item["source_dataset"] = manifest["dataset"]["name"]
            classes.append(item)
        class_maps.append(mapping)

    samples: list[dict] = []
    for source_name, manifest, mapping in (
        ("legacy", legacy, class_maps[0]),
        ("modern", modern, class_maps[1]),
    ):
        for source in manifest["samples"]:
            item = dict(source)
            item["class_id"] = mapping[int(source["class_id"])]
            item["source_dataset"] = manifest["dataset"]["name"]
            if source_name == "legacy":
                path = (legacy_images / source["member"]).resolve()
                if legacy_images not in path.parents:
                    raise ValueError("Legacy manifest member escapes its image root")
                item["path"] = str(path)
            samples.append(item)

    counts = Counter(item["split"] for item in samples)
    return {
        "schema_version": 1,
        "purpose": "frozen_research_benchmark",
        "dataset": {
            "name": "VMMRdb 100-class plus DVM-Car late-2010s 40-class",
            "commercial_use_cleared": False,
            "final_benchmark": False,
            "limitation": (
                "Both image sources are restricted to research evaluation; DVM licensing "
                "metadata conflicts. Web/dealer photos do not certify dealership video."
            ),
        },
        "archive": {"path": legacy["archive"]["path"]},
        "sources": [
            {"manifest": str(legacy_manifest.resolve()), "sha256": hashlib.sha256(legacy_raw).hexdigest()},
            {"manifest": str(modern_manifest.resolve()), "sha256": hashlib.sha256(modern_raw).hexdigest()},
        ],
        "split_policy": {
            "method": "preserve_each_frozen_source_split_without_reassignment",
            "test_is_frozen_before_training": True,
        },
        "classes": classes,
        "samples": samples,
        "counts": {key: counts[key] for key in ("train", "development", "test")},
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("legacy_manifest", type=Path)
    parser.add_argument("legacy_images", type=Path)
    parser.add_argument("modern_manifest", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = combine_manifests(args.legacy_manifest, args.legacy_images, args.modern_manifest)
    payload = (json.dumps(result, indent=2) + "\n").encode()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(payload)
    args.output.with_suffix(args.output.suffix + ".sha256").write_text(
        hashlib.sha256(payload).hexdigest() + "\n", encoding="ascii"
    )
    print(json.dumps({"classes": len(result["classes"]), **result["counts"]}, indent=2))


if __name__ == "__main__":
    main()
