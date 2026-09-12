import React, { useState } from 'react';
import { TrackResult } from '../types';
import { X, CheckCircle2, XCircle, AlertTriangle, MapPin } from 'lucide-react';

interface TrackDetailModalProps {
  track: TrackResult | null;
  onClose: () => void;
  onFeedback: (trackId: number, status: 'confirmed' | 'rejected' | 'needs_research', notes?: string) => void;
}

export const TrackDetailModal: React.FC<TrackDetailModalProps> = ({ track, onClose, onFeedback }) => {
  const [notes, setNotes] = useState(track?.human_notes || '');

  if (!track) return null;

  return (
    <div style={{
      position: 'fixed',
      inset: 0,
      background: 'rgba(10, 13, 20, 0.85)',
      backdropFilter: 'blur(10px)',
      display: 'flex',
      alignItems: 'center',
      justifyContent: 'center',
      zIndex: 1000,
      padding: '1.25rem'
    }}>
      <div style={{
        background: '#121722',
        border: '1px solid #222C3E',
        borderRadius: '6px',
        maxWidth: '860px',
        width: '100%',
        maxHeight: '90vh',
        overflowY: 'auto',
        display: 'flex',
        flexDirection: 'column',
        boxShadow: '0 20px 50px rgba(0, 0, 0, 0.6)'
      }}>
        {/* Header */}
        <div style={{
          padding: '1rem 1.25rem',
          borderBottom: '1px solid #222C3E',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          background: '#1A2130'
        }}>
          <div>
            <h2 style={{ fontSize: '1.1rem', fontWeight: 700, color: '#F0F6FC', display: 'flex', alignItems: 'center', gap: '0.6rem' }}>
              Track #{track.track_id} — Deep Inspection
              <span className={`status-tag ${track.classification === 'strong_match' ? 'status-tag-green' : (track.classification === 'possible_match' ? 'status-tag-yellow' : 'status-tag-red')}`}>
                {track.classification.replace('_', ' ')}
              </span>
            </h2>
            <p style={{ fontSize: '0.75rem', color: '#8B949E', marginTop: '0.15rem' }}>
              Observed from {track.first_seen_seconds.toFixed(1)}s to {track.last_seen_seconds.toFixed(1)}s (Best Frame: {track.best_timestamp_seconds.toFixed(1)}s)
            </p>
          </div>
          <button onClick={onClose} style={{ background: '#0A0D14', border: '1px solid #222C3E', borderRadius: '4px', color: '#8B949E', cursor: 'pointer', padding: '0.35rem' }}>
            <X size={18} />
          </button>
        </div>

        {/* Content Body */}
        <div style={{ padding: '1.25rem', display: 'flex', flexDirection: 'column', gap: '1.25rem' }}>
          {/* Top Row: Crops & Metrics */}
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '1rem' }}>
            {/* Multi-frame Crops */}
            <div>
              <h4 style={{ fontSize: '0.82rem', fontWeight: 600, color: '#38BDF8', marginBottom: '0.5rem' }}>
                Multi-Frame Temporal Crops ({track.cropped_samples.length})
              </h4>
              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: '0.4rem' }}>
                {track.cropped_samples.map((cropPath, idx) => (
                  <div key={idx} style={{
                    background: '#000000',
                    borderRadius: '4px',
                    overflow: 'hidden',
                    aspectRatio: '2/3',
                    border: cropPath === track.best_frame_path ? '2px solid #38BDF8' : '1px solid #222C3E'
                  }}>
                    <img src={cropPath} alt={`Crop ${idx}`} style={{ width: '100%', height: '100%', objectFit: 'cover' }} />
                  </div>
                ))}
              </div>
            </div>

            {/* Score Metrics */}
            <div style={{ display: 'flex', flexDirection: 'column', gap: '0.75rem', background: '#0A0D14', padding: '1rem', borderRadius: '6px', border: '1px solid #222C3E' }}>
              <h4 style={{ fontSize: '0.82rem', fontWeight: 600, color: '#38BDF8' }}>
                Confidence Breakdown
              </h4>
              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '0.65rem' }}>
                <div>
                  <span style={{ fontSize: '0.72rem', color: '#8B949E' }}>Final Score:</span>
                  <p style={{ fontSize: '1.35rem', fontWeight: 800, color: '#38BDF8' }}>{(track.final_ranking_score * 100).toFixed(0)}%</p>
                </div>
                <div>
                  <span style={{ fontSize: '0.72rem', color: '#8B949E' }}>Appearance Sim:</span>
                  <p style={{ fontSize: '1.35rem', fontWeight: 800, color: '#10B981' }}>{(track.appearance_similarity * 100).toFixed(0)}%</p>
                </div>
                <div>
                  <span style={{ fontSize: '0.72rem', color: '#8B949E' }}>Detector Conf:</span>
                  <p style={{ fontSize: '1rem', fontWeight: 700, color: '#F0F6FC' }}>{(track.person_detection_confidence * 100).toFixed(0)}%</p>
                </div>
                <div>
                  <span style={{ fontSize: '0.72rem', color: '#8B949E' }}>Evidence Quality:</span>
                  <p style={{ fontSize: '1rem', fontWeight: 700, color: '#F0F6FC' }}>{(track.evidence_quality * 100).toFixed(0)}%</p>
                </div>
              </div>

              {track.gps_location && (
                <div style={{ paddingTop: '0.5rem', borderTop: '1px solid #222C3E', fontSize: '0.78rem', color: '#10B981', display: 'flex', alignItems: 'center', gap: '0.35rem' }}>
                  <MapPin size={14} />
                  <span><b>GPS Position:</b> {track.gps_location.latitude.toFixed(5)}, {track.gps_location.longitude.toFixed(5)} ({track.gps_location.altitude_m.toFixed(0)}m Alt)</span>
                </div>
              )}
            </div>
          </div>

          {/* Attribute Table */}
          <div>
            <h4 style={{ fontSize: '0.82rem', fontWeight: 600, color: '#38BDF8', marginBottom: '0.5rem' }}>
              Attribute Breakdown Matrix
            </h4>
            <div style={{ background: '#0A0D14', borderRadius: '6px', border: '1px solid #222C3E', overflow: 'hidden' }}>
              <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '0.78rem', textAlign: 'left' }}>
                <thead>
                  <tr style={{ background: '#1A2130', color: '#8B949E', borderBottom: '1px solid #222C3E' }}>
                    <th style={{ padding: '0.55rem 0.75rem' }}>Attribute</th>
                    <th style={{ padding: '0.55rem 0.75rem' }}>Expected Target</th>
                    <th style={{ padding: '0.55rem 0.75rem' }}>Observed Sighting</th>
                    <th style={{ padding: '0.55rem 0.75rem' }}>Visibility</th>
                    <th style={{ padding: '0.55rem 0.75rem' }}>Match Score</th>
                  </tr>
                </thead>
                <tbody>
                  {Object.entries(track.attributes).map(([attrKey, detail]) => (
                    <tr key={attrKey} style={{ borderBottom: '1px solid #222C3E' }}>
                      <td style={{ padding: '0.55rem 0.75rem', fontWeight: 600, color: '#F0F6FC', textTransform: 'capitalize' }}>{attrKey.replace('_', ' ')}</td>
                      <td style={{ padding: '0.55rem 0.75rem', color: '#8B949E' }}>{detail.expected}</td>
                      <td style={{ padding: '0.55rem 0.75rem', color: '#F0F6FC' }}>{detail.observed}</td>
                      <td style={{ padding: '0.55rem 0.75rem' }}>
                        <span className={`status-tag ${detail.visibility === 'clear' ? 'status-tag-green' : 'status-tag-blue'}`} style={{ fontSize: '0.68rem', padding: '0.1rem 0.4rem' }}>
                          {detail.visibility}
                        </span>
                      </td>
                      <td style={{ padding: '0.55rem 0.75rem', fontWeight: 700, color: detail.score ? '#10B981' : '#8B949E' }}>
                        {detail.score !== null && detail.score !== undefined ? `${(detail.score * 100).toFixed(0)}%` : 'N/A'}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>

          {/* Operator Decision */}
          <div style={{ background: '#0A0D14', padding: '0.9rem', borderRadius: '6px', border: '1px solid #222C3E', display: 'flex', flexDirection: 'column', gap: '0.65rem' }}>
            <h4 style={{ fontSize: '0.82rem', fontWeight: 600, color: '#38BDF8' }}>
              Human SAR Operator Verification
            </h4>
            <div style={{ display: 'flex', gap: '0.6rem' }}>
              <button
                onClick={() => onFeedback(track.track_id, 'confirmed', notes)}
                style={{
                  flex: 1,
                  padding: '0.55rem',
                  borderRadius: '4px',
                  border: '1px solid #10B981',
                  background: 'rgba(16, 185, 129, 0.15)',
                  color: '#10B981',
                  fontWeight: 600,
                  fontSize: '0.78rem',
                  cursor: 'pointer',
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  gap: '0.35rem'
                }}
              >
                <CheckCircle2 size={14} /> Confirm Sighting
              </button>

              <button
                onClick={() => onFeedback(track.track_id, 'rejected', notes)}
                style={{
                  flex: 1,
                  padding: '0.55rem',
                  borderRadius: '4px',
                  border: '1px solid #EF4444',
                  background: 'rgba(239, 68, 68, 0.15)',
                  color: '#EF4444',
                  fontWeight: 600,
                  fontSize: '0.78rem',
                  cursor: 'pointer',
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  gap: '0.35rem'
                }}
              >
                <XCircle size={14} /> Reject Sighting
              </button>

              <button
                onClick={() => onFeedback(track.track_id, 'needs_research', notes)}
                style={{
                  flex: 1,
                  padding: '0.55rem',
                  borderRadius: '4px',
                  border: '1px solid #F59E0B',
                  background: 'rgba(245, 158, 11, 0.15)',
                  color: '#F59E0B',
                  fontWeight: 600,
                  fontSize: '0.78rem',
                  cursor: 'pointer',
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  gap: '0.35rem'
                }}
              >
                <AlertTriangle size={14} /> Flag Re-Search
              </button>
            </div>

            <textarea
              className="modern-input"
              rows={2}
              value={notes}
              onChange={(e) => setNotes(e.target.value)}
              placeholder="Add optional operator notes or comments..."
              style={{ resize: 'none' }}
            />
          </div>
        </div>
      </div>
    </div>
  );
};
