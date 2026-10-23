"""Conservative, auditable licence-plate region profiles.

Profiles rank an OCR candidate; they never mutate its characters.  The built-in
Ontario and Quebec patterns cover common standard passenger layouts only.
Special, vanity, temporary, historic, trailer, commercial, and multi-row plates
remain supported as evidence but require review until a labelled LotTrace
dataset explicitly validates their layouts.
"""
from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Iterable


ALPHANUMERIC = frozenset("ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789")


@dataclass(frozen=True)
class PlateFormat:
    name: str
    pattern: str
    plate_type: str = "passenger"
    layout: str = "single_row"
    evidence_status: str = "regional_reference_only"

    def matches(self, text: str, *, plate_type: str | None, layout: str | None) -> bool:
        if plate_type and plate_type != self.plate_type:
            return False
        if layout and layout != self.layout:
            return False
        return bool(re.fullmatch(self.pattern, text))


@dataclass(frozen=True)
class PlateRegionProfile:
    name: str
    permitted_characters: frozenset[str]
    formats: tuple[PlateFormat, ...]
    unsupported_plate_types: tuple[str, ...]
    source: str


UNKNOWN_PROFILE = PlateRegionProfile(
    name="unknown",
    permitted_characters=ALPHANUMERIC,
    formats=(),
    unsupported_plate_types=(),
    source="No regional format ranking applied.",
)

ONTARIO_PROFILE = PlateRegionProfile(
    name="ontario",
    permitted_characters=ALPHANUMERIC,
    formats=(PlateFormat("standard_passenger_aaaa999", r"[A-Z]{4}[0-9]{3}"),),
    unsupported_plate_types=(
        "commercial", "trailer", "historic", "vanity", "temporary", "diplomatic", "other",
    ),
    source="Common Ontario standard-passenger layout; not LotTrace validation evidence.",
)

QUEBEC_PROFILE = PlateRegionProfile(
    name="quebec",
    permitted_characters=ALPHANUMERIC,
    formats=(
        PlateFormat("standard_passenger_a99aaa", r"[A-Z][0-9]{2}[A-Z]{3}"),
        PlateFormat("standard_passenger_999aaa", r"[0-9]{3}[A-Z]{3}"),
    ),
    unsupported_plate_types=(
        "commercial", "trailer", "historic", "vanity", "temporary", "diplomatic", "other",
    ),
    source="Common Quebec standard-passenger layouts; not LotTrace validation evidence.",
)

PROFILES = {profile.name: profile for profile in (UNKNOWN_PROFILE, ONTARIO_PROFILE, QUEBEC_PROFILE)}


def get_plate_profile(profile: str | PlateRegionProfile | None) -> PlateRegionProfile:
    if isinstance(profile, PlateRegionProfile):
        return profile
    name = (profile or "unknown").strip().lower()
    if name not in PROFILES:
        raise ValueError(f"Unknown plate-region profile: {profile}")
    return PROFILES[name]


def assess_candidate_format(
    text: str,
    profile: str | PlateRegionProfile | None,
    *,
    plate_type: str | None = None,
    layout: str | None = None,
) -> dict:
    """Return ranking metadata without changing ``text``."""
    selected = get_plate_profile(profile)
    if any(character not in selected.permitted_characters for character in text):
        return {"state": "unsupported", "matched_formats": [], "contribution": -0.05}
    if selected.name == "unknown":
        return {"state": "not_applied", "matched_formats": [], "contribution": 0.0}
    if plate_type in selected.unsupported_plate_types or layout == "multi_row":
        return {"state": "unsupported", "matched_formats": [], "contribution": -0.05}
    matches = [
        item.name for item in selected.formats
        if item.matches(text, plate_type=plate_type, layout=layout)
    ]
    if len(matches) == 1:
        return {"state": "supported", "matched_formats": matches, "contribution": 0.05}
    if len(matches) > 1:
        return {"state": "ambiguous", "matched_formats": matches, "contribution": 0.0}
    return {"state": "unsupported", "matched_formats": [], "contribution": -0.05}


def list_profiles() -> Iterable[PlateRegionProfile]:
    return PROFILES.values()
