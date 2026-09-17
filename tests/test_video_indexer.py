import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import cv2
import numpy as np

from app import database
from app.models.schemas import VideoMetadata
from app.services.video_indexer import VideoIndexer


def write_video(path: Path):
    writer = cv2.VideoWriter(str(path), cv2.VideoWriter_fourcc(*"mp4v"), 10, (96, 64))
    if not writer.isOpened():
        raise RuntimeError("test video writer unavailable")
    for index in range(30):
        value = 0 if index < 15 else 255
        writer.write(np.full((64, 96, 3), value, dtype=np.uint8))
    writer.release()


def metadata(path: Path) -> VideoMetadata:
    return VideoMetadata(
        filename=path.name, filepath=str(path), duration_seconds=3, frame_count=30, fps=10,
        width=96, height=64, codec="mp4v", file_size_mb=path.stat().st_size / 1024**2,
        creation_timestamp="",
    )


class VideoIndexerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.db_path = str(self.root / "test.db")
        self.patches = [
            patch.object(database, "DB_DIR", str(self.root)),
            patch.object(database, "DB_PATH", self.db_path),
        ]
        for item in self.patches:
            item.start()
            self.addCleanup(item.stop)
        database.init_db()

    def test_builds_scene_keyframes_and_reuses_compatible_index(self):
        video_path = self.root / "scene-change.mp4"
        write_video(video_path)
        indexer = VideoIndexer(str(self.root / "indexes"))
        first = indexer.build_or_reuse(metadata(video_path), "balanced")
        second = indexer.build_or_reuse(metadata(video_path), "balanced")
        self.assertFalse(first.cache_hit)
        self.assertTrue(second.cache_hit)
        self.assertEqual(first.index_id, second.index_id)
        self.assertGreaterEqual(first.scene_count, 2)
        self.assertIn(15, first.keyframe_indices)
        manifest = json.loads(Path(first.manifest_path).read_text(encoding="utf-8"))
        self.assertEqual(manifest["model_manifest"]["device"], "cpu")
        self.assertTrue(all(Path(frame["image_path"]).is_file() for frame in manifest["frames"]))
        with database.get_db_connection() as conn:
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM media_assets").fetchone()[0], 1)
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM video_indexes").fetchone()[0], 1)

    def test_different_modes_create_compatible_parallel_indexes(self):
        video_path = self.root / "modes.mp4"
        write_video(video_path)
        indexer = VideoIndexer(str(self.root / "indexes"))
        fast = indexer.build_or_reuse(metadata(video_path), "fast")
        thorough = indexer.build_or_reuse(metadata(video_path), "thorough")
        self.assertNotEqual(fast.index_id, thorough.index_id)
        self.assertGreater(len(thorough.keyframe_indices), len(fast.keyframe_indices))
        with database.get_db_connection() as conn:
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM media_assets").fetchone()[0], 1)
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM video_indexes").fetchone()[0], 2)

    def test_missing_empty_and_invalid_metadata_fail_honestly(self):
        missing = self.root / "missing.mp4"
        with self.assertRaisesRegex(ValueError, "empty or missing"):
            VideoIndexer(str(self.root / "indexes")).build_or_reuse(VideoMetadata(
                filename="missing.mp4", filepath=str(missing), duration_seconds=1, frame_count=1,
                fps=1, width=1, height=1, codec="", file_size_mb=0, creation_timestamp=""
            ))
        empty = self.root / "empty.mp4"
        empty.write_bytes(b"")
        with self.assertRaisesRegex(ValueError, "empty or missing"):
            VideoIndexer(str(self.root / "indexes")).build_or_reuse(VideoMetadata(
                filename="empty.mp4", filepath=str(empty), duration_seconds=1, frame_count=1,
                fps=1, width=1, height=1, codec="", file_size_mb=0, creation_timestamp=""
            ))


if __name__ == "__main__":
    unittest.main()
