import math
from typing import List, Dict, Any, Tuple, Optional
from app.models.schemas import DetectionItem

class TrackState:
    def __init__(self, track_id: int, initial_detection: DetectionItem):
        self.track_id = track_id
        self.detections: List[DetectionItem] = [initial_detection]
        self.last_seen_seconds = initial_detection.timestamp_seconds
        self.first_seen_seconds = initial_detection.timestamp_seconds
        self.last_bbox = initial_detection.bbox  # [x1, y1, x2, y2]
        self.velocity = [0.0, 0.0]  # center dx, dy per second

    def update(self, det: DetectionItem):
        dt = max(0.01, det.timestamp_seconds - self.last_seen_seconds)
        old_center = [(self.last_bbox[0] + self.last_bbox[2])/2.0, (self.last_bbox[1] + self.last_bbox[3])/2.0]
        new_center = [(det.bbox[0] + det.bbox[2])/2.0, (det.bbox[1] + det.bbox[3])/2.0]

        dx = (new_center[0] - old_center[0]) / dt
        dy = (new_center[1] - old_center[1]) / dt
        self.velocity = [0.7 * self.velocity[0] + 0.3 * dx, 0.7 * self.velocity[1] + 0.3 * dy]

        self.last_seen_seconds = det.timestamp_seconds
        self.last_bbox = det.bbox
        self.detections.append(det)

    def predict_center_at(self, timestamp_seconds: float) -> Tuple[float, float]:
        dt = timestamp_seconds - self.last_seen_seconds
        cx = (self.last_bbox[0] + self.last_bbox[2]) / 2.0
        cy = (self.last_bbox[1] + self.last_bbox[3]) / 2.0
        return (cx + self.velocity[0] * dt, cy + self.velocity[1] * dt)

def compute_iou(boxA: List[float], boxB: List[float]) -> float:
    xA = max(boxA[0], boxB[0])
    yA = max(boxA[1], boxB[1])
    xB = min(boxA[2], boxB[2])
    yB = min(boxA[3], boxB[3])

    interArea = max(0, xB - xA) * max(0, yB - yA)
    boxAArea = max(1e-5, (boxA[2] - boxA[0]) * (boxA[3] - boxA[0]))
    boxBArea = max(1e-5, (boxB[2] - boxB[0]) * (boxB[3] - boxB[0]))

    iou = interArea / float(boxAArea + boxBArea - interArea)
    return iou

class PersonTracker:
    def __init__(self, max_time_gap_seconds: float = 3.0, min_iou_threshold: float = 0.15):
        self.max_time_gap = max_time_gap_seconds
        self.min_iou = min_iou_threshold
        self.next_track_id = 1
        self.active_tracks: List[TrackState] = []
        self.completed_tracks: List[TrackState] = []

    def process_detections(self, frame_detections: List[DetectionItem]):
        if not frame_detections:
            return

        current_time = frame_detections[0].timestamp_seconds

        # Match detections to active tracks
        unmatched_dets = list(frame_detections)
        matches: List[Tuple[TrackState, DetectionItem]] = []

        for track in self.active_tracks:
            # Check time gap
            if (current_time - track.last_seen_seconds) > self.max_time_gap:
                continue

            pred_cx, pred_cy = track.predict_center_at(current_time)
            tw = track.last_bbox[2] - track.last_bbox[0]
            th = track.last_bbox[3] - track.last_bbox[1]
            predicted_box = [pred_cx - tw/2.0, pred_cy - th/2.0, pred_cx + tw/2.0, pred_cy + th/2.0]

            best_match_det = None
            best_score = -1.0

            for det in unmatched_dets:
                iou = compute_iou(predicted_box, det.bbox)
                # Also check center distance
                det_cx = (det.bbox[0] + det.bbox[2]) / 2.0
                det_cy = (det.bbox[1] + det.bbox[3]) / 2.0
                dist = math.hypot(det_cx - pred_cx, det_cy - pred_cy)
                diag = math.hypot(tw, th)
                dist_score = max(0.0, 1.0 - dist / max(50.0, 3.0 * diag))

                score = 0.7 * iou + 0.3 * dist_score
                if score > best_score and (iou >= self.min_iou or dist_score >= 0.6):
                    best_score = score
                    best_match_det = det

            if best_match_det is not None:
                matches.append((track, best_match_det))
                unmatched_dets.remove(best_match_det)

        # Update matched tracks
        for track, det in matches:
            track.update(det)

        # Create new tracks for unmatched detections
        for det in unmatched_dets:
            new_track = TrackState(self.next_track_id, det)
            self.next_track_id += 1
            self.active_tracks.append(new_track)

    def finalize(self) -> List[TrackState]:
        return self.active_tracks + self.completed_tracks
