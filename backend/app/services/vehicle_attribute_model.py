"""Optional local fine-grained vehicle classifier with auditable provenance."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import re
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
        self.device = device or ("cuda" if torch.cuda.is_available() else "cpu")
        self.prediction_task = manifest.get("prediction_task", "make_model_year_range")
        if self.prediction_task not in ("make_model_year_range", "vehicle_make_model", "grouped_make_model"):
            raise RuntimeError("Vehicle attribute prediction task is invalid.")
        self.make_model_groups = None
        self.class_to_group = None
        if self.prediction_task == "grouped_make_model":
            key_to_group = {}
            groups = []
            mapping = []
            clean = lambda value: re.sub(r"[^a-z0-9]+", "", str(value).casefold())
            for class_id, label in enumerate(self.labels):
                key = (clean(label.get("make")), clean(label.get("model")))
                if not all(key):
                    raise RuntimeError("Grouped vehicle labels require make and model.")
                if key not in key_to_group:
                    key_to_group[key] = len(groups)
                    groups.append({
                        "make": label["make"], "model": label["model"],
                        "source_class_ids": [],
                    })
                group_id = key_to_group[key]
                groups[group_id]["source_class_ids"].append(class_id)
                mapping.append(group_id)
            self.make_model_groups = groups
            self.class_to_group = torch.tensor(mapping, dtype=torch.long, device=self.device)
        self.input_size = int(manifest.get("input_size", 224))
        if not 64 <= self.input_size <= 1024:
            raise RuntimeError("Vehicle attribute input size is invalid.")
        rejection = manifest.get("unknown_rejection") or {}
        self.unknown_rejection_threshold = rejection.get("minimum_top1_probability")
        if self.unknown_rejection_threshold is not None:
            self.unknown_rejection_threshold = float(self.unknown_rejection_threshold)
            if not 0.0 <= self.unknown_rejection_threshold <= 1.0:
                raise RuntimeError("Vehicle unknown-rejection threshold is invalid.")
        self.unknown_rejection = rejection
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
                "prediction_task": self.prediction_task,
                "manifest_sha256": self.manifest_hash,
                "class_count": len(self.labels),
                "dataset": self.dataset,
                "outputs_are_model_confidence_not_accuracy": True,
                "unknown_rejection": self.unknown_rejection or None,
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
            output_labels = self.labels
            if self.prediction_task == "grouped_make_model":
                grouped = self.torch.zeros(
                    len(self.make_model_groups), dtype=probabilities.dtype, device=probabilities.device,
                )
                grouped.scatter_add_(0, self.class_to_group, probabilities)
                probabilities = grouped
                output_labels = self.make_model_groups
            values, indices = self.torch.topk(probabilities, min(top_k, len(output_labels)))
        if (
            self.unknown_rejection_threshold is not None
            and float(values[0].detach().cpu()) < self.unknown_rejection_threshold
        ):
            return []
        candidates = []
        for confidence, index in zip(values.detach().cpu().tolist(), indices.detach().cpu().tolist()):
            label = dict(output_labels[int(index)])
            candidates.append({
                "make": label.get("make"), "model": label.get("model"),
                "year_start": None if self.prediction_task == "grouped_make_model" else label.get("year_start"),
                "year_end": None if self.prediction_task == "grouped_make_model" else label.get("year_end"),
                "confidence": round(float(confidence), 6),
                "class_id": int(index), "confidence_kind": "model_softmax",
            })
            if label.get("source_class_ids") is not None:
                candidates[-1]["source_class_ids"] = label["source_class_ids"]
        return candidates
