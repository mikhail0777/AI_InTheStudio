import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import cv2
import numpy as np

from app import database
from app.models.open_vocabulary import ModelProvenance
from app.models.schemas import VideoMetadata
from app.services.semantic_retrieval import SemanticRetrievalService
from app.services.video_indexer import VideoIndexer


class FakeEmbeddingProvider:
    dimension = 2

    def __init__(self):
        self.image_calls = 0

    @property
    def provenance(self):
        return ModelProvenance(provider="test", model_name="color", model_version="1", device="cpu")

    def embed_images(self, paths):
        self.image_calls += 1
        vectors = []
        for path in paths:
            image = cv2.imread(path)
            vectors.append([2, 0] if float(image[:, :, 2].mean()) > float(image[:, :, 0].mean()) else [0, 3])
        return vectors

    def embed_text(self, texts):
        return [[4, 0] if "red" in text else [0, 5] for text in texts]


def write_video(path: Path):
    writer = cv2.VideoWriter(str(path), cv2.VideoWriter_fourcc(*"mp4v"), 2, (64, 64))
    for color in [(255, 0, 0)] * 2 + [(0, 0, 255)] * 2:
        writer.write(np.full((64, 64, 3), color, dtype=np.uint8))
    writer.release()


class SemanticRetrievalTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        for item in [patch.object(database, "DB_DIR", str(self.root)),
                     patch.object(database, "DB_PATH", str(self.root / "test.db"))]:
            item.start()
            self.addCleanup(item.stop)
        database.init_db()
        path = self.root / "colors.mp4"
        write_video(path)
        metadata = VideoMetadata(
            filename=path.name, filepath=str(path), duration_seconds=2, frame_count=4, fps=2,
            width=64, height=64, codec="mp4v", file_size_mb=path.stat().st_size / 1024**2,
            creation_timestamp="",
        )
        self.index = VideoIndexer(str(self.root / "indexes")).build_or_reuse(metadata, "thorough")

    def test_indexes_once_and_ranks_by_text_similarity(self):
        provider = FakeEmbeddingProvider()
        service = SemanticRetrievalService(provider)
        first_count = service.index_frames(self.index.index_id)
        second_count = service.index_frames(self.index.index_id)
        clip_count = service.index_clips(self.index.index_id)
        results = service.retrieve(self.index.index_id, "a red scene", limit=3, owner_kinds=("frame",))
        self.assertGreater(first_count, 0)
        self.assertEqual(second_count, 0)
        self.assertGreater(clip_count, 0)
        self.assertEqual(provider.image_calls, 1)
        self.assertEqual(results[0].rank, 1)
        self.assertLessEqual(results[0].semantic_similarity, 1)
        image = cv2.imread(results[0].artifact_path)
        self.assertGreater(float(image[:, :, 2].mean()), float(image[:, :, 0].mean()))
        clip_results = service.retrieve(self.index.index_id, "a red scene", limit=2, owner_kinds=("clip",))
        self.assertTrue(clip_results)
        self.assertTrue(all(item.owner_kind == "clip" for item in clip_results))

    def test_persists_auditable_candidates_for_search(self):
        provider = FakeEmbeddingProvider()
        service = SemanticRetrievalService(provider)
        with database.get_db_connection() as conn:
            conn.execute("INSERT INTO sessions(session_id,status) VALUES ('s','created')")
            conn.execute("""INSERT INTO searches(search_id,session_id,index_id,status,query_json)
                VALUES ('q','s',?,'retrieving',?)""", (self.index.index_id, json.dumps({"original_text": "blue"})))
        results = service.retrieve(self.index.index_id, "a blue scene", limit=2, search_id="q")
        with database.get_db_connection() as conn:
            rows = conn.execute("SELECT * FROM search_candidates WHERE search_id='q' ORDER BY rank").fetchall()
        self.assertEqual(len(rows), len(results))
        self.assertEqual(rows[0]["owner_id"], results[0].owner_id)

    def test_rejects_empty_queries_and_invalid_limits(self):
        service = SemanticRetrievalService(FakeEmbeddingProvider())
        with self.assertRaisesRegex(ValueError, "empty"):
            service.retrieve(self.index.index_id, " ")
        with self.assertRaisesRegex(ValueError, "positive"):
            service.retrieve(self.index.index_id, "red", limit=0)
        with self.assertRaisesRegex(ValueError, "exceed"):
            service.retrieve(self.index.index_id, "red", limit=1001)
        with self.assertRaisesRegex(ValueError, "4000"):
            service.retrieve(self.index.index_id, "x" * 4001)
        with self.assertRaisesRegex(ValueError, "owner kinds"):
            service.retrieve(self.index.index_id, "red", owner_kinds=("object",))


if __name__ == "__main__":
    unittest.main()
