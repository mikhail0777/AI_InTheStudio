from typing import List, Dict, Optional, Any, Literal
from pydantic import BaseModel, Field
from app.models.open_vocabulary import SearchQuery

class TargetConfiguration(BaseModel):
    free_text_description: str = Field(default="", max_length=4000)
    upper_clothing_type: Optional[str] = None
    upper_clothing_color: Optional[str] = None
    sleeve_length: Optional[str] = None
    lower_clothing_type: Optional[str] = None
    lower_clothing_color: Optional[str] = None
    shoe_color: Optional[str] = None
    hair_color: Optional[str] = None
    hair_length: Optional[str] = None
    body_build: Optional[str] = None
    backpack: Optional[str] = None
    hat: Optional[str] = None
    eyewear: Optional[str] = None
    footwear_type: Optional[str] = None
    posture: Optional[str] = None
    other_accessories: Optional[str] = None
    distinctive_features: Optional[str] = None
    required_attributes: List[str] = Field(default_factory=list)
    optional_attributes: List[str] = Field(default_factory=list)
    negative_attributes: List[str] = Field(default_factory=list)
    min_alert_confidence: float = Field(default=0.60, ge=0, le=1)
    reference_photo_path: Optional[str] = None

class AnalysisStrategy(BaseModel):
    broad_scan_fps: float = 1.0
    focused_scan_fps: float = 4.0
    focused_window_seconds: float = 5.0
    minimum_person_confidence: float = 0.40
    minimum_alert_score: float = 0.65
    minimum_track_observations: int = 2

class SearchPlan(BaseModel):
    target_summary: str
    high_value_attributes: List[str]
    supporting_attributes: List[str]
    low_reliability_attributes: List[str]
    negative_attributes: List[str]
    analysis_strategy: AnalysisStrategy

class VideoMetadata(BaseModel):
    filename: str
    filepath: str
    duration_seconds: float
    frame_count: int
    fps: float
    width: int
    height: int
    codec: str
    file_size_mb: float
    creation_timestamp: str

class DetectionItem(BaseModel):
    detection_id: str
    frame_idx: int
    timestamp_seconds: float
    bbox: List[float] = Field(min_length=4, max_length=4)  # xyxy, original-frame pixels
    confidence: float
    crop_path: Optional[str] = None
    quality_score: float = 1.0
    detector_name: str = "unknown"
    model_version: Optional[str] = None
    color_features: Dict[str, Dict[str, float]] = Field(default_factory=dict)
    attribute_visibility: Dict[str, str] = Field(default_factory=dict)
    backpack_detected: Optional[bool] = None
    mask_path: Optional[str] = None

class AttributeDetail(BaseModel):
    expected: str
    observed: str
    score: Optional[float] = None
    visibility: str  # clear, partial, not_visible, obscured
    assessment: Literal["match", "conflict", "unknown"] = "unknown"
    method: Optional[str] = None
    evidence_timestamps: List[float] = Field(default_factory=list)
    evidence_paths: List[str] = Field(default_factory=list)

class GPSPoint(BaseModel):
    timestamp_seconds: float
    latitude: float
    longitude: float
    altitude_m: Optional[float] = None
    relative_altitude_m: Optional[float] = None
    telemetry_match_offset_seconds: Optional[float] = None
    source: str = "srt_aircraft"

class TrackResult(BaseModel):
    session_id: str
    track_id: int
    first_seen_seconds: float
    last_seen_seconds: float
    best_timestamp_seconds: float
    classification: str  # strong_match, possible_match, unlikely_match, insufficient_visibility
    person_detection_confidence: float
    appearance_similarity: float
    evidence_quality: float
    final_ranking_score: float
    observations_analyzed: int
    attributes: Dict[str, AttributeDetail]
    matching_evidence: List[str]
    conflicting_evidence: List[str]
    unknown_attributes: List[str]
    requires_human_review: bool
    explanation: str
    best_frame_path: str
    cropped_samples: List[str] = Field(default_factory=list)
    human_feedback: Optional[str] = None  # confirmed, rejected, needs_research
    human_notes: Optional[str] = None
    gps_location: Optional[GPSPoint] = None
    model_version: Optional[str] = None
    evidence_timestamps: List[float] = Field(default_factory=list)
    evidence_observations: List[DetectionItem] = Field(default_factory=list)

class HumanFeedbackInput(BaseModel):
    status: Literal["confirmed", "rejected", "needs_research"]
    notes: Optional[str] = Field(default=None, max_length=4000)

class AgentLogEntry(BaseModel):
    timestamp: str
    step: str
    message: str
    level: str = "info"  # info, warning, match, action

class SessionStatus(BaseModel):
    session_id: str
    status: str  # created, uploaded, analyzing, paused, completed, error
    progress_percent: float = 0.0
    current_stage: str = "idle"
    current_timestamp_seconds: float = 0.0
    total_duration_seconds: float = 0.0
    people_detected_count: int = 0
    unique_tracks_count: int = 0
    entity_counts: Dict[str, int] = Field(default_factory=dict)
    results_count: int = 0
    search_query: Optional[SearchQuery] = None
    search_plan: Optional[SearchPlan] = None
    agent_logs: List[AgentLogEntry] = Field(default_factory=list)
    run_id: Optional[str] = None
    frames_sampled: int = 0
    frames_planned: int = 0
    error_message: Optional[str] = None

class SARReport(BaseModel):
    session_id: str
    mission_name: str
    generated_at: str
    target_description: TargetConfiguration
    search_plan: SearchPlan
    video_info: VideoMetadata
    total_frames_sampled: int
    total_people_detected: int
    unique_tracks_count: int
    ranked_sightings: List[TrackResult]
    has_telemetry: bool
    unsearched_intervals: List[Dict[str, float]]
    actionable_recommendations: List[str]
    analysis_run_id: Optional[str] = None
    analyzed_timestamps_seconds: List[float] = Field(default_factory=list)
    failed_sample_timestamps_seconds: List[float] = Field(default_factory=list)
    coverage_summary: str = ""
    limitations: List[str] = Field(default_factory=list)
    report_revision: str = ""
