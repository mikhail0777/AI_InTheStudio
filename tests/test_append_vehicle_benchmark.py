from copy import deepcopy

import pytest

from scripts.append_vehicle_benchmark import merge


def manifests():
    base = {
        "purpose": "frozen_research_benchmark",
        "dataset": {"name": "base"},
        "archive": {"path": "base.zip"},
        "classes": [{"class_id": 0, "make": "Ford", "model": "Escape", "year_start": 2013, "year_end": 2019}],
        "samples": [{"sample_id": "old", "class_id": 0, "split": "train"}],
    }
    addon = {
        "purpose": "frozen_commercially_reusable_vehicle_benchmark",
        "classes": [{"class_id": 0, "make": "Ford", "model": "Escape", "year_start": 2020, "year_end": 2026}],
        "samples": [
            {"sample_id": "new", "class_id": 0, "split": "test", "path": "new.jpg"},
            {"sample_id": "unknown", "class_id": None, "split": "unknown_test", "path": "u.jpg"},
        ],
    }
    return base, addon


def test_merge_preserves_old_ids_and_offsets_new_ids():
    base, addon = manifests()
    result = merge(base, addon)
    assert [item["class_id"] for item in result["classes"]] == [0, 1]
    assert [item["class_id"] for item in result["samples"]] == [0, 1, None]
    assert result["counts"]["unknown_test"] == 1


def test_merge_rejects_overlapping_year_answers():
    base, addon = manifests()
    overlapping = deepcopy(addon)
    overlapping["classes"][0]["year_start"] = 2018
    with pytest.raises(ValueError, match="Overlapping year labels"):
        merge(base, overlapping)
