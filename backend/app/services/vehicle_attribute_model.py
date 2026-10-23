"""Optional local fine-grained vehicle classifier with auditable provenance."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import threading

import cv2
import numpy as np

from app.models.open_vocabulary import ModelProvenance


_MODEL_LOCK = threading.RLock()


class LocalVehicleAttributeProvider:
    """Load a PyTorch Export classifier and a versioned label manifest.

    Softmax values are returned as model confidence only.  Acceptance remains a
    separate multi-frame decision and must be calibrated on held-out data.
    """

    def __init__(self, model_path, manifest_path, *, device=None, model=None):
        import torch
        self.torch = torch
        self.model_path = Path(model_path).resolve()
        self.manifest_path = Path(manifest_path).resolve()
        if not self.manifest_path.is_file():
            raise RuntimeError("Vehicle attribute label manifest is missing.")
        manifest = json.loads(self.manifest_path.read_text(encoding="utf-8"))
        self.labels = list(manifest.get("classes") or [])
        if not self.labels:
            raise RuntimeError("Vehicle attribute manifest contains no classes.")
        self.input_size = int(manifest.get("input_size", 224))
        if not 64 <= self.input_size <= 1024:
            raise RuntimeError("Vehicle attribute input size is invalid.")
        self.device = device or ("cuda" if torch.cuda.is_available() else "cpu")
        exported_model = model is None
        if model is None:
            if not self.model_path.is_file():
                raise RuntimeError("Vehicle attribute model is missing.")
            if self.model_path.suffix.lower() != ".pt2":
                raise RuntimeError("Vehicle attribute model must use the PyTorch Export .pt2 format.")
            exported = torch.export.load(str(self.model_path))
            model = exported.module()
        self.model = model.to(self.device)
        if not exported_model:
            self.model = self.model.eval()
        self.model_hash = (hashlib.sha256(self.model_path.read_bytes()).hexdigest()
                           if self.model_path.is_file() else "injected-test-model")
        self.manifest_hash = hashlib.sha256(self.manifest_path.read_bytes()).hexdigest()
        self.dataset = manifest.get("dataset") or {}

    @property
    def provenance(self):
        return ModelProvenance(
            provider="local-pytorch-export", model_name=self.model_path.name,
            model_version=self.model_hash, device=self.device,
            metadata={
                "task": "vehicle-make-model-year-candidates",
                "manifest_sha256": self.manifest_hash,
                "class_count": len(self.labels),
                "dataset": self.dataset,
                "outputs_are_model_confidence_not_accuracy": True,
            },
        )

    def _tensor(self, image_path):
        image = cv2.imread(str(image_path))
        if image is None or image.size == 0:
            raise ValueError("Vehicle crop could not be opened.")
        image = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
        height, width = image.shape[:2]
        scale = self.input_size / min(height, width)
        resized = cv2.resize(
            image, (round(width * scale), round(height * scale)),
            interpolation=cv2.INTER_AREA if scale < 1 else cv2.INTER_CUBIC,
        )
        y = max(0, (resized.shape[0] - self.input_size) // 2)
        x = max(0, (resized.shape[1] - self.input_size) // 2)
        crop = resized[y:y + self.input_size, x:x + self.input_size]
        values = crop.astype(np.float32) / 255.0
        values = (values - np.array([.485, .456, .406], np.float32)) / np.array([.229, .224, .225], np.float32)
        return self.torch.from_numpy(values.transpose(2, 0, 1)).unsqueeze(0).to(self.device)

    def predict(self, image_path, *, top_k=5):
        if top_k < 1:
            raise ValueError("top_k must be at least 1.")
        with self.torch.inference_mode(), _MODEL_LOCK:
            logits = self.model(self._tensor(image_path))
            if isinstance(logits, (tuple, list)):
                logits = logits[0]
            logits = logits.reshape(1, -1)
            if logits.shape[1] != len(self.labels):
                raise RuntimeError("Vehicle model output does not match its label manifest.")
            probabilities = self.torch.softmax(logits, dim=1)[0]
            values, indices = self.torch.topk(probabilities, min(top_k, len(self.labels)))
        candidates = []
        for confidence, index in zip(values.detach().cpu().tolist(), indices.detach().cpu().tolist()):
            label = dict(self.labels[int(index)])
            candidates.append({
                "make": label.get("make"), "model": label.get("model"),
                "year_start": label.get("year_start"), "year_end": label.get("year_end"),
                "confidence": round(float(confidence), 6),
                "class_id": int(index), "confidence_kind": "model_softmax",
            })
        return candidates
