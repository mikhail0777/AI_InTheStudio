export interface TargetConfiguration {
  free_text_description: string;
  upper_clothing_type?: string;
  upper_clothing_color?: string;
  lower_clothing_type?: string;
  lower_clothing_color?: string;
  shoe_color?: string;
  hair_color?: string;
  hair_length?: string;
  body_build?: string;
  backpack?: string;
  hat?: string;
  other_accessories?: string;
  distinctive_features?: string;
  required_attributes: string[];
  optional_attributes: string[];
  negative_attributes: string[];
  min_alert_confidence: number;
}

export interface AnalysisStrategy {
  broad_scan_fps: number;
  focused_scan_fps: number;
  focused_window_seconds: number;
  minimum_person_confidence: number;
  minimum_alert_score: number;
  minimum_track_observations: number;
}

export interface SearchPlan {
  target_summary: string;
  high_value_attributes: string[];
  supporting_attributes: string[];
  low_reliability_attributes: string[];
  negative_attributes: string[];
  analysis_strategy: AnalysisStrategy;
}

export interface VideoMetadata {
  filename: string;
  filepath: string;
  duration_seconds: number;
  frame_count: number;
  fps: number;
  width: number;
  height: number;
  codec: string;
  file_size_mb: number;
  creation_timestamp: string;
}

export interface AttributeDetail {
  expected: string;
  observed: string;
  score?: number | null;
  visibility: 'clear' | 'partial' | 'not_visible' | 'obscured';
}

export interface GPSPoint {
  timestamp_seconds: number;
  latitude: number;
  longitude: number;
  altitude_m: number;
  relative_altitude_m?: number;
}

export interface TrackResult {
  session_id: string;
  track_id: number;
  first_seen_seconds: number;
  last_seen_seconds: number;
  best_timestamp_seconds: number;
  classification: 'strong_match' | 'possible_match' | 'unlikely_match' | 'insufficient_visibility';
  person_detection_confidence: number;
  appearance_similarity: number;
  evidence_quality: number;
  final_ranking_score: number;
  observations_analyzed: number;
  attributes: Record<string, AttributeDetail>;
  matching_evidence: string[];
  conflicting_evidence: string[];
  unknown_attributes: string[];
  requires_human_review: boolean;
  explanation: string;
  best_frame_path: string;
  cropped_samples: string[];
  human_feedback?: 'confirmed' | 'rejected' | 'needs_research' | null;
  human_notes?: string | null;
  gps_location?: GPSPoint | null;
}

export interface AgentLogEntry {
  timestamp: string;
  step: string;
  message: string;
  level: 'info' | 'warning' | 'match' | 'action';
}

export interface SessionStatus {
  session_id: string;
  status: 'created' | 'uploaded' | 'analyzing' | 'paused' | 'completed' | 'error';
  progress_percent: number;
  current_stage: string;
  total_duration_seconds: number;
  people_detected_count: number;
  unique_tracks_count: number;
  search_plan?: SearchPlan | null;
  agent_logs: AgentLogEntry[];
}

export interface SARReport {
  session_id: string;
  mission_name: string;
  generated_at: string;
  target_description: TargetConfiguration;
  search_plan: SearchPlan;
  video_info: VideoMetadata;
  total_frames_sampled: number;
  total_people_detected: number;
  unique_tracks_count: number;
  ranked_sightings: TrackResult[];
  has_telemetry: boolean;
  unsearched_intervals: Array<{ start_seconds: number; end_seconds: number }>;
  actionable_recommendations: string[];
}
