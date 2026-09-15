"""YOLO-only person/backpack segmentation with explicit model provenance."""
import hashlib
import os
import threading
import uuid
from pathlib import Path
import cv2
import numpy as np
from app.models.schemas import DetectionItem
from app.services.visual_features import masked_regions

BACKEND_DIR = Path(__file__).resolve().parents[2]
_MODEL_CACHE = {}
_MODEL_LOCK = threading.RLock()


def _mask(polygon, shape, offset=(0, 0)):
    result = np.zeros(shape[:2], dtype=np.uint8)
    if polygon is not None and len(polygon) >= 3:
        points = np.rint(np.asarray(polygon) - np.array(offset)).astype(np.int32)
        cv2.fillPoly(result, [points], 255)
    return result


def _bag_owner(bag, people):
    x1, y1, x2, y2 = bag['bbox']
    area = max(1, (x2 - x1) * (y2 - y1))
    scores = []
    for index, person in enumerate(people):
        a, b, c, d = person['bbox']
        overlap = max(0, min(x2, c) - max(x1, a)) * max(0, min(y2, d) - max(y1, b)) / area
        if overlap >= .65:
            scores.append((overlap, index))
    scores.sort(reverse=True)
    if not scores or (len(scores) > 1 and scores[0][0] - scores[1][0] < .15):
        return None
    return scores[0][1]


def _box_iou(a, b):
    intersection = max(0.0, min(a[2], b[2]) - max(a[0], b[0])) * max(0.0, min(a[3], b[3]) - max(a[1], b[1]))
    area_a = max(0.0, a[2] - a[0]) * max(0.0, a[3] - a[1])
    area_b = max(0.0, b[2] - b[0]) * max(0.0, b[3] - b[1])
    return intersection / max(1.0, area_a + area_b - intersection)


def _deduplicate(records, threshold=.55):
    """Class-aware NMS for detections repeated by full-frame and overlapping tiles."""
    kept = []
    for candidate in sorted(records, key=lambda item: item['confidence'], reverse=True):
        if all(candidate['class'] != item['class'] or _box_iou(candidate['bbox'], item['bbox']) < threshold for item in kept):
            kept.append(candidate)
    return kept


class PersonDetector:
    def __init__(self, crop_dir: str, model_path=None):
        self.crop_dir = Path(crop_dir).resolve()
        self.crop_dir.mkdir(parents=True, exist_ok=True)
        self.model_path = Path(model_path or os.getenv('AIEYE_MODEL_PATH', str(BACKEND_DIR / 'models' / 'yolo11s-seg.pt'))).resolve()
        self.image_size = int(os.getenv('AIEYE_IMAGE_SIZE', '1280'))
        if self.image_size < 320 or self.image_size > 2048:
            raise ValueError('AIEYE_IMAGE_SIZE must be between 320 and 2048.')
        self.enable_tiling = os.getenv('AIEYE_ENABLE_TILING', 'true').lower() not in ('0', 'false', 'no')
        self.tile_overlap = float(os.getenv('AIEYE_TILE_OVERLAP', '.20'))
        if not 0 <= self.tile_overlap <= .5:
            raise ValueError('AIEYE_TILE_OVERLAP must be between 0 and .5.')
        self._init_yolo()

    def _init_yolo(self):
        if not self.model_path.is_file():
            raise RuntimeError('YOLO segmentation model missing. Run: python backend/download_models.py')
        config = Path(os.getenv('AIEYE_DATA_DIR', str(BACKEND_DIR / 'data'))) / 'ultralytics'
        config.mkdir(parents=True, exist_ok=True)
        os.environ.setdefault('YOLO_CONFIG_DIR', str(config.resolve()))
        key = (str(self.model_path), self.model_path.stat().st_mtime_ns)
        with _MODEL_LOCK:
            if key not in _MODEL_CACHE:
                import torch
                from ultralytics import YOLO
                torch.set_num_threads(max(1, int(os.getenv('AIEYE_CPU_THREADS', '4'))))
                try:
                    model = YOLO(str(self.model_path))
                except Exception as exc:
                    raise RuntimeError('Configured YOLO model could not be loaded; no fallback will run.') from exc
                if model.task != 'segment' or model.names.get(0) != 'person' or model.names.get(24) != 'backpack':
                    raise RuntimeError('Use a COCO segmentation model with person and backpack classes.')
                version = self.model_path.name + ':' + hashlib.sha256(self.model_path.read_bytes()).hexdigest()[:12]
                _MODEL_CACHE[key] = (model, version)
            self.yolo_model, self.model_version = _MODEL_CACHE[key]

    def _predict(self, frame, image_size, threshold):
        with _MODEL_LOCK:
            try:
                result = self.yolo_model.predict(frame, verbose=False, save=False, classes=[0, 24], conf=min(threshold, .25), iou=.5, imgsz=image_size)[0]
            except Exception as exc:
                raise RuntimeError('YOLO inference failed; analysis stopped without a fallback.') from exc
        records = []
        polygons = result.masks.xy if result.masks is not None else []
        for i, box in enumerate(result.boxes):
            label, score = int(box.cls.item()), float(box.conf.item())
            if score < (threshold if label == 0 else .35):
                continue
            records.append({'class': label, 'confidence': score, 'bbox': box.xyxy[0].cpu().tolist(),
                            'polygon': polygons[i] if i < len(polygons) else None})
        return records

    def _predict_with_tiles(self, frame, threshold):
        """Preserve full-frame context and recover small people at native resolution."""
        records = self._predict(frame, self.image_size, threshold)
        height, width = frame.shape[:2]
        if not self.enable_tiling or max(height, width) <= int(self.image_size * 1.25):
            return records
        tile = self.image_size
        stride = max(1, int(tile * (1 - self.tile_overlap)))
        xs = list(range(0, max(1, width - tile + 1), stride))
        ys = list(range(0, max(1, height - tile + 1), stride))
        xs.append(max(0, width - tile)); ys.append(max(0, height - tile))
        for y in sorted(set(ys)):
            for x in sorted(set(xs)):
                patch = frame[y:min(height, y + tile), x:min(width, x + tile)]
                for item in self._predict(patch, self.image_size, threshold):
                    translated = dict(item)
                    translated['bbox'] = [item['bbox'][0] + x, item['bbox'][1] + y,
                                          item['bbox'][2] + x, item['bbox'][3] + y]
                    if item['polygon'] is not None:
                        translated['polygon'] = np.asarray(item['polygon']) + np.array([x, y])
                    records.append(translated)
        return _deduplicate(records)

    @staticmethod
    def estimate_crop_quality(crop):
        if crop is None or crop.size == 0:
            return 0.0
        h, w = crop.shape[:2]
        blur = cv2.Laplacian(cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY), cv2.CV_64F).var()
        return float(round(.5 * min(1, h * w / 20000) + .5 * min(1, blur / 150), 3))

    def detect_in_frame(self, frame, session_id, frame_idx, timestamp_seconds, min_confidence=.4, crop_margin=.12):
        if frame is None or frame.size == 0:
            return []
        records = self._predict_with_tiles(frame, min_confidence)
        people = [r for r in records if r['class'] == 0]
        bags = [r for r in records if r['class'] == 24]
        assignments = [(bag, _bag_owner(bag, people)) for bag in bags]
        directory = (self.crop_dir / session_id).resolve()
        if directory.parent != self.crop_dir:
            raise ValueError('Invalid session storage path.')
        directory.mkdir(parents=True, exist_ok=True)
        output = []
        for pi, person in enumerate(people):
            x1, y1, x2, y2 = person['bbox']
            w, h = x2 - x1, y2 - y1
            a, b = max(0, int(x1 - w * crop_margin)), max(0, int(y1 - h * crop_margin))
            c, d = min(frame.shape[1], int(x2 + w * crop_margin)), min(frame.shape[0], int(y2 + h * crop_margin))
            crop = frame[b:d, a:c]
            if crop.size == 0:
                continue
            person_mask = _mask(person['polygon'], crop.shape, (a, b))
            bag_mask = np.zeros(crop.shape[:2], dtype=np.uint8)
            for bag, owner in assignments:
                if owner == pi:
                    bag_mask |= _mask(bag['polygon'], crop.shape, (a, b))
            features, visibility = masked_regions(crop, person_mask, bag_mask)
            detection_id = f'det_{session_id}_{frame_idx}_{uuid.uuid4().hex[:8]}'
            path = directory / (detection_id + '.jpg')
            mask_path = directory / (detection_id + '_mask.png')
            if not cv2.imwrite(str(path), crop) or not cv2.imwrite(str(mask_path), person_mask):
                raise RuntimeError('Could not save analysis evidence. Check available disk space.')
            output.append(DetectionItem(detection_id=detection_id, frame_idx=frame_idx, timestamp_seconds=timestamp_seconds,
                bbox=person['bbox'], confidence=person['confidence'], quality_score=self.estimate_crop_quality(crop),
                crop_path=f'/crops/{session_id}/{path.name}', mask_path=f'/crops/{session_id}/{mask_path.name}',
                detector_name='YOLO instance segmentation', model_version=self.model_version, color_features=features,
                attribute_visibility=visibility, backpack_detected=True if features.get('backpack') else None))
        return output

    def refine_evidence(self, detection):
        # Same model, higher relative resolution. This stage never creates detections.
        path = (self.crop_dir.parent / (detection.crop_path or '').lstrip('/')).resolve()
        if not path.is_relative_to(self.crop_dir) or not path.is_file():
            return detection
        crop = cv2.imread(str(path))
        if crop is None or min(crop.shape[:2]) < 24:
            return detection
        records = self._predict(crop, 640, .4)
        people = [r for r in records if r['class'] == 0]
        if not people:
            return detection
        original_path = (self.crop_dir.parent / (detection.mask_path or '').lstrip('/')).resolve()
        if not original_path.is_relative_to(self.crop_dir) or not original_path.is_file():
            return detection
        original_mask = cv2.imread(str(original_path), cv2.IMREAD_GRAYSCALE)
        if original_mask is None or original_mask.shape != crop.shape[:2]:
            return detection
        overlaps = []
        for candidate in people:
            candidate_mask = _mask(candidate['polygon'], crop.shape)
            intersection = np.count_nonzero((candidate_mask > 0) & (original_mask > 0))
            union = np.count_nonzero((candidate_mask > 0) | (original_mask > 0))
            overlaps.append(intersection / max(1, union))
        person_index = int(np.argmax(overlaps))
        if overlaps[person_index] < .5:
            return detection
        person = people[person_index]
        bag_mask = np.zeros(crop.shape[:2], dtype=np.uint8)
        for bag in (r for r in records if r['class'] == 24):
            if _bag_owner(bag, people) == person_index:
                bag_mask |= _mask(bag['polygon'], crop.shape)
        features, visibility = masked_regions(crop, _mask(person['polygon'], crop.shape), bag_mask)
        # Preserve a supported bag observation when a tighter view cannot recover it.
        if detection.backpack_detected and not features.get('backpack'):
            return detection
        if features:
            detection.color_features = features
            detection.attribute_visibility = visibility
            detection.backpack_detected = True if features.get('backpack') else None
        return detection
