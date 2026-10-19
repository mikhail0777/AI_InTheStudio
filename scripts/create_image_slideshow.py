"""Create a fixed-duration MP4 slideshow from an ordered list of images."""
from __future__ import annotations

import argparse
from pathlib import Path

import cv2
import numpy as np


def fit_on_canvas(image: np.ndarray, width: int, height: int) -> np.ndarray:
    source_height, source_width = image.shape[:2]
    scale = min(width / source_width, height / source_height)
    resized = cv2.resize(
        image,
        (max(1, round(source_width * scale)), max(1, round(source_height * scale))),
        interpolation=cv2.INTER_LANCZOS4 if scale > 1 else cv2.INTER_AREA,
    )
    canvas = np.full((height, width, 3), (28, 22, 16), dtype=np.uint8)
    x = (width - resized.shape[1]) // 2
    y = (height - resized.shape[0]) // 2
    canvas[y:y + resized.shape[0], x:x + resized.shape[1]] = resized
    return canvas


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("images", nargs="+", help="Images in display order")
    parser.add_argument("--output", required=True, help="Output MP4 path")
    parser.add_argument("--seconds", type=float, default=3.0, help="Seconds per image")
    parser.add_argument("--fps", type=int, default=30)
    parser.add_argument("--width", type=int, default=1280)
    parser.add_argument("--height", type=int, default=720)
    args = parser.parse_args()
    if args.seconds <= 0 or args.fps <= 0 or args.width <= 0 or args.height <= 0:
        raise SystemExit("Duration, frame rate, width, and height must be positive.")

    frames_per_image = round(args.seconds * args.fps)
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    writer = cv2.VideoWriter(
        str(output), cv2.VideoWriter_fourcc(*"mp4v"), args.fps, (args.width, args.height)
    )
    if not writer.isOpened():
        raise SystemExit("OpenCV could not initialize the MP4 writer.")
    try:
        for value in args.images:
            path = Path(value)
            image = cv2.imread(str(path))
            if image is None or image.size == 0:
                raise SystemExit(f"Could not read image: {path}")
            frame = fit_on_canvas(image, args.width, args.height)
            for _ in range(frames_per_image):
                writer.write(frame)
    finally:
        writer.release()
    print(f"Created {output} ({len(args.images)} images, {len(args.images) * args.seconds:.3f}s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
