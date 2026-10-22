import torch

from scripts.evaluate_ctc_plate_ocr import ctc_beam_candidates


def test_ctc_beam_candidates_collapse_repeats_and_return_ranked_text():
    tokens = [1, 1, 0, 2, 2, 0, 3]
    logits = torch.full((len(tokens), 4), -8.0)
    for index, token in enumerate(tokens):
        logits[index, token] = 0.0
    candidates = ctc_beam_candidates(logits, ["A", "B", "C"], beam_width=10, top_k=3)
    assert candidates[0]["text"] == "ABC"
    assert candidates[0]["log_score"] >= candidates[1]["log_score"]
