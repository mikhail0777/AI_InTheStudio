import csv
from pathlib import Path

import pytest

from scripts.prepare_fastplateocr_dataset import prepare


def make_source(root: Path):
    (root / "data.yaml").parent.mkdir(parents=True, exist_ok=True)
    (root / "data.yaml").write_text("names: ['A', '1']\n", encoding="utf-8")
    for split in ("train", "valid", "test"):
        (root / split / "images").mkdir(parents=True)
        (root / split / "labels").mkdir(parents=True)
        (root / split / "images" / f"{split}.jpg").write_bytes(split.encode())
        (root / split / "labels" / f"{split}.txt").write_text(
            "0 .2 .5 .1 .5\n1 .8 .5 .1 .5\n", encoding="utf-8",
        )


def test_preparation_excludes_test_and_does_not_invent_regions(tmp_path):
    source, destination = tmp_path / "source", tmp_path / "prepared"
    make_source(source)
    manifest = prepare(source, destination)
    assert manifest["policy"]["source_test_excluded"]
    assert not (destination / "test").exists()
    with (destination / "train" / "annotations.csv").open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    assert rows == [{"image_path": "images/train.jpg", "plate_text": "A1"}]


def test_partial_region_mapping_is_rejected(tmp_path):
    source, destination = tmp_path / "source", tmp_path / "prepared"
    make_source(source)
    with pytest.raises(ValueError):
        prepare(source, destination, {"train.jpg": "Ontario"})
