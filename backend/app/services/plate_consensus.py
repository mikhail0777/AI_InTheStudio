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
from app.services.plate_profiles import PlateRegionProfile, assess_candidate_format, get_plate_profile


@dataclass(frozen=True)
class RankedPlateCandidate:
    text: str
    raw_texts: tuple[str, ...]
    distinct_frames: int
    observation_count: int
    weighted_support: float
    best_confidence: float
    frame_indices: tuple[int, ...]
    format_state: str = "not_applied"
    matched_formats: tuple[str, ...] = ()
    format_ranking_contribution: float = 0.0

    def as_dict(self) -> dict:
        return {
            "text": self.text,
            "normalized_text": self.text,
            "raw_texts": list(self.raw_texts),
            "distinct_frames": self.distinct_frames,
            "observation_count": self.observation_count,
            "weighted_support": round(self.weighted_support, 6),
            "best_confidence": round(self.best_confidence, 6),
            "frame_indices": list(self.frame_indices),
            "format_state": self.format_state,
            "matched_formats": list(self.matched_formats),
            "format_ranking_contribution": self.format_ranking_contribution,
        }


def _bounded(value, default=0.0) -> float:
    try:
        return max(0.0, min(1.0, float(value)))
    except (TypeError, ValueError):
        return default


def rank_plate_candidates(
    observations: Iterable[dict], *, top_k: int = 5,
    profile: str | PlateRegionProfile | None = None,
    plate_type: str | None = None, layout: str | None = None,
) -> list[RankedPlateCandidate]:
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
    raw_texts: dict[str, set[str]] = defaultdict(set)
    for fallback_index, observation in enumerate(observations):
        frame_index = int(observation.get("frame_idx", fallback_index))
        quality = _bounded(observation.get("quality_score"), .5)
        candidates = observation.get("candidates") or [{
            "text": observation.get("text", ""),
            "confidence": observation.get("confidence", 0.0),
        }]
        best_in_frame: dict[str, tuple[float, float]] = {}
        for candidate in candidates:
            raw_text = str(candidate.get("text") or "")
            text = normalize_plate(raw_text)
            if not 3 <= len(text) <= 10:
                continue
            confidence = _bounded(candidate.get("confidence"))
            # Quality helps select evidence but can never turn weak OCR into a
            # high-confidence identity by itself.
            support = confidence * (.7 + .3 * quality)
            observation_counts[text] += 1
            raw_texts[text].add(raw_text)
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

    ranked = []
    for text, votes in by_text.items():
        format_assessment = assess_candidate_format(
            text, profile, plate_type=plate_type, layout=layout,
        )
        ranked.append(RankedPlateCandidate(
            text=text, raw_texts=tuple(sorted(raw_texts[text])),
            distinct_frames=len({item[0] for item in votes}),
            observation_count=observation_counts[text],
            weighted_support=sum(item[1] for item in votes),
            best_confidence=max(item[2] for item in votes),
            frame_indices=tuple(sorted({item[0] for item in votes})),
            format_state=format_assessment["state"],
            matched_formats=tuple(format_assessment["matched_formats"]),
            format_ranking_contribution=format_assessment["contribution"],
        ))
    ranked.sort(key=lambda item: (
        item.distinct_frames,
        item.weighted_support + item.format_ranking_contribution,
        item.weighted_support, item.best_confidence, item.text,
    ), reverse=True)
    return ranked[:top_k]


def build_plate_consensus(
    observations: Iterable[dict], *, top_k: int = 5,
    profile: str | PlateRegionProfile | None = None,
    plate_type: str | None = None, layout: str | None = None,
) -> dict:
    """Return a transparent consensus decision and ranked alternatives."""
    selected_profile = get_plate_profile(profile)
    ranked = rank_plate_candidates(
        observations, top_k=top_k, profile=selected_profile,
        plate_type=plate_type, layout=layout,
    )
    if not ranked:
        return {
            "selected_plate": None, "state": "uncertain", "reason": "no_valid_candidates",
            "ranked_candidates": [], "confusable_alternatives": [], "near_match_groups": [],
            "requires_review": True, "decision_score": 0.0,
            "region_profile": selected_profile.name,
        }
    winner = ranked[0]
    runner_up = ranked[1] if len(ranked) > 1 else None
    tied = bool(runner_up and (
        runner_up.distinct_frames == winner.distinct_frames
        and abs(runner_up.weighted_support - winner.weighted_support) < .15
    ))
    sufficient_evidence = (
        winner.distinct_frames >= 2
        and winner.best_confidence >= .5
        and winner.weighted_support >= .8
    )
    if tied:
        state, reason = "conflicting", "competing_candidates_have_similar_support"
    elif sufficient_evidence:
        state, reason = "exact_consensus", "same_exact_string_on_independent_frames"
    elif winner.distinct_frames >= 2:
        state, reason = "uncertain", "repeated_reading_has_insufficient_ocr_support"
    else:
        state, reason = "uncertain", "single_frame_support"
    if selected_profile.name != "unknown" and winner.format_state != "supported":
        state = "uncertain"
        reason = f"regional_format_{winner.format_state}_requires_review"
    confusable = [item.text for item in ranked[1:] if plate_similarity(item.text, winner.text) >= .90]
    near_match_groups = []
    remaining = list(ranked)
    while remaining:
        anchor = remaining.pop(0)
        members = [anchor]
        others = []
        for candidate in remaining:
            (members if plate_similarity(candidate.text, anchor.text) >= .80 else others).append(candidate)
        remaining = others
        if len(members) > 1:
            near_match_groups.append({
                "anchor": anchor.text,
                "candidates": [item.text for item in members],
                "distinct_frames": len({frame for item in members for frame in item.frame_indices}),
                "weighted_support": round(sum(item.weighted_support for item in members), 6),
                "review_only": True,
            })
    average_support = winner.weighted_support / max(1, winner.distinct_frames)
    runner_support = runner_up.weighted_support if runner_up else 0.0
    margin = max(0.0, winner.weighted_support - runner_support)
    decision_score = min(1.0, average_support) * min(1.0, winner.distinct_frames / 2) * min(1.0, .5 + margin)
    return {
        "selected_plate": winner.text,
        "state": state,
        "reason": reason,
        "ranked_candidates": [item.as_dict() for item in ranked],
        "confusable_alternatives": confusable,
        "near_match_groups": near_match_groups,
        "requires_review": state != "exact_consensus",
        "decision_score": round(decision_score, 6),
        "region_profile": selected_profile.name,
        "plate_type": plate_type,
        "layout": layout,
        "review_decision": "auto_accept" if state == "exact_consensus" else "requires_review",
        "decision_policy": {
            "minimum_independent_exact_frames": 2,
            "minimum_best_ocr_confidence": .5,
            "minimum_weighted_support": .8,
            "near_matches_are_review_only": True,
            "regional_formats_rank_candidates_but_never_rewrite_text": True,
        },
    }
