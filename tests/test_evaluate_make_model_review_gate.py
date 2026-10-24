import pytest

from scripts.evaluate_make_model_review_gate import choose_threshold, score


def test_threshold_maximizes_coverage_at_requested_precision():
    selected = choose_threshold([.9, .8, .7, .6], [True, True, True, False], .95)
    assert selected["threshold"] == pytest.approx(.7)
    assert selected["coverage"] == pytest.approx(.75)


def test_score_separates_accepted_accuracy_from_overall_coverage():
    result = score([.9, .8, .4], [True, False, False], .7)
    assert result["accepted"] == 2
    assert result["accepted_make_model_accuracy"] == pytest.approx(.5)
    assert result["review_rate"] == pytest.approx(1 / 3)
