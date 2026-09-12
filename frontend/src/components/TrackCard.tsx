import React from 'react';
import { TrackResult } from '../types';
import { Eye, CheckCircle2, XCircle, MapPin, Clock, Award } from 'lucide-react';

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
  const getBadgeStyle = (classification: string) => {
    switch (classification) {
      case 'strong_match': return 'status-tag-green';
      case 'possible_match': return 'status-tag-yellow';
      case 'unlikely_match': return 'status-tag-red';
      default: return 'status-tag-blue';
    }
  };

  const formatTime = (seconds: number) => {
    const m = Math.floor(seconds / 60);
    const s = Math.floor(seconds % 60);
    return `${m.toString().padStart(2, '0')}:${s.toString().padStart(2, '0')}`;
  };

  const scorePercent = (track.final_ranking_score * 100).toFixed(0);

  return (
    <div style={{
      background: isSelected ? '#1A2130' : '#121722',
      border: isSelected ? '1px solid #38BDF8' : '1px solid #222C3E',
      borderRadius: '6px',
      padding: '0.85rem',
      display: 'flex',
      flexDirection: 'column',
      gap: '0.6rem',
      cursor: 'pointer',
      transition: 'all 0.15s ease'
    }} onClick={onSelect}>
      {/* Header Bar */}
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '0.4rem' }}>
          <span className={`status-tag ${getBadgeStyle(track.classification)}`}>
            {track.classification.replace('_', ' ')}
          </span>
          <span style={{ fontSize: '0.78rem', fontWeight: 600, color: '#8B949E' }}>
            Track #{track.track_id}
          </span>
        </div>

        <div style={{ display: 'flex', alignItems: 'center', gap: '0.25rem', background: '#0A0D14', padding: '0.2rem 0.5rem', borderRadius: '4px', border: '1px solid #222C3E' }}>
          <Award size={12} color="#38BDF8" />
          <span style={{ fontSize: '0.8rem', fontWeight: 700, color: '#38BDF8' }}>
            {scorePercent}%
          </span>
        </div>
      </div>

      {/* Body: Thumbnail & Specs */}
      <div style={{ display: 'flex', gap: '0.75rem', alignItems: 'center' }}>
        <div style={{
          width: '68px',
          height: '96px',
          background: '#000000',
          borderRadius: '4px',
          overflow: 'hidden',
          border: '1px solid #222C3E',
          flexShrink: 0,
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center'
        }}>
          {track.best_frame_path ? (
            <img
              src={track.best_frame_path}
              alt={`Track #${track.track_id}`}
              style={{ width: '100%', height: '100%', objectFit: 'cover' }}
            />
          ) : (
            <span style={{ fontSize: '0.65rem', color: '#6E7681' }}>No Crop</span>
          )}
        </div>

        <div style={{ display: 'flex', flexDirection: 'column', gap: '0.35rem', flex: 1 }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.35rem', fontSize: '0.78rem', color: '#F0F6FC', fontWeight: 600 }}>
            <Clock size={12} color="#38BDF8" />
            <span>{formatTime(track.best_timestamp_seconds)} ({track.best_timestamp_seconds.toFixed(1)}s)</span>
          </div>

          {track.gps_location && (
            <div style={{ display: 'flex', alignItems: 'center', gap: '0.3rem', fontSize: '0.72rem', color: '#10B981' }}>
              <MapPin size={11} />
              <span>GPS [{track.gps_location.latitude.toFixed(4)}, {track.gps_location.longitude.toFixed(4)}]</span>
            </div>
          )}

          {/* Ranking Score Bar */}
          <div>
            <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '0.68rem', color: '#8B949E', marginBottom: '0.2rem' }}>
              <span>Match Confidence</span>
              <span>{(track.appearance_similarity * 100).toFixed(0)}%</span>
            </div>
            <div style={{ width: '100%', height: '4px', background: '#222C3E', borderRadius: '2px', overflow: 'hidden' }}>
              <div style={{
                width: `${scorePercent}%`,
                height: '100%',
                background: '#38BDF8'
              }} />
            </div>
          </div>
        </div>
      </div>

      {/* Operator Review Controls */}
      <div style={{ display: 'flex', gap: '0.35rem', paddingTop: '0.35rem', borderTop: '1px solid #222C3E' }}>
        <button
          onClick={(e) => { e.stopPropagation(); onFeedback(track.track_id, 'confirmed'); }}
          style={{
            flex: 1,
            padding: '0.3rem',
            borderRadius: '4px',
            border: track.human_feedback === 'confirmed' ? '1px solid #10B981' : '1px solid #222C3E',
            background: track.human_feedback === 'confirmed' ? 'rgba(16, 185, 129, 0.15)' : '#0A0D14',
            color: track.human_feedback === 'confirmed' ? '#10B981' : '#8B949E',
            fontSize: '0.72rem',
            fontWeight: 600,
            cursor: 'pointer',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            gap: '0.2rem'
          }}
        >
          <CheckCircle2 size={11} /> Confirm
        </button>

        <button
          onClick={(e) => { e.stopPropagation(); onFeedback(track.track_id, 'rejected'); }}
          style={{
            flex: 1,
            padding: '0.3rem',
            borderRadius: '4px',
            border: track.human_feedback === 'rejected' ? '1px solid #EF4444' : '1px solid #222C3E',
            background: track.human_feedback === 'rejected' ? 'rgba(239, 68, 68, 0.15)' : '#0A0D14',
            color: track.human_feedback === 'rejected' ? '#EF4444' : '#8B949E',
            fontSize: '0.72rem',
            fontWeight: 600,
            cursor: 'pointer',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            gap: '0.2rem'
          }}
        >
          <XCircle size={11} /> Reject
        </button>

        <button
          onClick={(e) => { e.stopPropagation(); onJumpToTime(track.best_timestamp_seconds); }}
          style={{
            padding: '0.3rem 0.55rem',
            borderRadius: '4px',
            border: '1px solid #222C3E',
            background: '#0A0D14',
            color: '#38BDF8',
            fontSize: '0.72rem',
            fontWeight: 600,
            cursor: 'pointer',
            display: 'flex',
            alignItems: 'center',
            gap: '0.2rem'
          }}
        >
          <Eye size={11} /> Seek
        </button>
      </div>
    </div>
  );
};
