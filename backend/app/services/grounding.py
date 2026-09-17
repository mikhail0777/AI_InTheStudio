"""Replaceable open-vocabulary OWLv2 grounding provider."""
import hashlib
import os
from pathlib import Path
import threading
import uuid
from typing import Sequence

import cv2
import numpy as np
from PIL import Image

from app.models.open_vocabulary import EntityDetection, ModelProvenance
from app.services.generic_detector import CandidateFrame
from app.services.visual_features import color_distribution


MODEL_ID = "google/owlv2-base-patch16-ensemble"
MODEL_REVISION = "410d70ced26e95c344915c2f10f4ecf967f2cde4"
MODEL_SHA256 = "e1e130b9e404cf91a75ad45644c1da9d7fa5284085eecc864266a6923efb99e7"
DEFAULT_MODEL_PATH = Path(__file__).resolve().parents[2] / "models" / "owlv2"
_CACHE = {}
_LOCK = threading.RLock()


def _box_iou(left, right):
    x1, y1 = max(left[0], right[0]), max(left[1], right[1])
    x2, y2 = min(left[2], right[2]), min(left[3], right[3])
    intersection = max(0.0, x2 - x1) * max(0.0, y2 - y1)
    left_area = max(0.0, left[2] - left[0]) * max(0.0, left[3] - left[1])
    right_area = max(0.0, right[2] - right[0]) * max(0.0, right[3] - right[1])
    return intersection / max(1.0, left_area + right_area - intersection)


def _phrase_nms(boxes, scores, labels, threshold=.45):
    kept = []
    for index in sorted(range(len(scores)), key=lambda item: float(scores[item]), reverse=True):
        box = [float(value) for value in boxes[index]]
        if any(labels[index] == labels[other] and _box_iou(box, boxes[other]) >= threshold for other in kept):
            continue
        kept.append(index)
    return kept


class Owlv2GroundingProvider:
    """Phrase-conditioned boxes for entities outside a fixed detection taxonomy."""

    def __init__(self, evidence_root: str, *, model_id=MODEL_ID, revision=MODEL_REVISION,
                 processor=None, model=None, device=None):
        self.evidence_root = Path(evidence_root).resolve()
        self.evidence_root.mkdir(parents=True, exist_ok=True)
        self.model_id, self.revision = model_id, revision
        if processor is not None and model is not None:
            self.processor, self.model = processor, model
            self.device = device or "cpu"
            self.weight_hash = "injected-test-model"
            return
        self._load(device)

    def _load(self, device):
        import torch
        from transformers import Owlv2ForObjectDetection, Owlv2Processor

        self.device = device or ("cuda" if torch.cuda.is_available() else "cpu")
        model_path = Path(os.environ.get("AIEYE_GROUNDING_MODEL_PATH", str(DEFAULT_MODEL_PATH))).resolve()
        weight = model_path / "model.safetensors"
        if not weight.is_file():
            raise RuntimeError("OWLv2 grounding model missing. Run: python backend/download_models.py")
        actual = hashlib.sha256(weight.read_bytes()).hexdigest()
        if actual != MODEL_SHA256:
            raise RuntimeError(f"Unexpected OWLv2 weight hash: {actual}")
        key = (str(model_path), self.revision, self.device)
        with _LOCK:
            if key not in _CACHE:
                processor = Owlv2Processor.from_pretrained(
                    str(model_path), local_files_only=True, use_fast=True,
                )
                model = Owlv2ForObjectDetection.from_pretrained(
                    str(model_path), local_files_only=True,
                    use_safetensors=True,
                ).to(self.device).eval()
                _CACHE[key] = processor, model
            self.processor, self.model = _CACHE[key]
        self.weight_hash = actual

    @property
    def provenance(self):
        return ModelProvenance(
            provider="huggingface-transformers", model_name=self.model_id,
            model_version=self.revision, device=self.device,
            metadata={"task": "open-vocabulary-grounding", "weight_sha256": self.weight_hash,
                      "localization_kind": "bounding_box", "processor": "fast"},
        )

    def ground(self, frames: Sequence[CandidateFrame], phrases: Sequence[str], session_id: str,
               min_confidence: float = .15):
        phrases = list(dict.fromkeys(phrase.strip().lower() for phrase in phrases if phrase.strip()))
        if not phrases or not frames:
            return []
        directory = (self.evidence_root / session_id).resolve()
        if directory.parent != self.evidence_root:
            raise ValueError("Invalid evidence directory.")
        directory.mkdir(parents=True, exist_ok=True)
        output = []
        batch_size = max(1, int(os.environ.get("AIEYE_GROUNDING_BATCH_SIZE", "2")))
        import torch
        for start in range(0, len(frames), batch_size):
            batch = frames[start:start + batch_size]
            arrays = [cv2.imread(frame.image_path) for frame in batch]
            if any(image is None or image.size == 0 for image in arrays):
                raise ValueError("A retrieved frame could not be opened for grounding.")
            images = [Image.fromarray(cv2.cvtColor(image, cv2.COLOR_BGR2RGB)) for image in arrays]
            inputs = self.processor(text=[phrases] * len(images), images=images,
                                    return_tensors="pt", padding=True)
            model_inputs = {name: value.to(self.device) for name, value in inputs.items()}
            with torch.inference_mode(), _LOCK:
                predictions = self.model(**model_inputs)
            sizes = torch.tensor([[image.height, image.width] for image in images])
            results = self.processor.post_process_grounded_object_detection(
                predictions, target_sizes=sizes, threshold=min_confidence,
            )
            for frame, image, result in zip(batch, arrays, results):
                text_labels = result.get("text_labels")
                labels = [str(text_labels[index]) if text_labels is not None else phrases[int(label_id)]
                          for index, label_id in enumerate(result["labels"])]
                for index in _phrase_nms(result["boxes"], result["scores"], labels):
                    box, score = result["boxes"][index], result["scores"][index]
                    label = labels[index]
                    bbox = [float(value) for value in box.cpu().tolist()]
                    x1, y1, x2, y2 = bbox
                    a, b = max(0, int(x1)), max(0, int(y1))
                    c, d = min(image.shape[1], int(np.ceil(x2))), min(image.shape[0], int(np.ceil(y2)))
                    if c <= a or d <= b:
                        continue
                    crop = image[b:d, a:c]
                    # OWLv2 produces boxes, not masks. Keep this explicit in provenance and
                    # use an inset box to reduce background leakage for approximate attributes.
                    mask = np.zeros(crop.shape[:2], dtype=np.uint8)
                    inset_x, inset_y = max(1, crop.shape[1] // 12), max(1, crop.shape[0] // 12)
                    mask[inset_y:crop.shape[0] - inset_y, inset_x:crop.shape[1] - inset_x] = 255
                    detection_id = f"ground_{frame.frame_idx}_{uuid.uuid4().hex[:10]}"
                    crop_file = directory / f"{detection_id}.jpg"
                    if not cv2.imwrite(str(crop_file), crop):
                        raise OSError("Could not save grounded evidence.")
                    blur = cv2.Laplacian(cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY), cv2.CV_64F).var()
                    quality = min(1.0, .5 + .5 * min(1.0, blur / 250.0))
                    output.append(EntityDetection(
                        detection_id=detection_id, frame_id=frame.frame_id,
                        frame_idx=frame.frame_idx, timestamp_seconds=frame.timestamp_seconds,
                        label=label.lower(), bbox=bbox, confidence=float(score), visibility=quality,
                        crop_path=f"/evidence/{session_id}/{crop_file.name}",
                        attributes={"colors": color_distribution(crop, mask),
                                    "semantic_similarity": frame.semantic_similarity,
                                    "localization_kind": "bounding_box"},
                        provenance=self.provenance,
                    ))
        return output
