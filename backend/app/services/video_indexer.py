"""Content-addressed, query-independent video indexing using CPU OpenCV primitives."""
from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
import uuid
from typing import Dict, List, Optional

import cv2
import numpy as np

from app import database
from app.models.schemas import VideoMetadata


INDEX_VERSION = "scene-keyframes-v1"
MODE_FPS = {"fast": 0.5, "balanced": 1.0, "thorough": 2.0}


@dataclass(frozen=True)
class VideoIndex:
    index_id: str
    media_id: str
    content_hash: str
    processing_mode: str
    keyframe_indices: List[int]
    scene_count: int
    clip_count: int
    manifest_path: str
    cache_hit: bool


def _sha256(path: str) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _config(mode: str) -> Dict[str, object]:
    if mode not in MODE_FPS:
        raise ValueError(f"Unsupported indexing mode: {mode}")
    config = {
        "index_version": INDEX_VERSION,
        "processing_mode": mode,
        "keyframe_fps": MODE_FPS[mode],
        "scene_probe_fps": float(os.environ.get("AIEYE_SCENE_PROBE_FPS", "2")),
        "scene_threshold": float(os.environ.get("AIEYE_SCENE_THRESHOLD", "0.18")),
        "clip_padding_seconds": float(os.environ.get("AIEYE_CLIP_PADDING_SECONDS", "2.5")),
    }
    if config["scene_probe_fps"] <= 0 or not 0 < config["scene_threshold"] <= 1:
        raise ValueError("Scene probe FPS must be positive and threshold must be in (0, 1].")
    if config["clip_padding_seconds"] <= 0:
        raise ValueError("Clip padding must be positive.")
    return config


def _config_hash(config: Dict[str, object]) -> str:
    encoded = json.dumps(config, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _scene_signature(frame) -> np.ndarray:
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    return cv2.resize(gray, (32, 18), interpolation=cv2.INTER_AREA).astype(np.float32) / 255.0


def _quality(frame) -> float:
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    sharpness = float(cv2.Laplacian(gray, cv2.CV_64F).var())
    return round(min(1.0, sharpness / 500.0), 4)


class VideoIndexer:
    def __init__(self, artifact_root: Optional[str] = None):
        self.artifact_root = Path(artifact_root) if artifact_root else Path(database.DB_DIR) / "indexes"

    @staticmethod
    def _load_complete(index_id: str, content_hash: str, mode: str, manifest_path: str) -> Optional[VideoIndex]:
        path = Path(manifest_path)
        if not path.is_file():
            return None
        try:
            manifest = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return None
        frame_paths = [Path(item["image_path"]) for item in manifest.get("frames", [])]
        if not frame_paths or not all(item.is_file() for item in frame_paths):
            return None
        return VideoIndex(
            index_id=index_id, media_id=manifest["media_id"], content_hash=content_hash,
            processing_mode=mode,
            keyframe_indices=[int(item["frame_idx"]) for item in manifest["frames"]],
            scene_count=len(manifest.get("scenes", [])), clip_count=len(manifest.get("clips", [])),
            manifest_path=str(path), cache_hit=True,
        )

    def build_or_reuse(self, video: VideoMetadata, mode: str = "balanced") -> VideoIndex:
        source = Path(video.filepath)
        if not source.is_file() or source.stat().st_size == 0:
            raise ValueError("Cannot index an empty or missing video.")
        if video.fps <= 0 or video.frame_count <= 0 or video.duration_seconds <= 0:
            raise ValueError("Cannot index video with invalid timing metadata.")
        config = _config(mode)
        config_hash = _config_hash(config)
        content_hash = _sha256(str(source))
        media_id = f"media_{content_hash[:24]}"
        with database.get_db_connection() as conn:
            conn.execute("BEGIN IMMEDIATE")
            conn.execute("""INSERT OR IGNORE INTO media_assets(media_id,content_hash,canonical_path,metadata)
                VALUES (?,?,?,?)""", (media_id, content_hash, str(source.resolve()), video.model_dump_json()))
            existing = conn.execute("""SELECT v.index_id,v.status,v.processing_mode,v.artifact_manifest_path
                FROM video_indexes v WHERE v.media_id=? AND v.config_hash=?""", (media_id, config_hash)).fetchone()
        if existing and existing["status"] == "complete" and existing["artifact_manifest_path"]:
            cached = self._load_complete(existing["index_id"], content_hash, existing["processing_mode"], existing["artifact_manifest_path"])
            if cached:
                return cached
        index_id = existing["index_id"] if existing else f"index_{uuid.uuid4().hex}"
        manifest_path = self.artifact_root / index_id / "manifest.json"
        model_manifest = {
            "scene_sampler": {"name": "opencv-frame-difference", "version": INDEX_VERSION},
            "opencv": cv2.__version__, "device": "cpu", "embeddings": None,
        }
        with database.get_db_connection() as conn:
            conn.execute("BEGIN IMMEDIATE")
            if existing:
                conn.execute("""UPDATE video_indexes SET status='building',model_manifest=?,
                    artifact_manifest_path=?,error_message=NULL,finished_at=NULL WHERE index_id=?""",
                    (json.dumps(model_manifest), str(manifest_path), index_id))
                conn.execute("DELETE FROM scenes WHERE index_id=?", (index_id,))
                conn.execute("DELETE FROM indexed_frames WHERE index_id=?", (index_id,))
                conn.execute("DELETE FROM indexed_clips WHERE index_id=?", (index_id,))
            else:
                conn.execute("""INSERT INTO video_indexes(index_id,media_id,status,processing_mode,config_hash,
                    index_version,model_manifest,artifact_manifest_path) VALUES (?,?,?,?,?,?,?,?)""",
                    (index_id, media_id, "building", mode, config_hash, INDEX_VERSION,
                     json.dumps(model_manifest), str(manifest_path)))
        try:
            return self._build(index_id, media_id, content_hash, video, config, model_manifest, manifest_path)
        except Exception as error:
            with database.get_db_connection() as conn:
                conn.execute("UPDATE video_indexes SET status='error',error_message=?,finished_at=CURRENT_TIMESTAMP WHERE index_id=?",
                             (str(error) or type(error).__name__, index_id))
            raise

    def _build(self, index_id, media_id, content_hash, video, config, model_manifest, manifest_path) -> VideoIndex:
        cap = cv2.VideoCapture(video.filepath)
        if not cap.isOpened():
            raise ValueError("The video could not be opened for indexing.")
        key_interval = max(1, round(video.fps / float(config["keyframe_fps"])))
        probe_interval = max(1, round(video.fps / float(config["scene_probe_fps"])))
        scene_threshold = float(config["scene_threshold"])
        scene_starts = [0]
        keyframes = {0, max(0, video.frame_count - 1)}
        previous_signature = None
        decoded = 0
        try:
            frame_idx = 0
            while frame_idx < video.frame_count:
                ok, frame = cap.read()
                if not ok or frame is None or frame.size == 0:
                    if decoded == 0:
                        raise ValueError("The video contains no decodable frames.")
                    break
                decoded += 1
                if frame_idx % key_interval == 0:
                    keyframes.add(frame_idx)
                if frame_idx % probe_interval == 0:
                    signature = _scene_signature(frame)
                    if previous_signature is not None:
                        difference = float(np.mean(np.abs(signature - previous_signature)))
                        if difference >= scene_threshold:
                            scene_starts.append(frame_idx)
                            keyframes.add(frame_idx)
                    previous_signature = signature
                frame_idx += 1
        finally:
            cap.release()
        if decoded == 0:
            raise ValueError("The video contains no decodable frames.")
        last_frame = decoded - 1
        keyframes = sorted(index for index in keyframes if index <= last_frame)
        scene_starts = sorted(set(index for index in scene_starts if index <= last_frame))
        scenes = []
        for position, start_idx in enumerate(scene_starts):
            next_idx = scene_starts[position + 1] if position + 1 < len(scene_starts) else decoded
            scenes.append({
                "scene_id": f"scene_{position:05d}", "start_frame_idx": start_idx,
                "end_frame_idx": max(start_idx, next_idx - 1),
                "start_seconds": start_idx / video.fps,
                "end_seconds": min(video.duration_seconds, max(start_idx, next_idx - 1) / video.fps),
            })
        output_dir = manifest_path.parent / "frames"
        output_dir.mkdir(parents=True, exist_ok=True)
        cap = cv2.VideoCapture(video.filepath)
        frames = []
        try:
            for frame_idx in keyframes:
                cap.set(cv2.CAP_PROP_POS_FRAMES, frame_idx)
                ok, frame = cap.read()
                if not ok or frame is None or frame.size == 0:
                    raise ValueError(f"Video decode failed while writing keyframe {frame_idx}.")
                frame_id = f"frame_{frame_idx:09d}"
                image_path = output_dir / f"{frame_id}.jpg"
                if not cv2.imwrite(str(image_path), frame, [cv2.IMWRITE_JPEG_QUALITY, 90]):
                    raise OSError(f"Could not write indexed frame {frame_idx}.")
                scene = next(item for item in reversed(scenes) if item["start_frame_idx"] <= frame_idx)
                frames.append({
                    "frame_id": frame_id, "frame_idx": frame_idx,
                    "timestamp_seconds": frame_idx / video.fps, "scene_id": scene["scene_id"],
                    "image_path": str(image_path.resolve()), "quality_score": _quality(frame),
                })
        finally:
            cap.release()
        padding = float(config["clip_padding_seconds"])
        clips = []
        for position, frame in enumerate(frames):
            clips.append({
                "clip_id": f"clip_{position:05d}",
                "start_seconds": max(0.0, frame["timestamp_seconds"] - padding),
                "end_seconds": min(video.duration_seconds, frame["timestamp_seconds"] + padding),
                "representative_frame_id": frame["frame_id"], "artifact_path": None,
            })
        manifest = {
            "index_id": index_id, "media_id": media_id, "content_hash": content_hash,
            "config": config, "model_manifest": model_manifest,
            "source_metadata": video.model_dump(mode="json"),
            "scenes": scenes, "frames": frames, "clips": clips,
        }
        manifest_path.parent.mkdir(parents=True, exist_ok=True)
        temporary = manifest_path.with_suffix(".json.tmp")
        temporary.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
        os.replace(temporary, manifest_path)
        with database.get_db_connection() as conn:
            conn.execute("BEGIN IMMEDIATE")
            conn.executemany("INSERT INTO scenes(index_id,scene_id,start_seconds,end_seconds) VALUES (?,?,?,?)",
                             [(index_id, item["scene_id"], item["start_seconds"], item["end_seconds"]) for item in scenes])
            conn.executemany("""INSERT INTO indexed_frames(index_id,frame_id,frame_idx,timestamp_seconds,
                scene_id,image_path,quality_score,metadata) VALUES (?,?,?,?,?,?,?,?)""",
                [(index_id, item["frame_id"], item["frame_idx"], item["timestamp_seconds"], item["scene_id"],
                  item["image_path"], item["quality_score"], "{}") for item in frames])
            conn.executemany("""INSERT INTO indexed_clips(index_id,clip_id,start_seconds,end_seconds,
                representative_frame_id,artifact_path,metadata) VALUES (?,?,?,?,?,?,?)""",
                [(index_id, item["clip_id"], item["start_seconds"], item["end_seconds"],
                  item["representative_frame_id"], item["artifact_path"], "{}") for item in clips])
            conn.execute("UPDATE video_indexes SET status='complete',finished_at=CURRENT_TIMESTAMP,error_message=NULL WHERE index_id=?",
                         (index_id,))
        return VideoIndex(
            index_id=index_id, media_id=media_id, content_hash=content_hash,
            processing_mode=str(config["processing_mode"]), keyframe_indices=keyframes,
            scene_count=len(scenes), clip_count=len(clips), manifest_path=str(manifest_path), cache_hit=False,
        )
