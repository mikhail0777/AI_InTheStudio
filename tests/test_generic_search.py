import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import cv2
import numpy as np

from app import database
from app.models.open_vocabulary import EntityDetection, ModelProvenance
from app.models.schemas import VideoMetadata
from app.services.generic_search import OpenVocabularySearchManager, track_entities
from app.services.query_parser import StructuredQueryParser


PROVENANCE = ModelProvenance(provider="test", model_name="test", model_version="1", device="cpu")


def create_video(path: Path):
    writer = cv2.VideoWriter(str(path), cv2.VideoWriter_fourcc(*"mp4v"), 2, (96, 64))
    for _ in range(8):
        writer.write(np.zeros((64, 96, 3), dtype=np.uint8))
    writer.release()


class GenericSearchTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        for item in [patch.object(database, "DB_DIR", str(self.root)),
                     patch.object(database, "DB_PATH", str(self.root / "test.db"))]:
            item.start()
            self.addCleanup(item.stop)
        database.init_db()
        self.video_path = self.root / "source.mp4"
        create_video(self.video_path)
        self.frame_path = self.root / "frame.jpg"
        cv2.imwrite(str(self.frame_path), np.zeros((64, 96, 3), dtype=np.uint8))
        with database.get_db_connection() as conn:
            conn.execute("INSERT INTO sessions(session_id,status,index_id) VALUES ('s','analyzing','idx')")
            conn.execute("INSERT INTO media_assets(media_id,content_hash,canonical_path,metadata) VALUES ('m','hash',?, '{}')", (str(self.video_path),))
            conn.execute("""INSERT INTO video_indexes(index_id,media_id,status,processing_mode,config_hash,index_version,model_manifest)
                VALUES ('idx','m','complete','balanced','config','v1','{}')""")
            for frame_id, frame_idx, timestamp in (("f1", 1, .5), ("f2", 2, 1.0)):
                conn.execute("""INSERT INTO indexed_frames(index_id,frame_id,frame_idx,timestamp_seconds,scene_id,image_path,quality_score)
                    VALUES ('idx',?,?,?,?,?,.8)""", (frame_id, frame_idx, timestamp, "scene", str(self.frame_path)))
        self.video = VideoMetadata(
            filename="source.mp4", filepath=str(self.video_path), duration_seconds=4,
            frame_count=8, fps=2, width=96, height=64, codec="mp4v",
            file_size_mb=self.video_path.stat().st_size / 1024**2, creation_timestamp="",
        )

    def detection(self, detection_id, frame_id, frame_idx, timestamp, colors, bbox=None):
        return EntityDetection(
            detection_id=detection_id, frame_id=frame_id, frame_idx=frame_idx,
            timestamp_seconds=timestamp, label="car", bbox=bbox or [10, 10, 50, 50],
            confidence=.9, visibility=.8, crop_path=f"/evidence/s/{detection_id}.jpg",
            attributes={"colors": colors, "semantic_similarity": .4}, provenance=PROVENANCE,
        )

    def test_required_yellow_evidence_gates_strong_match(self):
        detections = [
            self.detection("d1", "f1", 1, .5, {"yellow": .8, "white": .1, "grey": .1}),
            self.detection("d2", "f2", 2, 1.0, {"yellow": .75, "white": .15, "grey": .1}),
        ]
        results = OpenVocabularySearchManager._rank(
            StructuredQueryParser().parse("a yellow car"), "q", "s", self.video,
            [detections], self.root / "evidence", PROVENANCE,
        )
        self.assertEqual(results[0].classification, "strong_match")
        self.assertEqual(results[0].evidence[1].assessment, "supported")
        self.assertTrue((self.root / results[0].clip_path.lstrip("/").replace("evidence/", "evidence/")).is_file())

    def test_non_yellow_car_is_not_promoted_by_entity_or_semantic_score(self):
        detections = [
            self.detection("d1", "f1", 1, .5, {"blue": .8, "white": .1, "grey": .1}),
            self.detection("d2", "f2", 2, 1.0, {"blue": .75, "white": .15, "grey": .1}),
        ]
        results = OpenVocabularySearchManager._rank(
            StructuredQueryParser().parse("a yellow car"), "q", "s", self.video,
            [detections], self.root / "evidence", PROVENANCE,
        )
        self.assertEqual(results[0].classification, "unlikely_match")
        self.assertEqual(results[0].evidence[1].assessment, "conflicting")

    def test_chromatic_body_color_survives_windows_and_highlights(self):
        detections = [
            self.detection("d1", "f1", 1, .5, {"red": .3, "black": .3, "grey": .25, "white": .15}),
            self.detection("d2", "f2", 2, 1.0, {"red": .28, "black": .32, "grey": .25, "white": .15}),
        ]
        results = OpenVocabularySearchManager._rank(
            StructuredQueryParser().parse("a red car"), "q", "s", self.video,
            [detections], self.root / "evidence", PROVENANCE,
        )
        self.assertEqual(results[0].classification, "strong_match")
        self.assertEqual(results[0].evidence[1].assessment, "supported")

    def test_adjacent_observations_are_deduplicated_into_one_track(self):
        detections = [
            self.detection("d1", "f1", 1, .5, {"yellow": .8}),
            self.detection("d2", "f2", 2, 1.0, {"yellow": .8}, [12, 10, 52, 50]),
        ]
        tracks = track_entities(detections)
        self.assertEqual(len(tracks), 1)
        self.assertEqual(len(tracks[0]), 2)


if __name__ == "__main__":
    unittest.main()
