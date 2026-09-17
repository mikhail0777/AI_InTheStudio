"""Replaceable inference interfaces; implementations own no persistence."""
from typing import Iterable, List, Optional, Protocol, Sequence, runtime_checkable

from app.models.open_vocabulary import (
    EntityDetection, EntityTrack, EvidenceAssessment, ModelProvenance, SearchQuery,
)


class Provider(Protocol):
    @property
    def provenance(self) -> ModelProvenance: ...


@runtime_checkable
class QueryParser(Provider, Protocol):
    def parse(self, text: str) -> SearchQuery: ...


@runtime_checkable
class SceneSampler(Provider, Protocol):
    def plan(self, video_path: str, mode: str) -> Iterable[dict]: ...


@runtime_checkable
class EmbeddingProvider(Provider, Protocol):
    @property
    def dimension(self) -> int: ...
    def embed_images(self, image_paths: Sequence[str]) -> List[List[float]]: ...
    def embed_text(self, texts: Sequence[str]) -> List[List[float]]: ...


@runtime_checkable
class DetectionProvider(Provider, Protocol):
    def detect(self, frames: Sequence[object], vocabulary: Optional[Sequence[str]] = None,
               session_id: str = "") -> List[EntityDetection]: ...


@runtime_checkable
class GroundingProvider(Provider, Protocol):
    def ground(self, frames: Sequence[object], phrases: Sequence[str],
               session_id: str = "") -> List[EntityDetection]: ...


@runtime_checkable
class SegmentationProvider(Provider, Protocol):
    def segment(self, frames: Sequence[object], detections: Sequence[EntityDetection]) -> List[EntityDetection]: ...


@runtime_checkable
class TrackingProvider(Provider, Protocol):
    def update(self, detections: Sequence[EntityDetection]) -> None: ...
    def finalize(self) -> List[EntityTrack]: ...


@runtime_checkable
class ClipVerifier(Provider, Protocol):
    def verify(self, query: SearchQuery, clip_path: str, tracks: Sequence[EntityTrack]) -> List[EvidenceAssessment]: ...


@runtime_checkable
class RankingPolicy(Protocol):
    def score(self, query: SearchQuery, evidence: Sequence[EvidenceAssessment]) -> dict: ...
