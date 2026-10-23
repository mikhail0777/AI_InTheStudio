from pathlib import Path

from scripts.fine_tune_parseq_plate_ocr import (
    SyntheticPlateSample,
    render_synthetic_plate,
    synthetic_sequence,
)


def test_synthetic_plate_sequence_and_render_are_deterministic():
    font_dir = Path(__import__("matplotlib").get_data_path()) / "fonts" / "ttf"
    fonts = [font_dir / "DejaVuSans-Bold.ttf", font_dir / "DejaVuSansMono-Bold.ttf"]
    sequence = synthetic_sequence(1234)
    assert sequence.isalnum() and sequence == sequence.upper()
    sample = SyntheticPlateSample(1234, sequence)
    first = render_synthetic_plate(sample, fonts)
    second = render_synthetic_plate(sample, fonts)
    try:
        assert first.size == second.size
        assert first.tobytes() == second.tobytes()
    finally:
        first.close()
        second.close()
