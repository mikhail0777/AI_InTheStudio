"""Conservative multi-frame aggregation for vehicle make/model/year candidates."""
from __future__ import annotations

from collections import defaultdict
from typing import Iterable


def _bounded(value, default=0.0):
    try:
        return max(0.0, min(1.0, float(value)))
    except (TypeError, ValueError):
        return default


def _label(candidate):
    make = str(candidate.get("make") or "").strip()
    model = str(candidate.get("model") or "").strip()
    return make, model


def build_vehicle_attribute_consensus(observations: Iterable[dict], *, top_k=5) -> dict:
    """Rank make/model candidates with one vote per label and source frame.

    Year evidence is retained as a range.  A result remains unknown unless the
    same make/model has independent support and a clear lead over alternatives.
    """
    if top_k < 1:
        raise ValueError("top_k must be at least 1.")
    best_by_frame: dict[tuple[str, str, int], tuple[float, dict]] = {}
    for fallback, observation in enumerate(observations):
        frame_idx = int(observation.get("frame_idx", fallback))
        quality = _bounded(observation.get("quality_score"), .5)
        for candidate in observation.get("candidates") or []:
            make, model = _label(candidate)
            if not make or not model:
                continue
            confidence = _bounded(candidate.get("confidence"))
            support = confidence * (.7 + .3 * quality)
            key = (make.casefold(), model.casefold(), frame_idx)
            if key not in best_by_frame or support > best_by_frame[key][0]:
                best_by_frame[key] = (support, {**candidate, "make": make, "model": model})
    grouped = defaultdict(list)
    for (make_key, model_key, frame_idx), (support, candidate) in best_by_frame.items():
        grouped[(make_key, model_key)].append((frame_idx, support, candidate))
    ranked = []
    for votes in grouped.values():
        sample = votes[0][2]
        starts = [int(item[2]["year_start"]) for item in votes if item[2].get("year_start") is not None]
        ends = [int(item[2].get("year_end", item[2]["year_start"])) for item in votes
                if item[2].get("year_start") is not None]
        ranked.append({
            "make": sample["make"], "model": sample["model"],
            "year_start": min(starts) if starts else None,
            "year_end": max(ends) if ends else None,
            "distinct_frames": len(votes),
            "weighted_support": round(sum(item[1] for item in votes), 6),
            "best_confidence": round(max(_bounded(item[2].get("confidence")) for item in votes), 6),
            "frame_indices": sorted(item[0] for item in votes),
        })
    ranked.sort(key=lambda item: (
        item["distinct_frames"], item["weighted_support"], item["best_confidence"],
        item["make"], item["model"],
    ), reverse=True)
    ranked = ranked[:top_k]
    if not ranked:
        return {
            "state": "unknown", "selected": None, "ranked_candidates": [],
            "requires_review": True, "reason": "no_model_candidates",
        }
    winner = ranked[0]
    runner = ranked[1] if len(ranked) > 1 else None
    tied = bool(runner and runner["distinct_frames"] == winner["distinct_frames"]
                and abs(runner["weighted_support"] - winner["weighted_support"]) < .2)
    supported = winner["distinct_frames"] >= 2 and winner["best_confidence"] >= .5
    if tied:
        state, reason = "conflicting", "competing_make_model_candidates"
    elif supported:
        state, reason = "candidate_consensus", "same_make_model_on_independent_frames"
    else:
        state, reason = "unknown", "insufficient_independent_support"
    return {
        "state": state,
        "selected": winner if state == "candidate_consensus" else None,
        "ranked_candidates": ranked,
        "requires_review": state != "candidate_consensus",
        "reason": reason,
        "decision_policy": {
            "minimum_independent_frames": 2,
            "minimum_best_model_confidence": .5,
            "supports_unknown": True,
            "year_is_range": True,
        },
    }
