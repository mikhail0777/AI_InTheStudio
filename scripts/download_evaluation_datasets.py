"""Download and verify the official UC3M-LP and COCO 2017 validation datasets."""
from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import shutil
import sys
import threading
import urllib.request
import zipfile


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_ROOT = ROOT / "evaluation" / "datasets"
DATASETS = {
    "uc3m": [
        {
            "name": "UC3M-LP.zip",
            "url": "https://zenodo.org/records/17152029/files/UC3M-LP.zip?download=1",
            "md5": "496e3b5e66b78d231f71d85c0e5e11a3",
            "version": "Zenodo record 17152029",
            "license": "ODbL-1.0",
        },
    ],
    "coco": [
        {
            "name": "val2017.zip",
            "url": "http://images.cocodataset.org/zips/val2017.zip",
            "version": "COCO 2017 validation images",
            "license": "Image-specific Flickr terms; see COCO terms of use",
        },
        {
            "name": "annotations_trainval2017.zip",
            "url": "http://images.cocodataset.org/annotations/annotations_trainval2017.zip",
            "version": "COCO 2017 train/validation annotations",
            "license": "CC BY 4.0 annotations",
        },
    ],
}


def digest(path: Path, algorithm: str = "sha256") -> str:
    hasher = hashlib.new(algorithm)
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(8 * 1024 * 1024), b""):
            hasher.update(block)
    return hasher.hexdigest()


def remote_size(url: str) -> int:
    request = urllib.request.Request(
        url, headers={"User-Agent": "LotTrace-Evaluation/1.0", "Range": "bytes=0-0"},
    )
    with urllib.request.urlopen(request, timeout=120) as response:
        content_range = response.headers.get("Content-Range", "")
        if "/" in content_range:
            return int(content_range.rsplit("/", 1)[1])
        return int(response.headers["Content-Length"])


def download(url: str, destination: Path, workers: int = 1) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    partial = destination.with_suffix(destination.suffix + ".part")
    existing = partial.stat().st_size if partial.exists() else 0
    if workers > 1:
        total = remote_size(url)
        if existing >= total:
            partial.replace(destination)
            return
        remaining = total - existing
        chunk_size = (remaining + workers - 1) // workers
        ranges = []
        for index in range(workers):
            start = existing + index * chunk_size
            end = min(total - 1, start + chunk_size - 1)
            if start <= end:
                ranges.append((index, start, end))
        progress_lock = threading.Lock()
        downloaded = [sum((partial.with_suffix(partial.suffix + f".seg{index:02d}").stat().st_size
                           if partial.with_suffix(partial.suffix + f".seg{index:02d}").exists() else 0)
                          for index, _, _ in ranges)]

        def fetch_segment(segment: tuple[int, int, int]) -> Path:
            index, start, end = segment
            segment_path = partial.with_suffix(partial.suffix + f".seg{index:02d}")
            offset = segment_path.stat().st_size if segment_path.exists() else 0
            requested_start = start + offset
            if requested_start > end:
                return segment_path
            request = urllib.request.Request(
                url,
                headers={
                    "User-Agent": "LotTrace-Evaluation/1.0",
                    "Range": f"bytes={requested_start}-{end}",
                },
            )
            with urllib.request.urlopen(request, timeout=120) as response:
                if getattr(response, "status", 200) != 206:
                    raise RuntimeError("Dataset host did not honor a ranged download request.")
                with segment_path.open("ab") as output:
                    while True:
                        block = response.read(8 * 1024 * 1024)
                        if not block:
                            break
                        output.write(block)
                        with progress_lock:
                            downloaded[0] += len(block)
                            complete = existing + downloaded[0]
                            print(f"{destination.name}: {complete / 1024**3:.2f} / "
                                  f"{total / 1024**3:.2f} GiB", file=sys.stderr, flush=True)
            expected = end - start + 1
            if segment_path.stat().st_size != expected:
                raise RuntimeError(f"Incomplete range for {segment_path.name}")
            return segment_path

        with ThreadPoolExecutor(max_workers=workers) as executor:
            segments = list(executor.map(fetch_segment, ranges))
        assembled = destination.with_suffix(destination.suffix + ".assembled")
        with assembled.open("wb") as output:
            if partial.exists():
                with partial.open("rb") as source:
                    shutil.copyfileobj(source, output, 8 * 1024 * 1024)
            for segment in segments:
                with segment.open("rb") as source:
                    shutil.copyfileobj(source, output, 8 * 1024 * 1024)
        if assembled.stat().st_size != total:
            raise RuntimeError(f"Assembled size mismatch for {destination.name}")
        assembled.replace(destination)
        partial.unlink(missing_ok=True)
        for segment in segments:
            segment.unlink(missing_ok=True)
        return
    request = urllib.request.Request(url, headers={"User-Agent": "LotTrace-Evaluation/1.0"})
    if existing:
        request.add_header("Range", f"bytes={existing}-")
    with urllib.request.urlopen(request, timeout=120) as response:
        status = getattr(response, "status", 200)
        mode = "ab" if existing and status == 206 else "wb"
        if mode == "wb":
            existing = 0
        expected = int(response.headers.get("Content-Length", "0")) + existing
        received = existing
        with partial.open(mode) as output:
            while True:
                block = response.read(8 * 1024 * 1024)
                if not block:
                    break
                output.write(block)
                received += len(block)
                print(f"{destination.name}: {received / 1024**3:.2f} / "
                      f"{expected / 1024**3:.2f} GiB", file=sys.stderr, flush=True)
    partial.replace(destination)


def safe_extract(archive: Path, destination: Path) -> None:
    destination.mkdir(parents=True, exist_ok=True)
    root = destination.resolve()
    with zipfile.ZipFile(archive) as bundle:
        for member in bundle.infolist():
            target = (destination / member.filename).resolve()
            if root not in target.parents and target != root:
                raise ValueError(f"Unsafe archive member: {member.filename}")
        bundle.extractall(destination)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("dataset", choices=["uc3m", "coco", "all"])
    parser.add_argument("--root", type=Path, default=DEFAULT_ROOT)
    parser.add_argument("--no-extract", action="store_true")
    parser.add_argument("--workers", type=int, default=4)
    args = parser.parse_args()
    selected = DATASETS if args.dataset == "all" else {args.dataset: DATASETS[args.dataset]}
    args.root.mkdir(parents=True, exist_ok=True)
    manifest_path = args.root / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8")) if manifest_path.exists() else {}
    for dataset_name, assets in selected.items():
        dataset_root = args.root / dataset_name
        archives = args.root / "archives"
        records = []
        for asset in assets:
            archive = archives / asset["name"]
            if not archive.exists():
                download(asset["url"], archive, max(1, args.workers))
            if asset.get("md5") and digest(archive, "md5") != asset["md5"]:
                raise SystemExit(f"MD5 mismatch for {archive}")
            record = {
                **asset,
                "bytes": archive.stat().st_size,
                "sha256": digest(archive),
                "downloaded_at": datetime.now(timezone.utc).isoformat(),
            }
            records.append(record)
            if not args.no_extract:
                safe_extract(archive, dataset_root)
        manifest[dataset_name] = {"assets": records, "root": str(dataset_root.resolve())}
        manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(manifest_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
