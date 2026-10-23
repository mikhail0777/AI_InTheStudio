from scripts.prepare_dvm_modern_benchmark import parse_member, split_for


def test_parse_member_preserves_model_and_listing_group():
    parsed = parse_member(
        "confirmed_fronts/Ford/2017/Ford$$Focus$$2017$$Blue$$2_4$$123$$image_2.jpg"
    )
    assert parsed == {
        "make": "Ford", "model": "Focus", "year": 2017, "colour": "Blue",
        "view": "2_4", "listing_id": "123", "image_id": "image_2",
    }


def test_split_is_deterministic_and_known():
    assert split_for("Ford|Focus|123", "seed") == split_for("Ford|Focus|123", "seed")
    assert split_for("Ford|Focus|123", "seed") in {"train", "development", "test"}
