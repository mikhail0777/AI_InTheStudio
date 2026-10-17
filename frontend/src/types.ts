export interface TargetConfiguration {
  free_text_description: string;
  processing_mode: 'fast' | 'balanced' | 'thorough';
  upper_clothing_type?: string;
  upper_clothing_color?: string;
  sleeve_length?: string;
  lower_clothing_type?: string;
  lower_clothing_color?: string;
  shoe_color?: string;
  hair_color?: string;
  hair_length?: string;
  body_build?: string;
  backpack?: string;
  hat?: string;
  eyewear?: string;
  footwear_type?: string;
  posture?: string;
  other_accessories?: string;
  distinctive_features?: string;
  required_attributes: string[];
  optional_attributes: string[];
  negative_attributes: string[];
  min_alert_confidence: number;
  plate_number?: string;
  plate_match_mode?: 'exact' | 'partial';
  vehicle_make?: string;
  vehicle_model?: string;
  vehicle_year?: number;
  vehicle_color?: string;
  vehicle_body_type?: string;
  camera_name?: string;
  camera_role?: 'unknown' | 'lot_entry' | 'lot_exit' | 'service_entry' | 'service_exit' | 'lot_area';
  recorded_start_at?: string;
  business_open_time?: string;
  business_close_time?: string;
  search_start_seconds?: number;
  search_end_seconds?: number;
}

export interface VehicleSighting {
  sighting_id: string;
  session_id: string;
  requested_plate: string;
  observed_plate: string;
  match_kind: 'exact' | 'partial' | 'review_candidate';
  captured_at?: string | null;
  best_timestamp_seconds: number;
  camera_name?: string | null;
  event_type: string;
  after_hours?: number | null;
  vehicle_make?: string | null;
  vehicle_model?: string | null;
  vehicle_year?: number | null;
  vehicle_color?: string | null;
  vehicle_body_type?: string | null;
  evidence_frame?: string | null;
  review_status?: string | null;
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

export interface AgentLogEntry {
  timestamp: string;
  step: string;
  message: string;
  level: 'info' | 'warning' | 'match' | 'action';
}

export interface SessionStatus {
  session_id: string;
  status: 'created' | 'uploaded' | 'queued' | 'analyzing' | 'paused' | 'cancelled' | 'completed' | 'error';
  error_message?: string | null;
  run_id?: string | null;
  frames_sampled?: number;
  frames_planned?: number;
  progress_percent: number;
  current_stage: string;
  total_duration_seconds: number;
  people_detected_count: number;
  unique_tracks_count: number;
  entity_counts?: Record<string, number>;
  results_count?: number;
  search_query?: {
    original_text: string;
    entities: Array<{ entity_id: string; name: string; entity_type?: string | null }>;
  } | null;
  processing_mode?: 'fast' | 'balanced' | 'thorough' | null;
  stage_timings?: Record<string, number>;
  search_plan?: SearchPlan | null;
  agent_logs: AgentLogEntry[];
}

export interface ModelProvenance {
  provider: string;
  model_name: string;
  model_version: string;
  device: string;
  metadata: Record<string, unknown>;
}

export interface EntityDetection {
  detection_id: string;
  frame_id?: string | null;
  frame_idx: number;
  timestamp_seconds: number;
  label: string;
  bbox: number[];
  confidence: number;
  visibility: number;
  crop_path?: string | null;
  mask_path?: string | null;
  attributes: Record<string, unknown>;
  provenance: ModelProvenance;
}

export interface EntityTrack {
  track_id: string;
  label: string;
  start_seconds: number;
  end_seconds: number;
  detections: EntityDetection[];
  attributes: Record<string, unknown>;
}

export interface EvidenceAssessment {
  criterion_id: string;
  kind: 'entity' | 'attribute' | 'action' | 'relationship' | 'temporal' | 'quality';
  assessment: 'supported' | 'conflicting' | 'missing' | 'uncertain' | 'unsupported';
  score?: number | null;
  explanation: string;
  timestamps: number[];
  entity_track_ids: string[];
  evidence_paths: string[];
  provenance?: ModelProvenance | null;
}

export interface SearchResult {
  result_id: string;
  search_id: string;
  start_seconds: number;
  end_seconds: number;
  best_timestamp_seconds: number;
  classification: 'strong_match' | 'possible_match' | 'unlikely_match' | 'insufficient_visibility' | 'unsupported_query';
  overall_score: number;
  component_scores: Record<string, number>;
  entities: EntityTrack[];
  evidence: EvidenceAssessment[];
  explanation: string;
  best_frame_path?: string | null;
  clip_path?: string | null;
  model_provenance: ModelProvenance[];
  human_feedback?: 'confirmed' | 'rejected' | 'needs_research' | null;
  human_notes?: string | null;
}
