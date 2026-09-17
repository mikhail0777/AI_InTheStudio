"""Bounded, user-visible workload profiles for open-vocabulary search."""
from dataclasses import dataclass
from typing import Dict


@dataclass(frozen=True)
class ProcessingProfile:
    retrieval_limit: int
    localization_frame_limit: int
    localization_batch_size: int
    result_track_limit: int


PROFILES: Dict[str, ProcessingProfile] = {
    "fast": ProcessingProfile(12, 6, 2, 5),
    "balanced": ProcessingProfile(32, 16, 2, 10),
    "thorough": ProcessingProfile(80, 40, 4, 20),
}


def get_processing_profile(mode: str) -> ProcessingProfile:
    try:
        return PROFILES[mode]
    except KeyError as error:
        raise ValueError(f"Unsupported processing mode: {mode}") from error
