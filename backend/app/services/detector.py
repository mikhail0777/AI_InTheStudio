import os
import cv2
import numpy as np
import uuid
from typing import List, Dict, Any, Tuple, Optional
from app.models.schemas import DetectionItem

class PersonDetector:
    def __init__(self, crop_dir: str):
        self.crop_dir = crop_dir
        os.makedirs(self.crop_dir, exist_ok=True)
        self.yolo_model = None
        self._init_yolo()

    def _init_yolo(self):
        try:
            from ultralytics import YOLO
            # Load nano model (downloads automatically if not cached)
            self.yolo_model = YOLO("yolo11n.pt")
            print("[Detector] Ultralytics YOLO11n initialized successfully.")
        except Exception as e:
            try:
                from ultralytics import YOLO
                self.yolo_model = YOLO("yolov8n.pt")
                print("[Detector] Ultralytics YOLOv8n initialized successfully.")
            except Exception as e2:
                print(f"[Detector] YOLO init notice: {e2}. Using fallback color/motion/HOG person detector.")
                self.yolo_model = None

    def estimate_crop_quality(self, crop: np.ndarray) -> float:
        if crop is None or crop.size == 0:
            return 0.0
        h, w = crop.shape[:2]
        size_score = min(1.0, (h * w) / (120 * 60))  # ideal min crop ~60x120

        # Blur estimation via Laplacian variance
        gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)
        lap_var = cv2.Laplacian(gray, cv2.CV_64F).var()
        blur_score = min(1.0, lap_var / 150.0)

        # Aspect ratio score (human aspect ratio ~ 1.5 - 3.0 height/width)
        ar = h / max(1.0, float(w))
        ar_score = 1.0 if 1.2 <= ar <= 4.0 else 0.5

        quality = 0.4 * size_score + 0.4 * blur_score + 0.2 * ar_score
        return float(round(quality, 2))

    def detect_in_frame(
        self,
        frame: np.ndarray,
        session_id: str,
        frame_idx: int,
        timestamp_seconds: float,
        min_confidence: float = 0.35,
        crop_margin: float = 0.15
    ) -> List[DetectionItem]:
        detections: List[DetectionItem] = []
        if frame is None or frame.size == 0:
            return detections

        img_h, img_w = frame.shape[:2]
        boxes_conf: List[Tuple[List[float], float]] = []

        if self.yolo_model is not None:
            try:
                results = self.yolo_model(frame, verbose=False, classes=[0], conf=0.20)  # class 0 = person
                for r in results:
                    for box in r.boxes:
                        conf = float(box.conf[0].cpu().numpy())
                        if conf >= min_confidence:
                            xyxy = box.xyxy[0].cpu().numpy().tolist()
                            boxes_conf.append((xyxy, conf))
            except Exception as ex:
                print(f"[Detector] YOLO detection fallback trigger: {ex}")
                boxes_conf = self._fallback_detect(frame, min_confidence)

        if not boxes_conf:
            boxes_conf = self._fallback_detect(frame, min_confidence)

        # Save crops and build DetectionItem list
        session_crop_dir = os.path.join(self.crop_dir, session_id)
        os.makedirs(session_crop_dir, exist_ok=True)

        for (x1, y1, x2, y2), conf in boxes_conf:
            # Apply margin
            bw = x2 - x1
            bh = y2 - y1
            mx1 = max(0, int(x1 - bw * crop_margin))
            my1 = max(0, int(y1 - bh * crop_margin))
            mx2 = min(img_w, int(x2 + bw * crop_margin))
            my2 = min(img_h, int(y2 + bh * crop_margin))

            crop = frame[my1:my2, mx1:mx2]
            det_id = f"det_{session_id}_{frame_idx}_{uuid.uuid4().hex[:6]}"
            crop_rel_path = f"/crops/{session_id}/{det_id}.jpg"
            crop_full_path = os.path.join(session_crop_dir, f"{det_id}.jpg")

            if crop.size > 0:
                cv2.imwrite(crop_full_path, crop)
                quality = self.estimate_crop_quality(crop)
            else:
                quality = 0.1
                crop_rel_path = ""

            detections.append(
                DetectionItem(
                    detection_id=det_id,
                    frame_idx=frame_idx,
                    timestamp_seconds=timestamp_seconds,
                    bbox=[round(x1, 1), round(y1, 1), round(x2, 1), round(y2, 1)],
                    confidence=round(conf, 2),
                    crop_path=crop_rel_path,
                    quality_score=quality
                )
            )

        return detections

    def _fallback_detect(self, frame: np.ndarray, min_confidence: float) -> List[Tuple[List[float], float]]:
        """
        Robust OpenCV fallback person detection for synthetic demo or offline mode.
        Detects distinct human-like objects/blobs or uses HOG descriptor.
        """
        boxes_conf = []
        h, w = frame.shape[:2]

        # Use HOG descriptor
        hog = cv2.HOGDescriptor()
        hog.setSVMDetector(cv2.HOGDescriptor_getDefaultPeopleDetector())
        rects, weights = hog.detectMultiScale(frame, winStride=(8, 8), padding=(4, 4), scale=1.05)

        for (x, y, bw, bh), wgt in zip(rects, weights):
            conf = min(0.95, float(wgt) / 2.5 + 0.4)
            if conf >= min_confidence:
                boxes_conf.append(([float(x), float(y), float(x + bw), float(y + bh)], conf))

        # Removed color blob detection fallback to prevent tracking inanimate objects (blue bins, etc)
        return boxes_conf
