import pytest

from scripts.evaluation_metrics import (
    average_precision, box_iou, detection_ap, greedy_match, levenshtein,
    precision_recall_f1, wilson_interval,
)
from scripts.evaluate_uc3m_alpr import annotation, masked_edit_distance, search_metrics


def test_box_and_greedy_matching():
    assert box_iou([0, 0, 10, 10], [0, 0, 10, 10]) == 1.0
    matches, unmatched_predictions, unmatched_truths = greedy_match(
        [[0, 0, 10, 10], [20, 20, 30, 30]], [[0, 0, 10, 10]], .5,
    )
    assert matches == [(0, 0, 1.0)]
    assert unmatched_predictions == [1]
    assert unmatched_truths == []


def test_ocr_and_summary_metrics():
    assert levenshtein("ABC123", "ABC128") == 1
    assert precision_recall_f1(8, 2, 2)["f1"] == pytest.approx(.8)
    low, high = wilson_interval(80, 100)
    assert low < .8 < high


def test_average_precision_and_class_aware_detection_ap():
    assert average_precision([(0.9, True), (0.8, False)], 1) == 1.0
    predictions = {1: [
        {"bbox": [0, 0, 10, 10], "confidence": .9, "class": "car"},
        {"bbox": [20, 20, 30, 30], "confidence": .8, "class": "truck"},
    ]}
    truths = {1: [{"bbox": [0, 0, 10, 10], "class": "car"}]}
    ap, count = detection_ap(predictions, truths, .5, "car")
    assert ap == 1.0
    assert count == 1


def test_uc3m_annotation_excludes_occluded_text_from_exact_ocr(tmp_path):
    label = tmp_path / "one.json"
    label.write_text(
        '{"imagePath":"one.jpg","lps":['
        '{"lp_id":"AD-1234ABC","poly_coord":[[1,2],[11,2],[11,7],[1,7]]},'
        '{"lp_id":"AN-12*4ABC","poly_coord":[[20,2],[30,2],[30,7],[20,7]]}'
        ']}'
    )
    plates, image_name = annotation(label)
    assert image_name == "one.jpg"
    assert plates[0]["bbox"] == [1.0, 2.0, 11.0, 7.0]
    assert plates[0]["fully_readable"] is True
    assert plates[0]["template"] == "1234ABC"
    assert plates[1]["text"] == "124ABC"
    assert plates[1]["template"] == "12*4ABC"
    assert plates[1]["fully_readable"] is False
    assert masked_edit_distance("12*4ABC", "1234ABC") == 0
    assert masked_edit_distance("12*4ABC", "1234ABX") == 1


def test_exact_and_partial_search_measure_false_retrievals():
    report = search_metrics([
        {"key": "one", "templates": ["AB*D123"], "observed": ["ABCD123"]},
        {"key": "two", "templates": ["WX*Z999"], "observed": ["ABCD888"]},
    ], partial_length=2)
    assert report["exact"]["available"] is False
    assert report["partial_2_character"]["false_positive"] >= 1
