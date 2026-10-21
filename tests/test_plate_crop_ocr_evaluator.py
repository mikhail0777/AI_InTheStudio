import pytest

from scripts.evaluate_plate_crop_ocr import summarize


def test_summarize_reports_exact_topk_and_character_metrics():
    report = summarize([
        {"expected": "ABC123", "top1": "ABC123", "candidates": ["ABC123"]},
        {"expected": "XYZ789", "top1": "XYZ780", "candidates": ["XYZ780", "XYZ789"]},
        {"expected": "CAR555", "top1": "", "candidates": []},
    ])
    assert report["eligible_plate_crops"] == 3
    assert report["read_coverage"] == pytest.approx(2 / 3)
    assert report["top1_exact_plate_accuracy"] == pytest.approx(1 / 3)
    assert report["topk_exact_plate_accuracy"] == pytest.approx(2 / 3)
    assert report["character_edits"] == 7
    assert report["character_error_rate"] == pytest.approx(7 / 18)
