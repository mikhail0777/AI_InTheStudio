"""Run the real plate model on a labelled clip and print reproducible metrics."""
from __future__ import annotations

import argparse
from collections import Counter
import json
from pathlib import Path
import sys
import time

import cv2

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.services.license_plate_reader import LicensePlateReader, normalize_plate, plate_similarity


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--video", required=True)
    parser.add_argument("--plate", required=True)
    parser.add_argument("--fps", type=float, default=4.0)
    parser.add_argument("--no-tiles", action="store_true")
    args = parser.parse_args()
    target = normalize_plate(args.plate)
    path = Path(args.video)
    cap = cv2.VideoCapture(str(path))
    source_fps = cap.get(cv2.CAP_PROP_FPS)
    frame_count = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    if not cap.isOpened() or source_fps <= 0 or frame_count <= 0:
        raise SystemExit(f"Could not open a valid video: {path}")
    interval = max(1, round(source_fps / args.fps))
    indices = list(range(0, frame_count, interval))
    reader = LicensePlateReader()
    readings: list[dict] = []
    sampled = 0
    started = time.perf_counter()
    for frame_idx in indices:
        cap.set(cv2.CAP_PROP_POS_FRAMES, frame_idx)
        ok, frame = cap.read()
        if not ok:
            continue
        sampled += 1
        for result in reader.read_frame(frame, tiled=not args.no_tiles):
            text = normalize_plate(result.text)
            readings.append({
                "frame": frame_idx, "seconds": round(frame_idx / source_fps, 3),
                "text": text, "confidence": round(result.confidence, 4),
                "similarity": round(plate_similarity(text, target), 4),
            })
    cap.release()
    exact = [item for item in readings if item["text"] == target]
    frames_with_reads = {item["frame"] for item in readings}
    exact_frames = {item["frame"] for item in exact}
    report = {
        "video": str(path), "ground_truth_plate": target,
        "duration_seconds": round(frame_count / source_fps, 3),
        "sample_fps": args.fps, "sampled_frames": sampled,
        "frames_with_any_plate_read": len(frames_with_reads),
        "frames_with_exact_plate_read": len(exact_frames),
        "clip_level_exact_match": bool(exact),
        "exact_rate_among_frames_with_reads": round(len(exact_frames) / len(frames_with_reads), 4) if frames_with_reads else 0.0,
        "first_exact_seconds": min((item["seconds"] for item in exact), default=None),
        "top_ocr_readings": Counter(item["text"] for item in readings).most_common(10),
        "elapsed_seconds": round(time.perf_counter() - started, 3),
        "model": reader.provenance.model_dump(mode="json"),
    }
    print(json.dumps(report, indent=2))
    return 0 if exact else 1


if __name__ == "__main__":
    raise SystemExit(main())
