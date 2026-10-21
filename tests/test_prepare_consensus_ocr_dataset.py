from pathlib import Path

from scripts.prepare_consensus_ocr_dataset import prepare


def make_dataset(root: Path) -> None:
    root.mkdir(parents=True)
    (root / "data.yaml").write_text("names: ['A', 'B', 'C', '1', '2', '3', '4']\n", encoding="utf-8")
    for split in ("train", "valid", "test"):
        images = root / split / "images"
        labels = root / split / "labels"
        images.mkdir(parents=True)
        labels.mkdir(parents=True)
        stem = f"BA1234C_ABC1234_{split}_jpg.rf.abc"
        (images / f"{stem}.jpg").write_bytes(split.encode())
        (labels / f"{stem}.txt").write_text(
            "0 .1 .5 .1 .4\n1 .2 .5 .1 .4\n2 .3 .5 .1 .4\n3 .4 .5 .1 .4\n4 .5 .5 .1 .4\n5 .6 .5 .1 .4\n6 .7 .5 .1 .4\n",
            encoding="utf-8",
        )


def test_prepare_keeps_only_corroborated_original_labels(tmp_path):
    source = tmp_path / "source"
    destination = tmp_path / "derived"
    make_dataset(source)
    original = (source / "test" / "labels" / "BA1234C_ABC1234_test_jpg.rf.abc.txt").read_text()
    manifest = prepare(source, destination)
    assert manifest["splits"]["test"] == {"included": 1, "excluded": 0}
    assert manifest["splits"]["valid"] == {"included": 0, "excluded": 1}
    assert manifest["splits"]["train"] == {"included": 0, "excluded": 1}
    assert (source / "test" / "labels" / "BA1234C_ABC1234_test_jpg.rf.abc.txt").read_text() == original
    assert (destination / "test" / "labels" / "BA1234C_ABC1234_test_jpg.rf.abc.txt").read_text() == original
    assert (destination / "derivation_manifest.json").exists()
    assert "train: train/images" in (destination / "data.yaml").read_text()
