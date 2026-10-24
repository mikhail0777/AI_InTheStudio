from scripts.collapse_vehicle_make_model_manifest import collapse


def test_collapse_preserves_splits_and_remaps_year_classes():
    manifest = {
        "purpose": "frozen_research_benchmark",
        "dataset": {"name": "fixture", "limitation": "fixture"},
        "archive": {"path": "fixture.zip"},
        "classes": [
            {"class_id": 0, "make": "Ford", "model": "F-150", "year_start": 2001},
            {"class_id": 1, "make": "ford", "model": "f150", "year_start": 2021},
            {"class_id": 2, "make": "Kia", "model": "Forte", "year_start": 2021},
        ],
        "samples": [
            {"sample_id": "a", "class_id": 0, "split": "train"},
            {"sample_id": "b", "class_id": 1, "split": "test"},
            {"sample_id": "c", "class_id": 2, "split": "development"},
        ],
    }
    result = collapse(manifest)
    assert result["counts"] == {"classes": 2, "train": 1, "test": 1, "development": 1}
    assert [item["class_id"] for item in result["samples"]] == [0, 0, 1]
    assert result["samples"][1]["source_class_id"] == 1
