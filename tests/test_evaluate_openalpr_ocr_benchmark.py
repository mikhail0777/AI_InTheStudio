from scripts.evaluate_openalpr_ocr_benchmark import select_rows, split_rows, summarize


def test_selection_is_deterministic_and_bounded():
    rows = [{"file": str(index)} for index in range(10)]
    assert select_rows(rows, 4, 7) == select_rows(rows, 4, 7)
    assert len(select_rows(rows, 4, 7)) == 4


def test_split_keeps_development_and_final_disjoint():
    rows = [{"file": str(index)} for index in range(10)]
    development, final = split_rows(rows, 4, 7)
    assert len(development) == 4
    assert len(final) == 6
    assert {row["file"] for row in development}.isdisjoint(row["file"] for row in final)


def test_summary_reports_exact_and_character_accuracy():
    report = summarize([
        {"expected": "ABC123", "predicted": "ABC123", "candidates": ["ABC123"], "confidence": .9998},
        {"expected": "XYZ789", "predicted": "XYZ78", "candidates": ["XYZ78", "XYZ789"], "confidence": .9},
    ], auto_accept_confidence=.9995)
    assert report["exact_matches"] == 1
    assert report["exact_plate_accuracy"] == 0.5
    assert report["character_edits"] == 1
    assert report["character_accuracy"] == 11 / 12
    assert report["topk_exact_matches"] == 2
    assert report["topk_exact_plate_accuracy"] == 1.0
    assert report["operational_acceptance"]["accepted"] == 1
    assert report["operational_acceptance"]["accepted_exact_matches"] == 1
    assert report["operational_acceptance"]["sent_to_review"] == 1
