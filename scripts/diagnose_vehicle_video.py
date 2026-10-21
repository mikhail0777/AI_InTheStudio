"""Run the production coarse vehicle detector over sampled video frames."""
from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import tempfile
import time

import cv2
from ultralytics import YOLO


VEHICLE_NAMES = {"car", "truck", "bus", "motorcycle"}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("video")
    parser.add_argument("--fps", type=float, default=1.0)
    parser.add_argument("--model", default=str(Path(__file__).resolve().parents[1] / "backend" / "models" / "yolo11s-seg.pt"))
    args = parser.parse_args()
    path, model_path = Path(args.video).resolve(), Path(args.model).resolve()
    cap = cv2.VideoCapture(str(path))
    source_fps, frames = cap.get(cv2.CAP_PROP_FPS), int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    if not cap.isOpened() or source_fps <= 0 or frames <= 0:
        raise SystemExit(f"Could not open a valid video: {path}")
    interval = max(1, round(source_fps / args.fps))
    indices = list(range(0, frames, interval))
    model = YOLO(str(model_path))
    names = {int(key): str(value).lower() for key, value in model.names.items()}
    class_ids = [key for key, value in names.items() if value in VEHICLE_NAMES]
    detected_frames, detections, categories = 0, 0, Counter()
    started = time.perf_counter()
    with tempfile.TemporaryDirectory() as root:
        root = Path(root)
        for start in range(0, len(indices), 8):
            paths = []
            for frame_idx in indices[start:start + 8]:
                cap.set(cv2.CAP_PROP_POS_FRAMES, frame_idx)
                ok, frame = cap.read()
                if not ok:
                    continue
                frame_path = root / f"{frame_idx:09d}.jpg"
                cv2.imwrite(str(frame_path), frame)
                paths.append(frame_path)
            results = model.predict([str(item) for item in paths], classes=class_ids, conf=.25,
                                    iou=.5, imgsz=1280, verbose=False, save=False, device="cpu")
            for result in results:
                found = []
                for box in result.boxes:
                    category = names[int(box.cls.item())]
                    categories[category] += 1
                    found.append(category)
                detected_frames += int(bool(found))
                detections += len(found)
    cap.release()
    elapsed = time.perf_counter() - started
    report = {
        "video": str(path), "duration_seconds": round(frames / source_fps, 3),
        "sample_fps": args.fps, "sampled_frames": len(indices),
        "frames_with_vehicle": detected_frames, "vehicle_detections": detections,
        "frame_detection_coverage": round(detected_frames / len(indices), 4) if indices else 0.0,
        "categories": dict(categories), "elapsed_seconds": round(elapsed, 3),
        "model": {"provider": "ultralytics", "model_name": model_path.name,
                  "model_version": hashlib.sha256(model_path.read_bytes()).hexdigest(), "device": "cpu"},
        "limitation": "No frame-level vehicle boxes are labelled in this video; this is functional coverage, not accuracy."
    }
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
