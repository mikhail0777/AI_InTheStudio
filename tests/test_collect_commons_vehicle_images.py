import numpy as np
from unittest.mock import patch

from scripts.collect_commons_vehicle_images import category_files, commercial_license_allowed, dhash, plain


def test_commercial_license_allowlist_rejects_noncommercial_and_nd():
    assert commercial_license_allowed("CC BY-SA 4.0")
    assert commercial_license_allowed("Public domain")
    assert commercial_license_allowed("CC0")
    assert not commercial_license_allowed("CC BY-NC 4.0")
    assert not commercial_license_allowed("CC BY-ND 3.0")


def test_plain_removes_commons_html():
    assert plain("<b>Jane&nbsp;Doe</b>") == "Jane Doe"


def test_dhash_is_stable_for_same_pixels():
    image = np.arange(9 * 8 * 3, dtype=np.uint8).reshape(8, 9, 3)
    assert dhash(image) == dhash(image.copy())


def test_category_metadata_work_is_bounded_and_deterministic():
    titles = [{"title": f"File:{value}.jpg"} for value in range(100)]
    calls = []

    def fake_api(params):
        if params.get("list") == "categorymembers":
            return {"query": {"categorymembers": titles}}
        calls.extend(params["titles"].split("|"))
        return {"query": {"pages": []}}

    with patch("scripts.collect_commons_vehicle_images.api", side_effect=fake_api):
        category_files("Example", 3, candidate_multiplier=2)
    assert len(calls) == 6
    assert calls == sorted(
        calls, key=lambda title: __import__("hashlib").sha256(f"Example|{title}".encode()).hexdigest()
    )
