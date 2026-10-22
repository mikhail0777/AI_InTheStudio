import csv
import json
from pathlib import Path

from scripts.export_ocr_conflict_review import export_queue


def test_export_queue_includes_only_human_reviewable_conflicts(tmp_path: Path):
    source = tmp_path / "source"
    images = source / "train" / "images"
    images.mkdir(parents=True)
    for name in ("conflict.jpg", "duplicate.jpg"):
        (images / name).write_bytes(name.encode())
    manifest = tmp_path / "manifest.json"
    manifest.write_text(json.dumps({"records": [
        {"status": "excluded", "reason": "label_and_filename_do_not_agree", "split": "train",
         "file": "conflict.jpg", "filename_candidates": ["ABC1234"], "label_sequence": "ABC1284"},
        {"status": "excluded", "reason": "identity_reserved_for_higher_priority_split", "split": "train",
         "file": "duplicate.jpg", "filename_candidates": ["ABC1234"], "label_sequence": "ABC1234"},
    ]}), encoding="utf-8")

    summary = export_queue(source, manifest, tmp_path / "queue")

    assert summary["review_items"] == 1
    with (tmp_path / "queue" / "review_queue.csv").open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    assert rows[0]["decision"] == "pending"
    assert rows[0]["human_verified_sequence"] == ""
    assert (tmp_path / "queue" / "images" / "train__conflict.jpg").exists()
