import pytest

from scripts.evaluate_vehicle_unknown_rejection import choose_threshold, score


def test_threshold_is_selected_from_development_only():
    result = choose_threshold([.95, .90, .85, .80], [.70, .60, .40], .75)
    assert result["threshold"] == pytest.approx(.80)
    assert result["known_acceptance"] == 1.0
    assert result["unknown_rejection"] == 1.0


def test_score_reports_false_unknown_assignments_and_review_rate():
    result = score([.9, .4], [0, 1], [0, 0], [.8, .3], .5)
    assert result["known_accepted"] == 1
    assert result["known_exact_and_accepted"] == 1
    assert result["unknown_rejected"] == 1
    assert result["false_exact_assignments_on_unknown"] == 1
    assert result["review_rate"] == pytest.approx(.5)
