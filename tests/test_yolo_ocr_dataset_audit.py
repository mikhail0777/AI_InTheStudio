from pathlib import Path

from scripts.audit_yolo_ocr_dataset import audit, filename_candidates, filename_truth, ordered_sequence


def write_dataset(root: Path) -> None:
    (root / "data.yaml").write_text("names: ['A', 'B', '1', '2']\n", encoding="utf-8")
    for split in ("train", "valid", "test"):
        (root / split / "images").mkdir(parents=True)
        (root / split / "labels").mkdir(parents=True)
    (root / "train" / "images" / "AB12_jpg.rf.abc.jpg").write_bytes(b"train")
    (root / "train" / "labels" / "AB12_jpg.rf.abc.txt").write_text(
        "0 .1 .5 .1 .4\n1 .3 .5 .1 .4\n2 .5 .5 .1 .4\n3 .7 .5 .1 .4\n",
        encoding="utf-8",
    )
    (root / "test" / "images" / "BA21_jpg.rf.def.jpg").write_bytes(b"test")
    (root / "test" / "labels" / "BA21_jpg.rf.def.txt").write_text(
        "1 .1 .5 .1 .4\n0 .3 .5 .1 .4\n3 .5 .5 .1 .4\n2 .7 .5 .1 .4\n",
        encoding="utf-8",
    )


def test_orders_single_and_two_row_character_boxes():
    boxes = [
        {"character": "2", "x": .6, "y": .7, "height": .2},
        {"character": "A", "x": .2, "y": .3, "height": .2},
        {"character": "1", "x": .4, "y": .7, "height": .2},
        {"character": "B", "x": .4, "y": .3, "height": .2},
    ]
    assert ordered_sequence(boxes) == "AB12"


def test_filename_truth_is_conservative():
    assert filename_truth(Path("ABC123_jpg.rf.abcdef.jpg")) == "ABC123"
    assert filename_candidates(Path("WRONG12_ABC1234_50_20_jpg.rf.abcdef.jpg")) == ["WRONG12", "ABC1234"]
    assert filename_truth(Path("ordinary_image_jpg.rf.abcdef.jpg")) is None


def test_audit_validates_labels_and_filename_cross_check(tmp_path):
    write_dataset(tmp_path)
    report = audit(tmp_path, compare_filename_truth=True)
    assert report["character_detection_evaluation_eligible"] is True
    assert report["exact_plate_sequence_evaluation_eligible"] is True
    assert report["splits"]["train"]["filename_truth"]["exact_match_rate"] == 1.0
    assert report["splits"]["test"]["character_instances"] == 4


def test_audit_rejects_cross_split_byte_duplicates(tmp_path):
    write_dataset(tmp_path)
    duplicate = tmp_path / "valid" / "images" / "AB12_jpg.rf.999.jpg"
    duplicate.write_bytes(b"train")
    (tmp_path / "valid" / "labels" / "AB12_jpg.rf.999.txt").write_text(
        "0 .1 .5 .1 .4\n", encoding="utf-8",
    )
    report = audit(tmp_path)
    assert report["character_detection_evaluation_eligible"] is False
    assert report["exact_plate_sequence_evaluation_eligible"] is False
    assert len(report["cross_split_exact_duplicate_groups"]) == 1
