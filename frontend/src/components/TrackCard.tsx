import React from 'react';
import { TrackResult } from '../types';
import { Eye, CheckCircle2, XCircle, MapPin, Clock } from 'lucide-react';
import { candidateLabels, formatTime, reviewLabel } from '../review';

interface TrackCardProps {
  track: TrackResult;
  isSelected: boolean;
  onSelect: () => void;
  onJumpToTime: (seconds: number) => void;
  onFeedback: (trackId: number, status: 'confirmed' | 'rejected' | 'needs_research') => void;
}

export const TrackCard: React.FC<TrackCardProps> = ({ track, isSelected, onSelect, onJumpToTime, onFeedback }) => (
  <article className={`card-module track-card ${isSelected ? 'selected' : ''}`}>
    <div className="row-between">
      <span className="status-label">Track #{track.track_id}</span>
      <span className={`candidate-badge ${track.classification}`}>{candidateLabels[track.classification]}</span>
    </div>
    <button className="track-preview" onClick={onSelect} aria-label={`Review evidence for track ${track.track_id}`}>
      <div className="evidence-thumbnail">
        {track.best_frame_path ? <img src={track.best_frame_path} alt={`Original candidate crop, track ${track.track_id}`} /> : <span>No image</span>}
      </div>
      <div className="track-summary">
        <span className="icon-line"><Clock size={15} />{formatTime(track.best_timestamp_seconds)} · {track.observations_analyzed} observations</span>
        <strong>{reviewLabel(track)}</strong>
        <p>{track.matching_evidence[0] || (track.classification === 'insufficient_visibility' ? 'Visible attributes are insufficient for comparison.' : 'Open the evidence to inspect this candidate.')}</p>
        {track.gps_location && <span className="icon-line muted"><MapPin size={14} />Drone: {track.gps_location.latitude.toFixed(5)}, {track.gps_location.longitude.toFixed(5)}</span>}
      </div>
    </button>
    <div className="track-actions">
      <button className="btn-industrial" aria-pressed={track.human_feedback === 'confirmed'} onClick={() => onFeedback(track.track_id, 'confirmed')}><CheckCircle2 size={16} />Confirm</button>
      <button className="btn-industrial" aria-pressed={track.human_feedback === 'rejected'} onClick={() => onFeedback(track.track_id, 'rejected')}><XCircle size={16} />Reject</button>
      <button className="btn-industrial" title="Jump to original footage" aria-label={`Play track ${track.track_id} in original footage`} onClick={() => onJumpToTime(track.best_timestamp_seconds)}><Eye size={17} /></button>
    </div>
  </article>
);
