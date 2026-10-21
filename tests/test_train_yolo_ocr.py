from pathlib import Path

import pytest

from scripts.train_yolo_ocr import validate_inputs


def test_validate_inputs_accepts_dataset_directory(tmp_path: Path):
    model = tmp_path / "model.pt"
    model.write_bytes(b"checkpoint")
    dataset = tmp_path / "dataset"
    dataset.mkdir()
    (dataset / "data.yaml").write_text("names: [A]\n", encoding="utf-8")

    assert validate_inputs(model, dataset) == (model.resolve(), (dataset / "data.yaml").resolve())


def test_validate_inputs_rejects_missing_files(tmp_path: Path):
    with pytest.raises(FileNotFoundError, match="Model checkpoint"):
        validate_inputs(tmp_path / "missing.pt", tmp_path / "missing.yaml")
