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
      case 'strong_match': return 'green';
      case 'possible_match': return 'yellow';
      case 'unlikely_match': return 'red';
      default: return 'blue';
    }
  };

  const formatTime = (seconds: number) => {
    const m = Math.floor(seconds / 60);
    const s = Math.floor(seconds % 60);
    return `${m.toString().padStart(2, '0')}:${s.toString().padStart(2, '0')}`;
  };

  const scorePercent = (track.final_ranking_score * 100).toFixed(0);

  return (
    <div 
      className="card-module group"
      style={{
        padding: '24px',
        display: 'flex',
        flexDirection: 'column',
        gap: '16px',
        cursor: 'pointer',
        boxShadow: isSelected ? 'var(--shadow-floating)' : 'var(--shadow-card)',
        transform: isSelected ? 'translateY(-4px)' : 'none',
        border: isSelected ? '1px solid rgba(255, 71, 87, 0.3)' : '1px solid transparent'
      }} 
      onClick={onSelect}
    >
      <div className="screws" />

      {/* Header Bar */}
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', zIndex: 10 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
          <div className="status-label" style={{ display: 'flex', alignItems: 'center', gap: '6px', background: 'var(--bg-panel)', padding: '4px 8px', borderRadius: 'var(--radius-sm)', boxShadow: 'var(--shadow-sharp)' }}>
            <span className={`led ${getBadgeStyle(track.classification)}`} style={{ width: '8px', height: '8px' }} />
            {track.classification.replace('_', ' ')}
          </div>
          <span className="status-label" style={{ color: 'var(--text-primary)' }}>
            MODULE #{track.track_id}
          </span>
        </div>

        <div className="input-slot" style={{ width: 'auto', padding: '4px 12px', display: 'flex', alignItems: 'center', gap: '6px' }}>
          <Award size={14} color="var(--accent-orange)" />
          <span style={{ fontSize: '14px', fontWeight: 700, color: 'var(--text-primary)' }}>
            {scorePercent}%
          </span>
        </div>
      </div>

      {/* Body: Thumbnail & Specs */}
      <div style={{ display: 'flex', gap: '20px', alignItems: 'center', zIndex: 10 }}>
        <div className="input-slot" style={{
          width: '80px',
          height: '100px',
          padding: '4px',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          flexShrink: 0
        }}>
          {track.best_frame_path ? (
            <img
              src={track.best_frame_path}
              alt={`Track #${track.track_id}`}
              className="grayscale group-hover:grayscale-0 transition-all duration-500"
              style={{ width: '100%', height: '100%', objectFit: 'cover', borderRadius: '4px' }}
            />
          ) : (
            <span className="status-label">NO DATA</span>
          )}
        </div>

        <div style={{ display: 'flex', flexDirection: 'column', gap: '8px', flex: 1 }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '8px', fontSize: '13px', fontWeight: 600 }}>
            <Clock size={14} color="var(--text-muted)" />
            <span>{formatTime(track.best_timestamp_seconds)} ({track.best_timestamp_seconds.toFixed(1)}s)</span>
          </div>

          {track.gps_location && (
            <div style={{ display: 'flex', alignItems: 'center', gap: '8px', fontSize: '12px', fontWeight: 500, color: 'var(--text-muted)' }}>
              <MapPin size={14} />
              <span>GPS: {track.gps_location.latitude.toFixed(4)}, {track.gps_location.longitude.toFixed(4)}</span>
            </div>
          )}

          {/* Ranking Score Bar */}
          <div style={{ marginTop: '8px' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '6px' }}>
              <span className="status-label">MATCH CONFIDENCE</span>
              <span className="status-label">{(track.appearance_similarity * 100).toFixed(0)}%</span>
            </div>
            <div className="input-slot" style={{ height: '12px', padding: 0, overflow: 'hidden' }}>
              <div style={{
                width: `${scorePercent}%`,
                height: '100%',
                background: 'var(--text-primary)',
                borderRadius: 'var(--radius-md)'
              }} />
            </div>
          </div>
        </div>
      </div>

      {/* Operator Review Controls */}
      <div style={{ display: 'flex', gap: '12px', paddingTop: '16px', borderTop: '2px dashed var(--shadow-color)', zIndex: 10 }}>
        <button
          className={`btn-industrial ${track.human_feedback === 'confirmed' ? 'btn-primary' : ''}`}
          onClick={(e) => { e.stopPropagation(); onFeedback(track.track_id, 'confirmed'); }}
          style={{ flex: 1, padding: '12px 8px', fontSize: '12px' }}
        >
          <CheckCircle2 size={16} /> CONFIRM
        </button>

        <button
          className="btn-industrial"
          onClick={(e) => { e.stopPropagation(); onFeedback(track.track_id, 'rejected'); }}
          style={{ flex: 1, padding: '12px 8px', fontSize: '12px', color: track.human_feedback === 'rejected' ? 'var(--accent-orange)' : '' }}
        >
          <XCircle size={16} /> REJECT
        </button>

        <button
          className="btn-industrial"
          onClick={(e) => { e.stopPropagation(); onJumpToTime(track.best_timestamp_seconds); }}
          style={{ padding: '12px', flexShrink: 0 }}
        >
          <Eye size={18} />
        </button>
      </div>
    </div>
  );
};
