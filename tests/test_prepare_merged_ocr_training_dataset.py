from pathlib import Path

from scripts.prepare_merged_ocr_training_dataset import prepare


def make_dataset(root: Path, names: list[str], splits: tuple[str, ...]) -> None:
    root.mkdir(parents=True)
    (root / "data.yaml").write_text(f"names: {names!r}\n", encoding="utf-8")
    for split in splits:
        (root / split / "images").mkdir(parents=True)
        (root / split / "labels").mkdir(parents=True)
        (root / split / "images" / f"{split}.jpg").write_bytes(b"image")
        (root / split / "labels" / f"{split}.txt").write_text("0 .2 .5 .1 .2\n", encoding="utf-8")


def test_prepare_maps_supplemental_classes_and_reserves_its_test(tmp_path: Path):
    primary = tmp_path / "primary"
    supplemental = tmp_path / "supplemental"
    output = tmp_path / "output"
    make_dataset(primary, ["A", "B", "C"], ("train", "valid", "test"))
    make_dataset(supplemental, ["C", "A"], ("train", "valid", "test"))
    (supplemental / "train" / "labels" / "train.txt").write_text("1 .2 .5 .1 .2\n0 .5 .5 .1 .2\n")

    manifest = prepare(primary, supplemental, output, "owner-permitted research")

    assert manifest["splits"]["train"]["images"] == 2
    assert manifest["splits"]["valid"]["images"] == 1
    assert manifest["splits"]["test"]["images"] == 1
    remapped = (output / "train" / "labels" / "supplemental__train.txt").read_text().splitlines()
    assert remapped[0].startswith("0 ")
    assert remapped[1].startswith("2 ")
    assert not (output / "test" / "images" / "supplemental__test.jpg").exists()
