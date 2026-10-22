from pathlib import Path

import torch

from scripts.train_ctc_plate_ocr import PlateCRNN, greedy_decode


def test_plate_crnn_outputs_time_batch_classes():
    model = PlateCRNN(3)
    output = model(torch.zeros(2, 1, 32, 160))
    assert output.shape[1:] == (2, 4)
    assert output.shape[0] > 7


def test_greedy_decode_collapses_repeats_and_blanks():
    tokens = torch.tensor([[1], [1], [0], [2], [2], [3]])
    logits = torch.full((6, 1, 4), -10.0)
    logits.scatter_(2, tokens.unsqueeze(2), 0.0)
    assert greedy_decode(logits, ["A", "B", "C"]) == ["ABC"]
