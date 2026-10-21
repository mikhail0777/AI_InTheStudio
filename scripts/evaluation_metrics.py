"""Dependency-free detection and OCR metrics used by reproducible benchmarks."""
from __future__ import annotations

from collections import defaultdict
import math
from typing import Iterable, Sequence


def box_iou(left: Sequence[float], right: Sequence[float]) -> float:
    x1, y1 = max(left[0], right[0]), max(left[1], right[1])
    x2, y2 = min(left[2], right[2]), min(left[3], right[3])
    intersection = max(0.0, x2 - x1) * max(0.0, y2 - y1)
    left_area = max(0.0, left[2] - left[0]) * max(0.0, left[3] - left[1])
    right_area = max(0.0, right[2] - right[0]) * max(0.0, right[3] - right[1])
    union = left_area + right_area - intersection
    return intersection / union if union > 0 else 0.0


def levenshtein(left: str, right: str) -> int:
    if len(left) < len(right):
        left, right = right, left
    previous = list(range(len(right) + 1))
    for row, left_char in enumerate(left, start=1):
        current = [row]
        for column, right_char in enumerate(right, start=1):
            current.append(min(
                current[-1] + 1,
                previous[column] + 1,
                previous[column - 1] + (left_char != right_char),
            ))
        previous = current
    return previous[-1]


def precision_recall_f1(tp: int, fp: int, fn: int) -> dict[str, float | int]:
    precision = tp / (tp + fp) if tp + fp else 0.0
    recall = tp / (tp + fn) if tp + fn else 0.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    return {
        "true_positive": tp, "false_positive": fp, "false_negative": fn,
        "precision": precision, "recall": recall, "f1": f1,
        "precision_wilson_95": wilson_interval(tp, tp + fp),
        "recall_wilson_95": wilson_interval(tp, tp + fn),
    }


def wilson_interval(successes: int, total: int, z: float = 1.959963984540054) -> list[float]:
    """Return a two-sided Wilson score interval for a binomial proportion."""
    if total <= 0:
        return [0.0, 0.0]
    proportion = successes / total
    denominator = 1 + z * z / total
    centre = (proportion + z * z / (2 * total)) / denominator
    margin = z * math.sqrt(
        proportion * (1 - proportion) / total + z * z / (4 * total * total)
    ) / denominator
    return [max(0.0, centre - margin), min(1.0, centre + margin)]


def greedy_match(predictions: Sequence[Sequence[float]], truths: Sequence[Sequence[float]],
                 threshold: float) -> tuple[list[tuple[int, int, float]], list[int], list[int]]:
    candidates = sorted(
        ((box_iou(pred, truth), pred_index, truth_index)
         for pred_index, pred in enumerate(predictions)
         for truth_index, truth in enumerate(truths)),
        reverse=True,
    )
    used_predictions: set[int] = set()
    used_truths: set[int] = set()
    matches = []
    for overlap, pred_index, truth_index in candidates:
        if overlap < threshold:
            break
        if pred_index in used_predictions or truth_index in used_truths:
            continue
        used_predictions.add(pred_index)
        used_truths.add(truth_index)
        matches.append((pred_index, truth_index, overlap))
    return (
        matches,
        [index for index in range(len(predictions)) if index not in used_predictions],
        [index for index in range(len(truths)) if index not in used_truths],
    )


def average_precision(records: Iterable[tuple[float, bool]], ground_truth_count: int) -> float:
    """101-point interpolated AP for confidence-labelled prediction records."""
    if ground_truth_count <= 0:
        return 0.0
    ordered = sorted(records, key=lambda item: item[0], reverse=True)
    tp = fp = 0
    points: list[tuple[float, float]] = []
    for _, correct in ordered:
        tp += int(correct)
        fp += int(not correct)
        points.append((tp / ground_truth_count, tp / (tp + fp)))
    return sum(
        max((precision for recall, precision in points if recall >= target), default=0.0)
        for target in (index / 100 for index in range(101))
    ) / 101


def detection_ap(predictions_by_image: dict[int | str, list[dict]],
                 truths_by_image: dict[int | str, list[dict]], iou_threshold: float,
                 class_name: str | None = None) -> tuple[float, int]:
    """Calculate class-aware AP while matching predictions within each image."""
    truth_count = 0
    truth_boxes: dict[int | str, list[Sequence[float]]] = {}
    for image_id, truths in truths_by_image.items():
        selected = [item["bbox"] for item in truths if class_name is None or item["class"] == class_name]
        truth_boxes[image_id] = selected
        truth_count += len(selected)
    used: dict[int | str, set[int]] = defaultdict(set)
    ranked = []
    for image_id, predictions in predictions_by_image.items():
        for prediction in predictions:
            if class_name is None or prediction["class"] == class_name:
                ranked.append((float(prediction["confidence"]), image_id, prediction["bbox"]))
    records = []
    for confidence, image_id, predicted_box in sorted(ranked, reverse=True):
        options = [
            (box_iou(predicted_box, truth), index)
            for index, truth in enumerate(truth_boxes.get(image_id, []))
            if index not in used[image_id]
        ]
        overlap, match_index = max(options, default=(0.0, -1))
        correct = overlap >= iou_threshold
        if correct:
            used[image_id].add(match_index)
        records.append((confidence, correct))
    return average_precision(records, truth_count), truth_count
