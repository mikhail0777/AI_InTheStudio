import pytest

from scripts.evaluate_yolo_ocr_sequence import predicted_sequence, summarize


def test_prediction_order_and_threshold():
    boxes = [
        {"character": "2", "x": .7, "confidence": .8},
        {"character": "A", "x": .1, "confidence": .9},
        {"character": "1", "x": .5, "confidence": .4},
    ]
    assert predicted_sequence(boxes, .3) == "A12"
    assert predicted_sequence(boxes, .5) == "A2"


def test_sequence_summary_uses_exact_and_edit_distance_metrics():
    rows = [
        {"expected": "AB12", "predictions": [
            {"character": char, "x": index, "confidence": .9}
            for index, char in enumerate("AB12")
        ]},
        {"expected": "CAR7", "predictions": [
            {"character": char, "x": index, "confidence": .9}
            for index, char in enumerate("CAB7")
        ]},
    ]
    metrics = summarize(rows, .5)
    assert metrics["exact_plate_accuracy"] == .5
    assert metrics["character_error_rate"] == pytest.approx(1 / 8)
