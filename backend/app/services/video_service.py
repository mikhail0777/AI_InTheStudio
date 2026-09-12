import os
import cv2
import time
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
        if not cap.isOpened():
            raise ValueError(f"Could not open video file or format unsupported: {filepath}")

        frame_count = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        fps = float(cap.get(cv2.CAP_PROP_FPS))
        width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        fourcc = int(cap.get(cv2.CAP_PROP_FOURCC))
        codec = "".join([chr((fourcc >> 8 * i) & 0xFF) for i in range(4)]).strip()

        duration = (frame_count / fps) if fps > 0 else 0.0
        cap.release()

        file_size_mb = round(os.path.getsize(filepath) / (1024 * 1024), 2)
        stat = os.stat(filepath)
        creation_time = datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%d %H:%M:%S")

        return VideoMetadata(
            filename=os.path.basename(filepath),
            filepath=filepath,
            duration_seconds=round(duration, 2),
            frame_count=frame_count,
            fps=round(fps, 2),
            width=width,
            height=height,
            codec=codec or "h264",
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
        if duration <= 0 or fps_sample <= 0:
            return [0.0]
        step = 1.0 / fps_sample
        timestamps = []
        t = 0.0
        while t <= duration:
            timestamps.append(round(t, 2))
            t += step
        return timestamps
