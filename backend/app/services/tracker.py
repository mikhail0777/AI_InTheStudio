"""Conservative within-recording association; track IDs are not identities."""
import math
from typing import List, Optional
from app.models.schemas import DetectionItem


def compute_iou(a: List[float], b: List[float]) -> float:
    area_a = max(0.0, a[2] - a[0]) * max(0.0, a[3] - a[1])
    area_b = max(0.0, b[2] - b[0]) * max(0.0, b[3] - b[1])
    intersection = max(0.0, min(a[2], b[2]) - max(a[0], b[0])) * max(0.0, min(a[3], b[3]) - max(a[1], b[1]))
    union = area_a + area_b - intersection
    return intersection / union if union > 0 else 0.0


class TrackState:
    def __init__(self, track_id: int, initial_detection: DetectionItem):
        self.track_id = track_id
        self.detections = [initial_detection]
        self.last_seen_seconds = initial_detection.timestamp_seconds
        self.first_seen_seconds = initial_detection.timestamp_seconds
        self.last_bbox = initial_detection.bbox
        self.velocity = [0.0, 0.0]

    def predict_center_at(self, timestamp_seconds):
        dt = max(0.0, timestamp_seconds - self.last_seen_seconds)
        return tuple((self.last_bbox[i] + self.last_bbox[i + 2]) / 2 + self.velocity[i] * dt for i in (0, 1))

    def update(self, detection):
        dt = detection.timestamp_seconds - self.last_seen_seconds
        if dt <= 0:
            return
        for i in (0, 1):
            shift = (detection.bbox[i] + detection.bbox[i + 2] - self.last_bbox[i] - self.last_bbox[i + 2]) / 2
            self.velocity[i] = .5 * self.velocity[i] + .5 * shift / dt
        self.last_bbox = detection.bbox
        self.last_seen_seconds = detection.timestamp_seconds
        self.detections.append(detection)


class PersonTracker:
    def __init__(self, max_time_gap_seconds=3.0, min_iou_threshold=.15):
        self.max_time_gap = max_time_gap_seconds
        self.min_iou = min_iou_threshold
        self.next_track_id = 1
        self.active_tracks = []
        self.completed_tracks = []

    def process_detections(self, frame_detections: List[DetectionItem], timestamp_seconds: Optional[float] = None):
        now = timestamp_seconds if timestamp_seconds is not None else (frame_detections[0].timestamp_seconds if frame_detections else None)
        if now is None:
            return
        expired = [t for t in self.active_tracks if now - t.last_seen_seconds > self.max_time_gap]
        self.completed_tracks.extend(expired)
        self.active_tracks = [t for t in self.active_tracks if t not in expired]
        pairs = []
        for ti, track in enumerate(self.active_tracks):
            if now <= track.last_seen_seconds:
                continue
            w, h = track.last_bbox[2] - track.last_bbox[0], track.last_bbox[3] - track.last_bbox[1]
            cx, cy = track.predict_center_at(now)
            predicted = [cx - w / 2, cy - h / 2, cx + w / 2, cy + h / 2]
            for di, det in enumerate(frame_detections):
                dw, dh = det.bbox[2] - det.bbox[0], det.bbox[3] - det.bbox[1]
                area_ratio = dw * dh / max(1.0, w * h)
                if not .3 <= area_ratio <= 3.3:
                    continue
                iou = compute_iou(predicted, det.bbox)
                distance = math.hypot((det.bbox[0] + det.bbox[2]) / 2 - cx, (det.bbox[1] + det.bbox[3]) / 2 - cy)
                normalized = distance / max(1.0, math.hypot(w, h))
                if iou >= self.min_iou or normalized < .35:
                    pairs.append((.8 * iou + .2 * max(0, 1 - normalized), ti, di))
        used_tracks, used_detections = set(), set()
        for _, ti, di in sorted(pairs, reverse=True):
            if ti not in used_tracks and di not in used_detections:
                self.active_tracks[ti].update(frame_detections[di])
                used_tracks.add(ti)
                used_detections.add(di)
        for di, det in enumerate(frame_detections):
            if di not in used_detections:
                if any(d.frame_idx == det.frame_idx and compute_iou(d.bbox, det.bbox) > .8 for t in self.active_tracks for d in t.detections[-1:]):
                    continue
                self.active_tracks.append(TrackState(self.next_track_id, det))
                self.next_track_id += 1

    def finalize(self):
        return sorted(self.completed_tracks + self.active_tracks, key=lambda t: t.track_id)
