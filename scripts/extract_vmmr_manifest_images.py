"""Extract only images referenced by a frozen VMMR manifest."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import shutil
from zipfile import ZipFile


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("manifest", type=Path)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
    root = args.output_dir.resolve()
    root.mkdir(parents=True, exist_ok=True)
    members = sorted({item["member"] for item in manifest.get("samples") or []})
    extracted = 0
    with ZipFile(manifest["archive"]["path"]) as source:
        available = set(source.namelist())
        for member in members:
            if member not in available:
                raise SystemExit(f"Manifest member is missing from archive: {member}")
            destination = (root / member).resolve()
            if root not in destination.parents:
                raise SystemExit(f"Unsafe archive member: {member}")
            destination.parent.mkdir(parents=True, exist_ok=True)
            if not destination.exists():
                with source.open(member) as input_file, destination.open("xb") as output_file:
                    shutil.copyfileobj(input_file, output_file)
            extracted += 1
            if extracted % 1000 == 0:
                print(f"Extracted {extracted}/{len(members)}", flush=True)
    print(json.dumps({"images": extracted, "output_dir": str(root)}, indent=2))


if __name__ == "__main__":
    main()
