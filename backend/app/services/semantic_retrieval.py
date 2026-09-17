"""Local image/text embeddings and cosine candidate retrieval."""
import json
import math
import os
from pathlib import Path
from typing import List, Optional, Sequence

import numpy as np

from app import database
from app.models.open_vocabulary import ModelProvenance, SemanticCandidate


SIGLIP_MODEL_ID = "google/siglip-base-patch16-224"
SIGLIP_REVISION = "7fd15f0689c79d79e38b1c2e2e2370a7bf2761ed"
SIGLIP_WEIGHT_SHA256 = "2c63cb7d1f2e95ba501893cbb8faeb4ea9a3af295498d35097126228659c2af8"


def _normalize(values: np.ndarray) -> np.ndarray:
    values = np.asarray(values, dtype=np.float32)
    lengths = np.linalg.norm(values, axis=1, keepdims=True)
    if np.any(~np.isfinite(lengths)) or np.any(lengths <= 0):
        raise ValueError("Embedding provider returned a zero or non-finite vector.")
    return values / lengths


class SiglipEmbeddingProvider:
    """Pinned, offline-only SigLIP provider with batched CPU/GPU inference."""

    def __init__(self, model_id: str = SIGLIP_MODEL_ID, revision: str = SIGLIP_REVISION,
                 device: Optional[str] = None, batch_size: Optional[int] = None):
        try:
            import torch
            from transformers import AutoModel, AutoProcessor
        except ImportError as error:
            raise RuntimeError("SigLIP dependencies are missing. Run: python -m pip install -r backend/requirements.txt") from error
        self.torch = torch
        self.model_id = model_id
        self.revision = revision
        self.device = device or ("cuda" if torch.cuda.is_available() else "cpu")
        self.batch_size = batch_size or int(os.environ.get("AIEYE_EMBEDDING_BATCH_SIZE", "8" if self.device == "cuda" else "2"))
        if self.batch_size <= 0:
            raise ValueError("Embedding batch size must be positive.")
        try:
            # Runtime is intentionally offline. Model installation is an explicit operator action.
            self.processor = AutoProcessor.from_pretrained(
                model_id, revision=revision, local_files_only=True, use_fast=False,
            )
            self.model = AutoModel.from_pretrained(
                model_id, revision=revision, local_files_only=True, use_safetensors=True,
            ).to(self.device).eval()
        except (OSError, ValueError) as error:
            raise RuntimeError(
                "Pinned SigLIP model is not installed. Run: python backend/download_models.py"
            ) from error
        self._dimension = int(self.model.config.text_config.hidden_size)

    @property
    def dimension(self) -> int:
        return self._dimension

    @property
    def provenance(self) -> ModelProvenance:
        return ModelProvenance(
            provider="huggingface-transformers", model_name=self.model_id,
            model_version=self.revision, device=self.device,
            metadata={"weight_sha256": SIGLIP_WEIGHT_SHA256, "input_size": 224},
        )

    @staticmethod
    def _pooled(output):
        return output.pooler_output if hasattr(output, "pooler_output") else output

    def embed_images(self, image_paths: Sequence[str]) -> List[List[float]]:
        from PIL import Image
        vectors = []
        for start in range(0, len(image_paths), self.batch_size):
            paths = image_paths[start:start + self.batch_size]
            images = []
            try:
                for path in paths:
                    with Image.open(path) as source:
                        source.load()
                        images.append(source.convert("RGB"))
                inputs = self.processor(images=images, return_tensors="pt")
                inputs = {name: value.to(self.device) for name, value in inputs.items()}
                with self.torch.inference_mode():
                    output = self._pooled(self.model.get_image_features(**inputs))
                vectors.append(output.detach().float().cpu().numpy())
            finally:
                for image in images:
                    image.close()
        if not vectors:
            return []
        return _normalize(np.concatenate(vectors, axis=0)).tolist()

    def embed_text(self, texts: Sequence[str]) -> List[List[float]]:
        vectors = []
        prompts = [f"This is a photo of {text.strip()}." for text in texts]
        for start in range(0, len(prompts), self.batch_size):
            inputs = self.processor(
                text=prompts[start:start + self.batch_size], padding="max_length",
                truncation=True, return_tensors="pt",
            )
            inputs = {name: value.to(self.device) for name, value in inputs.items()}
            with self.torch.inference_mode():
                output = self._pooled(self.model.get_text_features(**inputs))
            vectors.append(output.detach().float().cpu().numpy())
        if not vectors:
            return []
        return _normalize(np.concatenate(vectors, axis=0)).tolist()


class SemanticRetrievalService:
    def __init__(self, provider=None):
        self.provider = provider

    def _provider(self):
        if self.provider is None:
            self.provider = SiglipEmbeddingProvider()
        return self.provider

    def index_frames(self, index_id: str) -> int:
        provider = self._provider()
        provenance = provider.provenance
        with database.get_db_connection() as conn:
            index = conn.execute("SELECT model_manifest FROM video_indexes WHERE index_id=? AND status='complete'", (index_id,)).fetchone()
            if not index:
                raise LookupError("Completed video index not found.")
            frames = conn.execute("""SELECT f.frame_id,f.image_path FROM indexed_frames f
                LEFT JOIN embeddings e ON e.index_id=f.index_id AND e.owner_kind='frame'
                    AND e.owner_id=f.frame_id AND e.provider=? AND e.model_version=?
                WHERE f.index_id=? AND e.owner_id IS NULL ORDER BY f.timestamp_seconds""",
                (provenance.provider, provenance.model_version, index_id)).fetchall()
        if not frames:
            return 0
        paths = [row["image_path"] for row in frames]
        if any(not Path(path).is_file() for path in paths):
            raise ValueError("An indexed frame artifact is missing; rebuild the video index.")
        vectors = _normalize(np.asarray(provider.embed_images(paths), dtype=np.float32)).tolist()
        if len(vectors) != len(frames):
            raise RuntimeError("Embedding provider returned the wrong number of vectors.")
        rows = []
        for frame, vector in zip(frames, vectors):
            array = np.asarray(vector, dtype="<f4")
            if array.ndim != 1 or len(array) != provider.dimension:
                raise RuntimeError("Embedding provider returned an unexpected vector dimension.")
            rows.append((index_id, "frame", frame["frame_id"], provenance.provider,
                         provenance.model_version, provider.dimension, array.tobytes(), "{}"))
        with database.get_db_connection() as conn:
            conn.execute("BEGIN IMMEDIATE")
            conn.executemany("""INSERT OR REPLACE INTO embeddings(index_id,owner_kind,owner_id,provider,
                model_version,dimension,vector,metadata) VALUES (?,?,?,?,?,?,?,?)""", rows)
            manifest = json.loads(index["model_manifest"])
            manifest["embeddings"] = provenance.model_dump(mode="json")
            conn.execute("UPDATE video_indexes SET model_manifest=? WHERE index_id=?", (json.dumps(manifest), index_id))
        return len(rows)

    def index_clips(self, index_id: str) -> int:
        provider = self._provider()
        provenance = provider.provenance
        self.index_frames(index_id)
        with database.get_db_connection() as conn:
            clips = conn.execute("""SELECT c.clip_id,c.start_seconds,c.end_seconds
                FROM indexed_clips c LEFT JOIN embeddings e ON e.index_id=c.index_id
                    AND e.owner_kind='clip' AND e.owner_id=c.clip_id
                    AND e.provider=? AND e.model_version=?
                WHERE c.index_id=? AND e.owner_id IS NULL ORDER BY c.start_seconds""",
                (provenance.provider, provenance.model_version, index_id)).fetchall()
            frame_rows = conn.execute("""SELECT e.owner_id,e.dimension,e.vector,f.timestamp_seconds
                FROM embeddings e JOIN indexed_frames f ON f.index_id=e.index_id AND f.frame_id=e.owner_id
                WHERE e.index_id=? AND e.owner_kind='frame' AND e.provider=? AND e.model_version=?
                ORDER BY f.timestamp_seconds""", (index_id, provenance.provider, provenance.model_version)).fetchall()
        if not clips:
            return 0
        rows = []
        for clip in clips:
            vectors = [np.frombuffer(frame["vector"], dtype="<f4") for frame in frame_rows
                       if clip["start_seconds"] <= frame["timestamp_seconds"] <= clip["end_seconds"]]
            if not vectors:
                raise RuntimeError(f"Clip {clip['clip_id']} contains no indexed frame embeddings.")
            vector = _normalize(np.mean(np.stack(vectors), axis=0, keepdims=True))[0].astype("<f4")
            rows.append((index_id, "clip", clip["clip_id"], provenance.provider,
                         provenance.model_version, len(vector), vector.tobytes(),
                         json.dumps({"aggregation": "normalized_mean_frame_embeddings"})))
        with database.get_db_connection() as conn:
            conn.execute("BEGIN IMMEDIATE")
            conn.executemany("""INSERT OR REPLACE INTO embeddings(index_id,owner_kind,owner_id,provider,
                model_version,dimension,vector,metadata) VALUES (?,?,?,?,?,?,?,?)""", rows)
        return len(rows)

    def retrieve(self, index_id: str, query: str, limit: int = 20,
                 search_id: Optional[str] = None,
                 owner_kinds: Sequence[str] = ("frame", "clip")) -> List[SemanticCandidate]:
        if not query.strip():
            raise ValueError("Search query cannot be empty.")
        if len(query) > 4000:
            raise ValueError("Search query must be at most 4000 characters.")
        if limit <= 0:
            raise ValueError("Candidate limit must be positive.")
        if limit > 1000:
            raise ValueError("Candidate limit must not exceed 1000.")
        owner_kinds = tuple(dict.fromkeys(owner_kinds))
        if not owner_kinds or any(kind not in ("frame", "clip") for kind in owner_kinds):
            raise ValueError("Candidate owner kinds must contain frame and/or clip.")
        provider = self._provider()
        self.index_frames(index_id)
        if "clip" in owner_kinds:
            self.index_clips(index_id)
        query_vectors = provider.embed_text([query])
        if len(query_vectors) != 1:
            raise RuntimeError("Embedding provider did not return one query vector.")
        query_vector = _normalize(np.asarray(query_vectors, dtype=np.float32))[0]
        provenance = provider.provenance
        with database.get_db_connection() as conn:
            rows = conn.execute("""SELECT e.owner_kind,e.owner_id,e.dimension,e.vector,
                CASE WHEN e.owner_kind='frame' THEN f.timestamp_seconds ELSE rf.timestamp_seconds END timestamp_seconds,
                CASE WHEN e.owner_kind='frame' THEN f.image_path ELSE rf.image_path END image_path,
                CASE WHEN e.owner_kind='frame' THEN f.scene_id ELSE rf.scene_id END scene_id,
                CASE WHEN e.owner_kind='frame' THEN f.quality_score ELSE rf.quality_score END quality_score,
                c.start_seconds clip_start_seconds,c.end_seconds clip_end_seconds
                FROM embeddings e
                JOIN indexed_frames f ON f.index_id=e.index_id AND f.frame_id=e.owner_id
                    AND e.owner_kind='frame'
                LEFT JOIN indexed_clips c ON c.index_id=e.index_id AND c.clip_id=e.owner_id
                    AND e.owner_kind='clip'
                LEFT JOIN indexed_frames rf ON rf.index_id=c.index_id AND rf.frame_id=c.representative_frame_id
                WHERE e.index_id=? AND e.provider=? AND e.model_version=?
                UNION ALL
                SELECT e.owner_kind,e.owner_id,e.dimension,e.vector,rf.timestamp_seconds,
                    rf.image_path,rf.scene_id,rf.quality_score,c.start_seconds,c.end_seconds
                FROM embeddings e JOIN indexed_clips c ON c.index_id=e.index_id AND c.clip_id=e.owner_id
                    AND e.owner_kind='clip'
                JOIN indexed_frames rf ON rf.index_id=c.index_id AND rf.frame_id=c.representative_frame_id
                WHERE e.index_id=? AND e.provider=? AND e.model_version=?""",
                (index_id, provenance.provider, provenance.model_version,
                 index_id, provenance.provider, provenance.model_version)).fetchall()
        rows = [row for row in rows if row["owner_kind"] in owner_kinds]
        scored = []
        for row in rows:
            vector = np.frombuffer(row["vector"], dtype="<f4")
            if row["dimension"] != len(vector) or len(vector) != len(query_vector):
                raise RuntimeError("Stored embedding dimension does not match the active model.")
            score = float(np.dot(query_vector, vector))
            if not math.isfinite(score):
                continue
            scored.append((max(-1.0, min(1.0, score)), row))
        scored.sort(key=lambda item: (-item[0], item[1]["timestamp_seconds"], item[1]["owner_kind"]))
        candidates = [SemanticCandidate(
            candidate_id=f"{row['owner_kind']}:{row['owner_id']}", index_id=index_id,
            owner_kind=row["owner_kind"], owner_id=row["owner_id"],
            timestamp_seconds=row["timestamp_seconds"], semantic_similarity=round(score, 6),
            rank=rank, artifact_path=row["image_path"],
            metadata={"scene_id": row["scene_id"], "quality_score": row["quality_score"],
                      "clip_start_seconds": row["clip_start_seconds"],
                      "clip_end_seconds": row["clip_end_seconds"],
                      "query": query, "provenance": provenance.model_dump(mode="json")},
        ) for rank, (score, row) in enumerate(scored[:limit], start=1)]
        if search_id:
            with database.get_db_connection() as conn:
                conn.execute("BEGIN IMMEDIATE")
                if not conn.execute("SELECT 1 FROM searches WHERE search_id=?", (search_id,)).fetchone():
                    raise LookupError("Search record not found.")
                conn.execute("DELETE FROM search_candidates WHERE search_id=?", (search_id,))
                conn.executemany("""INSERT INTO search_candidates(search_id,candidate_id,owner_kind,owner_id,
                    semantic_similarity,rank,payload) VALUES (?,?,?,?,?,?,?)""", [
                    (search_id, item.candidate_id, item.owner_kind, item.owner_id,
                     item.semantic_similarity, item.rank, item.model_dump_json()) for item in candidates
                ])
        return candidates
