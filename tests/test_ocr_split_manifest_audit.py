import pytest

from scripts.audit_ocr_split_manifest import audit_records, hamming_distance


def record(identifier, split, **values):
    return {
        "id": identifier, "split": split, "source": "licensed-source",
        "license": "CC-BY-4.0", "checksum": f"sum-{identifier}",
        "label_type": "full_plate_transcription", "transcription": "ABCD123",
        "usage_restrictions": "local research", **values,
    }


def test_split_audit_detects_identity_and_near_duplicate_leakage():
    report = audit_records([
        record("train", "train", plate_identity="ABCD123", perceptual_hash="0000000000000000"),
        record("test", "final_test", plate_identity="ABCD123", perceptual_hash="0000000000000001"),
    ])
    assert not report["passes"]
    assert {item["field"] for item in report["leakage"]} == {"plate_identity", "near_duplicate"}


def test_split_audit_accepts_isolated_complete_records_deterministically():
    rows = [
        record("train", "train", plate_identity="ABCD123", perceptual_hash="0000000000000000"),
        record("test", "final_test", plate_identity="WXYZ987", perceptual_hash="ffffffffffffffff"),
    ]
    assert audit_records(rows) == audit_records(rows)
    assert audit_records(rows)["passes"]


def test_masked_truth_and_missing_provenance_are_invalid():
    bad = record("masked", "validation", transcription="AB**123")
    bad["license"] = ""
    report = audit_records([bad])
    assert not report["passes"]
    assert "unmasked_full_plate_truth" in report["invalid_records"][0]["problems"]
    assert "license" in report["invalid_records"][0]["problems"]


def test_hamming_distance_rejects_malformed_hashes():
    with pytest.raises(ValueError):
        hamming_distance("xyz", "123")
