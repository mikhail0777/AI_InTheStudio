import os
import cv2
import time
import math
import numpy as np
from datetime import datetime
from typing import Dict, Any, List, Tuple, Optional
from app.models.schemas import VideoMetadata

class VideoService:
    @staticmethod
    def inspect_video(filepath: str) -> VideoMetadata:
        if not os.path.exists(filepath):
            raise FileNotFoundError(f"Video file not found: {filepath}")

        cap = cv2.VideoCapture(filepath)
        try:
            if not cap.isOpened():
                raise ValueError("Video cannot be decoded; check the file and codec.")
            values = [cap.get(prop) for prop in (cv2.CAP_PROP_FRAME_COUNT, cv2.CAP_PROP_FPS,
                       cv2.CAP_PROP_FRAME_WIDTH, cv2.CAP_PROP_FRAME_HEIGHT)]
            if any(not math.isfinite(value) or value <= 0 for value in values):
                raise ValueError("Video has invalid frame count, frame rate, or dimensions.")
            frame_count, fps, width, height = int(values[0]), float(values[1]), int(values[2]), int(values[3])
            ret, first_frame = cap.read()
            if not ret or first_frame is None or first_frame.size == 0:
                raise ValueError("Video contains no decodable frames.")
            fourcc = int(cap.get(cv2.CAP_PROP_FOURCC))
            codec = "".join([chr((fourcc >> 8 * i) & 0xFF) for i in range(4)]).strip()
            duration = frame_count / fps
        finally:
            cap.release()

        file_size_mb = round(os.path.getsize(filepath) / (1024 * 1024), 2)
        stat = os.stat(filepath)
        creation_time = datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%d %H:%M:%S")

        return VideoMetadata(
            filename=os.path.basename(filepath),
            filepath=filepath,
            duration_seconds=duration,
            frame_count=frame_count,
            fps=fps,
            width=width,
            height=height,
            codec=codec or "unknown",
            file_size_mb=file_size_mb,
            creation_timestamp=creation_time
        )

    @staticmethod
    def extract_frame_at_timestamp(video_path: str, timestamp_seconds: float) -> Optional[np.ndarray]:
        cap = cv2.VideoCapture(video_path)
        if not cap.isOpened():
            return None
        fps = cap.get(cv2.CAP_PROP_FPS)
        target_frame = int(timestamp_seconds * fps)
        cap.set(cv2.CAP_PROP_POS_FRAMES, target_frame)
        ret, frame = cap.read()
        cap.release()
        return frame if ret else None

    @staticmethod
    def get_sample_timestamps(duration: float, fps_sample: float) -> List[float]:
        if not math.isfinite(duration) or not math.isfinite(fps_sample) or duration <= 0 or fps_sample <= 0:
            return []
        # The end of a video is exclusive; do not request a nonexistent final frame.
        return [index / fps_sample for index in range(math.ceil(duration * fps_sample))
                if index / fps_sample < duration]

    @staticmethod
    def sample_frame_indices(video: VideoMetadata, sample_fps: float, start: float = 0.0,
                             end: Optional[float] = None) -> List[int]:
        end = min(video.duration_seconds, end if end is not None else video.duration_seconds)
        start = max(0.0, start)
        return sorted({min(video.frame_count - 1, int((start + offset) * video.fps))
                       for offset in VideoService.get_sample_timestamps(max(0.0, end - start), sample_fps)
                       if 0 <= int((start + offset) * video.fps) < video.frame_count})
