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

  const getLedColor = (classification: string) => {
    switch (classification) {
      case 'strong_match': return 'green';
      case 'possible_match': return 'yellow';
      case 'unlikely_match': return 'red';
      default: return 'yellow';
    }
  };

  return (
    <div className="modal-overlay">
      <div className="modal-content">
        <div className="screws" />
        
        {/* Header */}
        <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', marginBottom: '32px' }}>
          <div>
            <div style={{ display: 'flex', alignItems: 'center', gap: '16px', marginBottom: '8px' }}>
              <h2 style={{ fontSize: '1.5rem', margin: 0 }}>MODULE DEEP INSPECTION</h2>
              <div className="status-label" style={{ display: 'flex', alignItems: 'center', gap: '6px', background: 'var(--bg-panel)', padding: '6px 12px', borderRadius: 'var(--radius-sm)', boxShadow: 'var(--shadow-sharp)' }}>
                <span className={`led ${getLedColor(track.classification)}`} />
                {track.classification.replace('_', ' ')}
              </div>
            </div>
            <p className="status-label" style={{ color: 'var(--text-muted)' }}>
              TRACK #{track.track_id} | {track.first_seen_seconds.toFixed(1)}S TO {track.last_seen_seconds.toFixed(1)}S
            </p>
          </div>
          
          <button onClick={onClose} className="btn-industrial" style={{ padding: '12px', borderRadius: 'var(--radius-full)' }}>
            <X size={20} />
          </button>
        </div>

        {/* Content Body */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: '32px' }}>
          
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '32px' }}>
            {/* Multi-frame Crops */}
            <div className="card-module" style={{ padding: '16px' }}>
              <h4 className="status-label" style={{ marginBottom: '16px' }}>TEMPORAL CROPS ({track.cropped_samples.length})</h4>
              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: '12px' }}>
                {track.cropped_samples.map((cropPath, idx) => (
                  <div key={idx} className="screen-panel" style={{
                    aspectRatio: '2/3',
                    border: cropPath === track.best_frame_path ? '2px solid var(--accent-orange)' : 'none',
                    boxShadow: cropPath === track.best_frame_path ? 'var(--shadow-glow)' : 'var(--shadow-recessed)'
                  }}>
                    <img src={cropPath} alt={`Crop ${idx}`} style={{ width: '100%', height: '100%', objectFit: 'cover' }} />
                  </div>
                ))}
              </div>
            </div>

            {/* Score Metrics */}
            <div className="card-module" style={{ padding: '24px', display: 'flex', flexDirection: 'column', gap: '24px' }}>
              <h4 className="status-label">CONFIDENCE BREAKDOWN</h4>
              
              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '16px' }}>
                <div className="input-slot" style={{ display: 'flex', flexDirection: 'column', gap: '4px', alignItems: 'center', textAlign: 'center' }}>
                  <span className="status-label">FINAL SCORE</span>
                  <span style={{ fontSize: '24px', fontWeight: 800, color: 'var(--text-primary)' }}>{(track.final_ranking_score * 100).toFixed(0)}%</span>
                </div>
                <div className="input-slot" style={{ display: 'flex', flexDirection: 'column', gap: '4px', alignItems: 'center', textAlign: 'center' }}>
                  <span className="status-label">APPEARANCE</span>
                  <span style={{ fontSize: '24px', fontWeight: 800, color: '#22c55e' }}>{(track.appearance_similarity * 100).toFixed(0)}%</span>
                </div>
                <div className="input-slot" style={{ display: 'flex', flexDirection: 'column', gap: '4px', alignItems: 'center', textAlign: 'center' }}>
                  <span className="status-label">DETECTOR CONF</span>
                  <span style={{ fontSize: '18px', fontWeight: 700 }}>{(track.person_detection_confidence * 100).toFixed(0)}%</span>
                </div>
                <div className="input-slot" style={{ display: 'flex', flexDirection: 'column', gap: '4px', alignItems: 'center', textAlign: 'center' }}>
                  <span className="status-label">EVIDENCE QUALITY</span>
                  <span style={{ fontSize: '18px', fontWeight: 700 }}>{(track.evidence_quality * 100).toFixed(0)}%</span>
                </div>
              </div>

              {track.gps_location && (
                <div className="input-slot" style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', gap: '8px' }}>
                  <MapPin size={16} color="var(--accent-orange)" />
                  <span style={{ fontSize: '13px', fontWeight: 600 }}>{track.gps_location.latitude.toFixed(5)}, {track.gps_location.longitude.toFixed(5)} ({track.gps_location.altitude_m.toFixed(0)}M)</span>
                </div>
              )}
            </div>
          </div>

          {/* Attribute Table */}
          <div className="card-module" style={{ padding: '24px' }}>
            <h4 className="status-label" style={{ marginBottom: '16px' }}>ATTRIBUTE MATRIX</h4>
            <div className="input-slot" style={{ padding: '0', overflow: 'hidden' }}>
              <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '13px', textAlign: 'left', fontFamily: 'var(--font-mono)' }}>
                <thead>
                  <tr style={{ borderBottom: '2px solid rgba(0,0,0,0.1)' }}>
                    <th style={{ padding: '12px 16px', color: 'var(--text-muted)' }}>ATTRIBUTE</th>
                    <th style={{ padding: '12px 16px', color: 'var(--text-muted)' }}>EXPECTED</th>
                    <th style={{ padding: '12px 16px', color: 'var(--text-muted)' }}>OBSERVED</th>
                    <th style={{ padding: '12px 16px', color: 'var(--text-muted)' }}>MATCH</th>
                  </tr>
                </thead>
                <tbody>
                  {Object.entries(track.attributes).map(([attrKey, detail], idx) => (
                    <tr key={attrKey} style={{ borderBottom: idx !== Object.entries(track.attributes).length - 1 ? '1px solid rgba(0,0,0,0.05)' : 'none' }}>
                      <td style={{ padding: '12px 16px', fontWeight: 700 }}>{attrKey.replace('_', ' ').toUpperCase()}</td>
                      <td style={{ padding: '12px 16px' }}>{detail.expected.toUpperCase()}</td>
                      <td style={{ padding: '12px 16px' }}>{detail.observed.toUpperCase()}</td>
                      <td style={{ padding: '12px 16px', fontWeight: 700, color: detail.score ? '#22c55e' : 'var(--text-muted)' }}>
                        {detail.score !== null && detail.score !== undefined ? `${(detail.score * 100).toFixed(0)}%` : 'N/A'}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>

          {/* Operator Decision */}
          <div className="card-module" style={{ padding: '24px', display: 'flex', flexDirection: 'column', gap: '16px' }}>
            <h4 className="status-label">SAR OPERATOR VERIFICATION</h4>
            
            <div style={{ display: 'flex', gap: '16px' }}>
              <button className="btn-industrial" onClick={() => onFeedback(track.track_id, 'confirmed', notes)} style={{ flex: 1 }}>
                <CheckCircle2 size={18} color="#22c55e" /> CONFIRM SIGHTING
              </button>

              <button className="btn-industrial" onClick={() => onFeedback(track.track_id, 'rejected', notes)} style={{ flex: 1 }}>
                <XCircle size={18} color="var(--accent-orange)" /> REJECT SIGHTING
              </button>

              <button className="btn-industrial" onClick={() => onFeedback(track.track_id, 'needs_research', notes)} style={{ flex: 1 }}>
                <AlertTriangle size={18} color="#eab308" /> FLAG RE-SEARCH
              </button>
            </div>

            <textarea
              className="input-slot"
              rows={2}
              value={notes}
              onChange={(e) => setNotes(e.target.value)}
              placeholder="APPEND MISSION NOTES..."
              style={{ resize: 'none', marginTop: '8px' }}
            />
          </div>

        </div>
      </div>
    </div>
  );
};
