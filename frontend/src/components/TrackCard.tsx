import React from 'react';
import { TrackResult } from '../types';
import { Eye, CheckCircle2, XCircle, MapPin, Clock, Award, HelpCircle } from 'lucide-react';

interface TrackCardProps {
  track: TrackResult;
  isSelected: boolean;
  onSelect: () => void;
  onJumpToTime: (seconds: number) => void;
  onFeedback: (trackId: number, status: 'confirmed' | 'rejected' | 'needs_research') => void;
}

export const TrackCard: React.FC<TrackCardProps> = ({
  track,
  isSelected,
  onSelect,
  onJumpToTime,
  onFeedback
}) => {
  const getBadgeClass = (classification: string) => {
    switch (classification) {
      case 'strong_match': return 'badge-strong';
      case 'possible_match': return 'badge-possible';
      case 'unlikely_match': return 'badge-unlikely';
      default: return 'badge-grey';
    }
  };

  const formatTime = (seconds: number) => {
    const m = Math.floor(seconds / 60);
    const s = Math.floor(seconds % 60);
    return `${m.toString().padStart(2, '0')}:${s.toString().padStart(2, '0')}`;
  };

  return (
    <div style={{
      background: isSelected ? 'rgba(56, 189, 248, 0.08)' : 'var(--bg-card)',
      border: isSelected ? '1px solid var(--primary)' : '1px solid var(--border-color)',
      borderRadius: '8px',
      padding: '0.9rem',
      display: 'flex',
      flexDirection: 'column',
      gap: '0.6rem',
      transition: 'all 0.2s ease',
      boxShadow: isSelected ? '0 0 15px rgba(56, 189, 248, 0.15)' : 'none'
    }}>
      {/* Header with Classification Badge & Ranking Score */}
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
          <span className={`badge ${getBadgeClass(track.classification)}`}>
            {track.classification.replace('_', ' ')}
          </span>
          <span style={{ fontSize: '0.8rem', fontWeight: 700, color: 'var(--text-muted)' }}>
            Track #{track.track_id}
          </span>
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: '0.3rem', background: '#0F172A', padding: '0.2rem 0.5rem', borderRadius: '4px', border: '1px solid #1E293B' }}>
          <Award size={14} color="#38BDF8" />
          <span style={{ fontSize: '0.85rem', fontWeight: 800, color: '#38BDF8' }}>
            {(track.final_ranking_score * 100).toFixed(0)}%
          </span>
        </div>
      </div>

      {/* Main Body: Crop Image & Metrics */}
      <div style={{ display: 'flex', gap: '0.8rem', alignItems: 'center' }}>
        {/* Crop Thumbnail */}
        <div style={{
          width: '72px',
          height: '110px',
          background: '#000000',
          borderRadius: '6px',
          overflow: 'hidden',
          border: '1px solid var(--border-bright)',
          flexShrink: 0,
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center'
        }}>
          {track.best_frame_path ? (
            <img
              src={track.best_frame_path}
              alt={`Track #${track.track_id} Crop`}
              style={{ width: '100%', height: '100%', objectFit: 'cover' }}
            />
          ) : (
            <span style={{ fontSize: '0.65rem', color: 'var(--text-dim)' }}>No Crop</span>
          )}
        </div>

        {/* Metrics & Evidence */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: '0.35rem', flex: 1 }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', fontSize: '0.8rem', color: 'var(--text-main)', fontWeight: 600 }}>
            <Clock size={14} color="#38BDF8" />
            <span>{formatTime(track.best_timestamp_seconds)} ({track.best_timestamp_seconds}s)</span>
          </div>

          {track.gps_location && (
            <div style={{ display: 'flex', alignItems: 'center', gap: '0.4rem', fontSize: '0.75rem', color: '#10B981' }}>
              <MapPin size={13} />
              <span>{track.gps_location.latitude}, {track.gps_location.longitude}</span>
            </div>
          )}

          <div style={{ fontSize: '0.75rem', color: 'var(--text-muted)' }}>
            App Sim: <b style={{ color: '#F8FAFC' }}>{(track.appearance_similarity * 100).toFixed(0)}%</b> | Det Conf: <b style={{ color: '#F8FAFC' }}>{(track.person_detection_confidence * 100).toFixed(0)}%</b>
          </div>

          <p style={{ fontSize: '0.75rem', color: 'var(--text-muted)', lineHeight: 1.3, display: '-webkit-box', WebkitLineClamp: 2, WebkitBoxOrient: 'vertical', overflow: 'hidden' }}>
            {track.explanation}
          </p>
        </div>
      </div>

      {/* Matching Evidence Tags */}
      {track.matching_evidence.length > 0 && (
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: '0.3rem' }}>
          {track.matching_evidence.slice(0, 2).map((ev, i) => (
            <span key={i} style={{ fontSize: '0.7rem', background: 'rgba(16, 185, 129, 0.1)', color: '#10B981', border: '1px solid rgba(16, 185, 129, 0.3)', padding: '0.15rem 0.4rem', borderRadius: '4px' }}>
              ✓ {ev}
            </span>
          ))}
        </div>
      )}

      {/* Human Feedback Controls */}
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', paddingTop: '0.4rem', borderTop: '1px solid var(--border-color)' }}>
        <button
          className="btn btn-secondary"
          onClick={() => onJumpToTime(track.best_timestamp_seconds)}
          style={{ padding: '0.3rem 0.6rem', fontSize: '0.75rem' }}
        >
          Jump to Time
        </button>

        <div style={{ display: 'flex', gap: '0.3rem' }}>
          <button
            title="Confirm Match"
            onClick={() => onFeedback(track.track_id, 'confirmed')}
            style={{
              background: track.human_feedback === 'confirmed' ? '#10B981' : 'var(--bg-dark)',
              color: track.human_feedback === 'confirmed' ? '#FFFFFF' : '#10B981',
              border: '1px solid #10B981',
              borderRadius: '4px',
              padding: '0.3rem 0.5rem',
              cursor: 'pointer'
            }}
          >
            <CheckCircle2 size={15} />
          </button>
          <button
            title="Reject Match"
            onClick={() => onFeedback(track.track_id, 'rejected')}
            style={{
              background: track.human_feedback === 'rejected' ? '#EF4444' : 'var(--bg-dark)',
              color: track.human_feedback === 'rejected' ? '#FFFFFF' : '#EF4444',
              border: '1px solid #EF4444',
              borderRadius: '4px',
              padding: '0.3rem 0.5rem',
              cursor: 'pointer'
            }}
          >
            <XCircle size={15} />
          </button>
          <button
            className="btn btn-secondary"
            onClick={onSelect}
            style={{ padding: '0.3rem 0.6rem', fontSize: '0.75rem' }}
          >
            <Eye size={14} /> Details
          </button>
        </div>
      </div>
    </div>
  );
};
