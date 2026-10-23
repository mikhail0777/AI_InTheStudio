import argparse
import csv
import json

import cv2
import numpy as np
import pytest

from scripts.evaluate_readable_plate_benchmark import verify_frozen
from scripts.prepare_readable_plate_benchmark import freeze, yolo_boxes


def test_yolo_boxes_converts_normalized_coordinates(tmp_path):
    label = tmp_path / "sample.txt"
    label.write_text("0 0.5 0.5 0.4 0.2\n", encoding="utf-8")
    assert yolo_boxes(label, 100, 50) == [[30, 20, 70, 30]]


def make_candidate(tmp_path, readability="readable", transcription="ABC123"):
    benchmark = tmp_path / "benchmark"
    images = benchmark / "images"
    images.mkdir(parents=True)
    image_path = images / "plate_0001.png"
    cv2.imwrite(str(image_path), np.full((40, 120, 3), 220, dtype=np.uint8))
    from scripts.prepare_readable_plate_benchmark import sha256_file
    (benchmark / "private_provenance.json").write_text(json.dumps({
        "records": [{"sample_id": "plate_0001", "crop_sha256": sha256_file(image_path)}]
    }), encoding="utf-8")
    with (benchmark / "review.csv").open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=[
            "sample_id", "transcription", "readability", "vehicle_group_id", "reviewer", "notes",
        ])
        writer.writeheader()
        writer.writerow({"sample_id": "plate_0001", "transcription": transcription,
                         "readability": readability, "vehicle_group_id": "vehicle-1",
                         "reviewer": "human", "notes": ""})
    return benchmark


def test_freeze_creates_verifiable_manifest(tmp_path):
    benchmark = make_candidate(tmp_path)
    result = freeze(argparse.Namespace(benchmark=benchmark))
    assert result["counts"]["readable"] == 1
    assert verify_frozen(benchmark)["records"][0]["transcription"] == "ABC123"


def test_freeze_rejects_guessed_unreadable_truth(tmp_path):
    benchmark = make_candidate(tmp_path, readability="unreadable", transcription="ABC123")
    with pytest.raises(ValueError, match="must not contain transcription"):
        freeze(argparse.Namespace(benchmark=benchmark))


def test_freeze_accepts_out_of_scope_without_transcription(tmp_path):
    benchmark = make_candidate(tmp_path, readability="out_of_scope", transcription="")
    result = freeze(argparse.Namespace(benchmark=benchmark))
    assert result["counts"]["out_of_scope"] == 1
