import torch

from scripts.evaluate_grouped_vehicle_make_model import build_groups, grouped_probabilities


def test_year_ranges_and_punctuation_collapse_into_make_model_groups():
    groups, mapping = build_groups([
        {"make": "Ford", "model": "F-150", "year_start": 2001},
        {"make": "ford", "model": "f150", "year_start": 2021},
        {"make": "Ford", "model": "Escape", "year_start": 2020},
    ])
    assert len(groups) == 2
    assert mapping.tolist() == [0, 0, 1]


def test_probabilities_are_summed_before_ranking():
    logits = torch.log(torch.tensor([[.30, .29, .41]]))
    grouped = grouped_probabilities(logits, torch.tensor([0, 0, 1]), 2)
    assert grouped.argmax(dim=1).item() == 0
    assert torch.allclose(grouped, torch.tensor([[.59, .41]]), atol=1e-6)
