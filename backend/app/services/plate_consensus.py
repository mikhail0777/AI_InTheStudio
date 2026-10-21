"""Auditable multi-frame licence-plate candidate ranking.

Raw OCR strings remain unchanged.  Normalization removes display punctuation,
while common OCR confusions are exposed as review metadata and never silently
rewrite a candidate into a confirmed plate.
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from typing import Iterable

from app.services.license_plate_reader import normalize_plate, plate_similarity


@dataclass(frozen=True)
class RankedPlateCandidate:
    text: str
    distinct_frames: int
    observation_count: int
    weighted_support: float
    best_confidence: float
    frame_indices: tuple[int, ...]

    def as_dict(self) -> dict:
        return {
            "text": self.text,
            "distinct_frames": self.distinct_frames,
            "observation_count": self.observation_count,
            "weighted_support": round(self.weighted_support, 6),
            "best_confidence": round(self.best_confidence, 6),
            "frame_indices": list(self.frame_indices),
        }


def _bounded(value, default=0.0) -> float:
    try:
        return max(0.0, min(1.0, float(value)))
    except (TypeError, ValueError):
        return default


def rank_plate_candidates(observations: Iterable[dict], *, top_k: int = 5) -> list[RankedPlateCandidate]:
    """Rank exact OCR strings with at most one vote per text and frame.

    Each observation may contain a ``candidates`` list (raw and enhanced OCR
    variants) or the legacy top-level ``text``/``confidence`` pair.  A frame
    with many enhancement variants cannot outvote independent frames.
    """
    if top_k < 1:
        raise ValueError("top_k must be at least 1.")
    by_text: dict[str, list[tuple[int, float, float]]] = defaultdict(list)
    best_by_text_and_frame: dict[tuple[str, int], tuple[float, float]] = {}
    observation_counts: dict[str, int] = defaultdict(int)
    for fallback_index, observation in enumerate(observations):
        frame_index = int(observation.get("frame_idx", fallback_index))
        quality = _bounded(observation.get("quality_score"), .5)
        candidates = observation.get("candidates") or [{
            "text": observation.get("text", ""),
            "confidence": observation.get("confidence", 0.0),
        }]
        best_in_frame: dict[str, tuple[float, float]] = {}
        for candidate in candidates:
            text = normalize_plate(str(candidate.get("text") or ""))
            if not 3 <= len(text) <= 10:
                continue
            confidence = _bounded(candidate.get("confidence"))
            # Quality helps select evidence but can never turn weak OCR into a
            # high-confidence identity by itself.
            support = confidence * (.7 + .3 * quality)
            observation_counts[text] += 1
            current = best_in_frame.get(text)
            if current is None or support > current[0]:
                best_in_frame[text] = (support, confidence)
        for text, (support, confidence) in best_in_frame.items():
            key = (text, frame_index)
            current = best_by_text_and_frame.get(key)
            if current is None or support > current[0]:
                best_by_text_and_frame[key] = (support, confidence)
    for (text, frame_index), (support, confidence) in best_by_text_and_frame.items():
        by_text[text].append((frame_index, support, confidence))

    ranked = [RankedPlateCandidate(
        text=text,
        distinct_frames=len({item[0] for item in votes}),
        observation_count=observation_counts[text],
        weighted_support=sum(item[1] for item in votes),
        best_confidence=max(item[2] for item in votes),
        frame_indices=tuple(sorted({item[0] for item in votes})),
    ) for text, votes in by_text.items()]
    ranked.sort(key=lambda item: (
        item.distinct_frames, item.weighted_support, item.best_confidence, item.text
    ), reverse=True)
    return ranked[:top_k]


def build_plate_consensus(observations: Iterable[dict], *, top_k: int = 5) -> dict:
    """Return a transparent consensus decision and ranked alternatives."""
    ranked = rank_plate_candidates(observations, top_k=top_k)
    if not ranked:
        return {
            "selected_plate": None, "state": "uncertain", "reason": "no_valid_candidates",
            "ranked_candidates": [], "confusable_alternatives": [],
        }
    winner = ranked[0]
    runner_up = ranked[1] if len(ranked) > 1 else None
    tied = bool(runner_up and (
        runner_up.distinct_frames == winner.distinct_frames
        and abs(runner_up.weighted_support - winner.weighted_support) < .15
    ))
    if tied:
        state, reason = "conflicting", "competing_candidates_have_similar_support"
    elif winner.distinct_frames >= 2:
        state, reason = "exact_consensus", "same_exact_string_on_independent_frames"
    else:
        state, reason = "uncertain", "single_frame_support"
    confusable = [item.text for item in ranked[1:] if plate_similarity(item.text, winner.text) >= .90]
    return {
        "selected_plate": winner.text,
        "state": state,
        "reason": reason,
        "ranked_candidates": [item.as_dict() for item in ranked],
        "confusable_alternatives": confusable,
    }
