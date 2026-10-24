"""Mark an existing fine-grained label manifest for grouped make/model output."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("source", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    raw = args.source.read_bytes()
    manifest = json.loads(raw)
    if not manifest.get("classes"):
        raise SystemExit("Source label manifest has no classes")
    manifest["prediction_task"] = "grouped_make_model"
    manifest["source_label_manifest_sha256"] = hashlib.sha256(raw).hexdigest()
    manifest["year_output_policy"] = "omitted_from_visual_prediction"
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
