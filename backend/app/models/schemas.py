from typing import List, Dict, Optional, Any
from pydantic import BaseModel, Field

class TargetConfiguration(BaseModel):
    free_text_description: str = Field(..., example="Locate a person wearing a red hoodie, black pants, white shoes, with short dark hair and a blue backpack.")
    upper_clothing_type: Optional[str] = "hoodie"
    upper_clothing_color: Optional[str] = "red"
    lower_clothing_type: Optional[str] = "pants"
    lower_clothing_color: Optional[str] = "black"
    shoe_color: Optional[str] = None
    hair_color: Optional[str] = None
    hair_length: Optional[str] = None
    body_build: Optional[str] = "average"
    backpack: Optional[str] = "blue backpack"
    hat: Optional[str] = None
    other_accessories: Optional[str] = None
    distinctive_features: Optional[str] = None
    required_attributes: List[str] = Field(default_factory=lambda: ["red upper clothing"])
    optional_attributes: List[str] = Field(default_factory=lambda: ["blue backpack", "black pants"])
    negative_attributes: List[str] = Field(default_factory=lambda: ["hat", "bright green jacket"])
    min_alert_confidence: float = 0.60
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
    bbox: List[float]  # [x1, y1, x2, y2] normalized or pixels
    confidence: float
    crop_path: Optional[str] = None
    quality_score: float = 1.0

class AttributeDetail(BaseModel):
    expected: str
    observed: str
    score: Optional[float] = None
    visibility: str  # clear, partial, not_visible, obscured

class GPSPoint(BaseModel):
    timestamp_seconds: float
    latitude: float
    longitude: float
    altitude_m: float
    relative_altitude_m: Optional[float] = None

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

class HumanFeedbackInput(BaseModel):
    status: str  # confirmed, rejected, needs_research
    notes: Optional[str] = None

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
    search_plan: Optional[SearchPlan] = None
    agent_logs: List[AgentLogEntry] = Field(default_factory=list)

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
