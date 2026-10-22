import pytest

from scripts.evaluate_parseq_plate_ocr import confidence_bins


def test_confidence_bins_separate_confidence_from_measured_accuracy():
    rows = [
        {"confidence": .92, "observed": "ABC123", "expected": "ABC123"},
        {"confidence": .99, "observed": "ABC128", "expected": "ABC123"},
        {"confidence": .44, "observed": "XYZ", "expected": "XYZ"},
    ]
    bins = confidence_bins(rows)
    high = next(item for item in bins if item["low"] == .9)
    assert high["mean_confidence"] == pytest.approx(.955)
    assert high["exact_accuracy"] == .5
