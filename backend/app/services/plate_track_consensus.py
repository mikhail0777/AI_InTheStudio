"""Adaptive, auditable frame selection for multi-frame plate OCR.

The selector deliberately operates on already-captured plate observations.  It
does not know the expected plate text, so frame selection cannot be biased
toward a plate supplied by an operator.  Original observations remain intact;
the returned selection metadata records which independent frames contributed
to the consensus decision.
"""
from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Iterable

from app.services.plate_consensus import build_plate_consensus
from app.services.plate_profiles import PlateRegionProfile


@dataclass(frozen=True)
class SelectedPlateFrames:
    observations: tuple[dict, ...]
    input_observations: int
    distinct_input_frames: int
    selected_frame_indices: tuple[int, ...]
    discarded_frame_indices: tuple[int, ...]
    duration_seconds: float
    frame_budget: int

    def as_dict(self) -> dict:
        return {
            "input_observations": self.input_observations,
            "distinct_input_frames": self.distinct_input_frames,
            "selected_frames": len(self.selected_frame_indices),
            "selected_frame_indices": list(self.selected_frame_indices),
            "discarded_frame_indices": list(self.discarded_frame_indices),
            "duration_seconds": round(self.duration_seconds, 6),
            "frame_budget": self.frame_budget,
            "policy": {
                "name": "adaptive-quality-temporal-diversity-v1",
                "fixed_frame_count": False,
                "expected_plate_text_used": False,
                "one_observation_per_source_frame": True,
            },
        }


def _bounded(value, default=0.0) -> float:
    try:
        return max(0.0, min(1.0, float(value)))
    except (TypeError, ValueError):
        return default


def plate_observation_score(observation: dict) -> float:
    """Score evidence quality without considering the recognized text."""
    quality = _bounded(observation.get("quality_score"), .5)
    candidates = observation.get("candidates") or []
    confidence = max(
        (_bounded(candidate.get("confidence")) for candidate in candidates),
        default=_bounded(observation.get("confidence")),
    )
    metrics = observation.get("quality_metrics") or {}
    width = max(0.0, float(metrics.get("width", 0) or 0))
    height = max(0.0, float(metrics.get("height", 0) or 0))
    # A 160x40 crop is large enough that additional pixels should not dominate
    # sharpness, exposure, and OCR evidence quality.
    size = min(1.0, math.sqrt(width * height) / 80.0)
    return .60 * quality + .25 * confidence + .15 * size


def adaptive_frame_budget(
    distinct_frames: int, duration_seconds: float, *, minimum_frames: int = 3,
    maximum_frames: int = 10, target_frames_per_second: float = 2.0,
) -> int:
    """Choose more evidence for longer tracks without imposing a fixed count."""
    if minimum_frames < 1 or maximum_frames < minimum_frames:
        raise ValueError("Frame limits must satisfy 1 <= minimum <= maximum.")
    if target_frames_per_second <= 0:
        raise ValueError("target_frames_per_second must be positive.")
    if distinct_frames <= 0:
        return 0
    adaptive = max(minimum_frames, math.ceil(max(0.0, duration_seconds) * target_frames_per_second) + 1)
    return min(distinct_frames, maximum_frames, adaptive)


def select_plate_track_frames(
    observations: Iterable[dict], *, minimum_frames: int = 3,
    maximum_frames: int = 10, target_frames_per_second: float = 2.0,
) -> SelectedPlateFrames:
    """Select clear, temporally diverse plate observations from a vehicle track.

    Duplicate detections or preprocessing variants from the same source frame
    can contribute only once.  The first selected frame is the clearest.  Each
    later choice balances image quality with distance from frames already
    selected, preventing a burst of adjacent blurry frames from dominating.
    """
    supplied = list(observations)
    best_by_frame: dict[int, dict] = {}
    for fallback, observation in enumerate(supplied):
        frame_idx = int(observation.get("frame_idx", fallback))
        existing = best_by_frame.get(frame_idx)
        if existing is None or plate_observation_score(observation) > plate_observation_score(existing):
            best_by_frame[frame_idx] = observation
    candidates = sorted(
        best_by_frame.values(),
        key=lambda item: (float(item.get("timestamp_seconds", 0.0)), int(item.get("frame_idx", 0))),
    )
    if not candidates:
        return SelectedPlateFrames((), len(supplied), 0, (), (), 0.0, 0)
    timestamps = [float(item.get("timestamp_seconds", 0.0)) for item in candidates]
    duration = max(timestamps) - min(timestamps)
    budget = adaptive_frame_budget(
        len(candidates), duration, minimum_frames=minimum_frames,
        maximum_frames=maximum_frames, target_frames_per_second=target_frames_per_second,
    )
    if len(candidates) <= budget:
        selected = candidates
    else:
        remaining = list(candidates)
        first = max(remaining, key=lambda item: (
            plate_observation_score(item), -int(item.get("frame_idx", 0)),
        ))
        selected = [first]
        remaining.remove(first)
        time_scale = max(duration, 1e-6)
        while remaining and len(selected) < budget:
            def selection_score(item):
                timestamp = float(item.get("timestamp_seconds", 0.0))
                distance = min(
                    abs(timestamp - float(chosen.get("timestamp_seconds", 0.0)))
                    for chosen in selected
                ) / time_scale
                return .70 * plate_observation_score(item) + .30 * min(1.0, distance * budget)

            chosen = max(remaining, key=lambda item: (
                selection_score(item), plate_observation_score(item),
                -int(item.get("frame_idx", 0)),
            ))
            selected.append(chosen)
            remaining.remove(chosen)
        selected.sort(key=lambda item: (
            float(item.get("timestamp_seconds", 0.0)), int(item.get("frame_idx", 0)),
        ))
    selected_indices = tuple(int(item.get("frame_idx", 0)) for item in selected)
    discarded = tuple(sorted(set(best_by_frame) - set(selected_indices)))
    return SelectedPlateFrames(
        tuple(selected), len(supplied), len(best_by_frame), selected_indices,
        discarded, duration, budget,
    )


def build_track_plate_consensus(
    observations: Iterable[dict], *, top_k: int = 5,
    profile: str | PlateRegionProfile | None = None,
    plate_type: str | None = None, layout: str | None = None,
    minimum_frames: int = 3, maximum_frames: int = 10,
    target_frames_per_second: float = 2.0,
) -> tuple[dict, SelectedPlateFrames]:
    """Select track evidence and build the existing conservative consensus."""
    selection = select_plate_track_frames(
        observations, minimum_frames=minimum_frames, maximum_frames=maximum_frames,
        target_frames_per_second=target_frames_per_second,
    )
    consensus = build_plate_consensus(
        selection.observations, top_k=top_k, profile=profile,
        plate_type=plate_type, layout=layout,
    )
    consensus["frame_selection"] = selection.as_dict()
    return consensus, selection
