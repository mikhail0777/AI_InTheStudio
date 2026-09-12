import React, { useState } from 'react';
import { TrackResult } from '../types';
import { X, CheckCircle2, XCircle, AlertTriangle, MapPin, Award, Layers } from 'lucide-react';

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
      background: 'rgba(0, 0, 0, 0.8)',
      backdropFilter: 'blur(8px)',
      display: 'flex',
      alignItems: 'center',
      justifyContent: 'center',
      zIndex: 1000,
      padding: '1.5rem'
    }}>
      <div style={{
        background: '#111827',
        border: '1px solid #334155',
        borderRadius: '12px',
        maxWidth: '850px',
        width: '100%',
        maxHeight: '90vh',
        overflowY: 'auto',
        display: 'flex',
        flexDirection: 'column',
        boxShadow: '0 20px 50px rgba(0, 0, 0, 0.8)'
      }}>
        {/* Modal Header */}
        <div style={{
          padding: '1.2rem 1.5rem',
          borderBottom: '1px solid #1E293B',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between'
        }}>
          <div>
            <h2 style={{ fontSize: '1.2rem', fontWeight: 800, color: '#F8FAFC', display: 'flex', alignItems: 'center', gap: '0.6rem' }}>
              Track #{track.track_id} - Evidence Deep Inspection
              <span className={`badge ${track.classification === 'strong_match' ? 'badge-strong' : (track.classification === 'possible_match' ? 'badge-possible' : 'badge-unlikely')}`}>
                {track.classification.replace('_', ' ')}
              </span>
            </h2>
            <p style={{ fontSize: '0.8rem', color: '#94A3B8' }}>
              Seen from {track.first_seen_seconds}s to {track.last_seen_seconds}s (Best Frame: {track.best_timestamp_seconds}s)
            </p>
          </div>
          <button onClick={onClose} style={{ background: 'none', border: 'none', color: '#94A3B8', cursor: 'pointer' }}>
            <X size={24} />
          </button>
        </div>

        {/* Modal Content */}
        <div style={{ padding: '1.5rem', display: 'flex', flexDirection: 'column', gap: '1.5rem' }}>
          {/* Top Grid: Multi-frame Crops & Primary Metrics */}
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '1.2rem' }}>
            {/* Multi-frame Crops */}
            <div>
              <h4 style={{ fontSize: '0.85rem', fontWeight: 700, color: '#38BDF8', marginBottom: '0.6rem' }}>
                Multi-Frame Temporal Crop Views ({track.cropped_samples.length})
              </h4>
              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: '0.5rem' }}>
                {track.cropped_samples.map((cropPath, idx) => (
                  <div key={idx} style={{
                    background: '#000000',
                    borderRadius: '6px',
                    overflow: 'hidden',
                    aspectRatio: '2/3',
                    border: cropPath === track.best_frame_path ? '2px solid #38BDF8' : '1px solid #1E293B'
                  }}>
                    <img src={cropPath} alt={`Crop ${idx}`} style={{ width: '100%', height: '100%', objectFit: 'cover' }} />
                  </div>
                ))}
              </div>
            </div>

            {/* Score & GPS Breakdown */}
            <div style={{ display: 'flex', flexDirection: 'column', gap: '0.8rem', background: '#0F172A', padding: '1rem', borderRadius: '8px', border: '1px solid #1E293B' }}>
              <h4 style={{ fontSize: '0.85rem', fontWeight: 700, color: '#38BDF8' }}>
                Scoring Breakdown
              </h4>
              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '0.6rem', fontSize: '0.85rem' }}>
                <div>
                  <span style={{ color: '#94A3B8' }}>Final Ranking Score:</span>
                  <p style={{ fontSize: '1.4rem', fontWeight: 800, color: '#38BDF8' }}>{(track.final_ranking_score * 100).toFixed(0)}%</p>
                </div>
                <div>
                  <span style={{ color: '#94A3B8' }}>Appearance Sim:</span>
                  <p style={{ fontSize: '1.4rem', fontWeight: 800, color: '#10B981' }}>{(track.appearance_similarity * 100).toFixed(0)}%</p>
                </div>
                <div>
                  <span style={{ color: '#94A3B8' }}>Detection Conf:</span>
                  <p style={{ fontSize: '1.1rem', fontWeight: 700 }}>{(track.person_detection_confidence * 100).toFixed(0)}%</p>
                </div>
                <div>
                  <span style={{ color: '#94A3B8' }}>Evidence Quality:</span>
                  <p style={{ fontSize: '1.1rem', fontWeight: 700 }}>{(track.evidence_quality * 100).toFixed(0)}%</p>
                </div>
              </div>

              {track.gps_location && (
                <div style={{ paddingTop: '0.6rem', borderTop: '1px solid #1E293B', fontSize: '0.85rem', color: '#10B981' }}>
                  <MapPin size={16} style={{ display: 'inline', marginRight: '4px' }} />
                  <b>GPS Location:</b> {track.gps_location.latitude}, {track.gps_location.longitude} (Alt: {track.gps_location.altitude_m}m)
                </div>
              )}
            </div>
          </div>

          {/* Attribute Comparison Matrix */}
          <div>
            <h4 style={{ fontSize: '0.85rem', fontWeight: 700, color: '#38BDF8', marginBottom: '0.6rem' }}>
              Attribute Comparison Matrix
            </h4>
            <div style={{ background: '#0F172A', borderRadius: '8px', border: '1px solid #1E293B', overflow: 'hidden' }}>
              <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '0.85rem', textAlign: 'left' }}>
                <thead>
                  <tr style={{ background: '#1E293B', color: '#94A3B8' }}>
                    <th style={{ padding: '0.6rem 0.8rem' }}>Attribute</th>
                    <th style={{ padding: '0.6rem 0.8rem' }}>Expected Target</th>
                    <th style={{ padding: '0.6rem 0.8rem' }}>Observed Sighting</th>
                    <th style={{ padding: '0.6rem 0.8rem' }}>Visibility</th>
                    <th style={{ padding: '0.6rem 0.8rem' }}>Match Score</th>
                  </tr>
                </thead>
                <tbody>
                  {Object.entries(track.attributes).map(([attrKey, detail]) => (
                    <tr key={attrKey} style={{ borderBottom: '1px solid #1E293B' }}>
                      <td style={{ padding: '0.6rem 0.8rem', fontWeight: 600, textTransform: 'capitalize' }}>{attrKey.replace('_', ' ')}</td>
                      <td style={{ padding: '0.6rem 0.8rem', color: '#94A3B8' }}>{detail.expected}</td>
                      <td style={{ padding: '0.6rem 0.8rem', color: '#F8FAFC' }}>{detail.observed}</td>
                      <td style={{ padding: '0.6rem 0.8rem' }}>
                        <span style={{ fontSize: '0.75rem', padding: '0.15rem 0.4rem', borderRadius: '4px', background: detail.visibility === 'clear' ? 'rgba(16,185,129,0.2)' : 'rgba(148,163,184,0.2)' }}>
                          {detail.visibility}
                        </span>
                      </td>
                      <td style={{ padding: '0.6rem 0.8rem', fontWeight: 700, color: detail.score ? '#10B981' : '#94A3B8' }}>
                        {detail.score !== null && detail.score !== undefined ? `${(detail.score * 100).toFixed(0)}%` : 'N/A'}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>

          {/* Human Feedback Operator Decision */}
          <div style={{ background: '#0F172A', padding: '1rem', borderRadius: '8px', border: '1px solid #334155', display: 'flex', flexDirection: 'column', gap: '0.8rem' }}>
            <h4 style={{ fontSize: '0.85rem', fontWeight: 700, color: '#38BDF8' }}>
              Human Operator Confirmation & Review
            </h4>
            <div style={{ display: 'flex', gap: '0.8rem' }}>
              <button
                className="btn btn-success"
                onClick={() => onFeedback(track.track_id, 'confirmed', notes)}
                style={{ flex: 1 }}
              >
                <CheckCircle2 size={16} /> Confirm Sighting Match
              </button>
              <button
                className="btn btn-danger"
                onClick={() => onFeedback(track.track_id, 'rejected', notes)}
                style={{ flex: 1 }}
              >
                <XCircle size={16} /> Reject Sighting
              </button>
              <button
                className="btn btn-warning"
                onClick={() => onFeedback(track.track_id, 'needs_research', notes)}
                style={{ flex: 1 }}
              >
                <AlertTriangle size={16} /> Flag for Re-Search
              </button>
            </div>
            <textarea
              className="textarea"
              rows={2}
              value={notes}
              onChange={(e) => setNotes(e.target.value)}
              placeholder="Add optional SAR operator notes or comments..."
            />
          </div>
        </div>
      </div>
    </div>
  );
};
