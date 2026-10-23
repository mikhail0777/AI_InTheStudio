from scripts.evaluate_external_vmmr_classifier import (
    benchmark_class_for_prediction,
    normalize,
)


def test_normalize_handles_case_and_separators():
    assert normalize("Land_Rover  Range Rover") == "land rover range rover"


def test_prediction_maps_to_matching_benchmark_range():
    classes = [
        {"class_id": 0, "make": "Ford", "model": "Explorer", "year_start": 2001, "year_end": 2003},
        {"class_id": 1, "make": "Ford", "model": "Explorer", "year_start": 2004, "year_end": 2006},
    ]
    prediction = {"make": "ford", "model": "explorer", "year": 2005}
    assert benchmark_class_for_prediction(prediction, classes) == 1


def test_prediction_outside_supported_classes_is_unknown():
    classes = [
        {"class_id": 0, "make": "Ford", "model": "Explorer", "year_start": 2001, "year_end": 2003},
    ]
    prediction = {"make": "ford", "model": "explorer", "year": 2020}
    assert benchmark_class_for_prediction(prediction, classes) is None
