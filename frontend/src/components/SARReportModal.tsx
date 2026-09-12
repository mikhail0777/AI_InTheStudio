import React from 'react';
import { SessionStatus, TrackResult } from '../types';
import { X, Download, FileText, Shield, Crosshair } from 'lucide-react';

interface SARReportModalProps {
  status: SessionStatus | null;
  tracks: TrackResult[];
  onClose: () => void;
}

export const SARReportModal: React.FC<SARReportModalProps> = ({ status, tracks, onClose }) => {
  if (!status) return null;

  const strongMatches = tracks.filter(t => t.classification === 'strong_match');
  const possibleMatches = tracks.filter(t => t.classification === 'possible_match');

  return (
    <div className="modal-overlay">
      <div className="modal-content">
        <div className="screws" />
        
        {/* Header */}
        <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', marginBottom: '32px' }}>
          <div>
            <div style={{ display: 'flex', alignItems: 'center', gap: '16px', marginBottom: '8px' }}>
              <div style={{ padding: '8px', background: 'var(--bg-chassis)', boxShadow: 'var(--shadow-recessed)', borderRadius: 'var(--radius-full)' }}>
                <FileText size={20} color="var(--accent-orange)" />
              </div>
              <h2 style={{ fontSize: '1.5rem', margin: 0 }}>POST-FLIGHT SAR REPORT</h2>
            </div>
            <p className="status-label" style={{ color: 'var(--text-muted)' }}>
              MISSION SESSION ID: {status.session_id}
            </p>
          </div>
          
          <div style={{ display: 'flex', alignItems: 'center', gap: '16px' }}>
            <a
              href={`/reports/report_${status.session_id}.html`}
              target="_blank"
              rel="noreferrer"
              className="btn-industrial"
              style={{ padding: '8px 16px' }}
            >
              <Download size={16} /> DOWNLOAD EXPORT
            </a>
            <button onClick={onClose} className="btn-industrial" style={{ padding: '12px', borderRadius: 'var(--radius-full)' }}>
              <X size={20} />
            </button>
          </div>
        </div>

        {/* Report Content Body */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: '32px' }}>
          
          {/* Actionable Recommendations Callout */}
          <div className="card-module" style={{ padding: '24px', background: 'var(--bg-panel)' }}>
            <h3 style={{ fontSize: '1.1rem', fontWeight: 800, display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '16px', color: 'var(--accent-orange)' }}>
              <Shield size={20} /> ACTIONABLE RECOMMENDATIONS
            </h3>
            <ul style={{ paddingLeft: '24px', fontSize: '14px', fontWeight: 600, color: 'var(--text-primary)' }}>
              {strongMatches.length > 0 ? (
                <li>
                  <b style={{ color: '#22c55e' }}>DISPATCH GROUND TEAM:</b> Immediate ground team dispatch recommended to Track #{strongMatches[0].track_id}
                  {strongMatches[0].gps_location && ` at GPS (${strongMatches[0].gps_location.latitude.toFixed(5)}, ${strongMatches[0].gps_location.longitude.toFixed(5)})`} at timestamp {strongMatches[0].best_timestamp_seconds}s.
                </li>
              ) : possibleMatches.length > 0 ? (
                <li>
                  <b style={{ color: '#eab308' }}>PRIORITY SIGHTING REVIEW:</b> Confirm candidate sighting Track #{possibleMatches[0].track_id} at timestamp {possibleMatches[0].best_timestamp_seconds}s. Upper clothing and backpack match target profile.
                </li>
              ) : (
                <li>
                  <b>EXPAND SEARCH RADIUS:</b> No high-confidence target candidates identified in current flight recording. Expand search grid to adjacent sectors.
                </li>
              )}
            </ul>
          </div>

          {/* Top Ranked Candidates Grid */}
          <div className="card-module" style={{ padding: '24px' }}>
            <h3 className="status-label" style={{ marginBottom: '24px' }}>
              TOP RANKED CANDIDATES ({tracks.length} TOTAL SIGHTING TRACKS)
            </h3>
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(280px, 1fr))', gap: '24px' }}>
              {tracks.slice(0, 4).map((t) => (
                <div key={t.track_id} className="input-slot" style={{
                  display: 'flex',
                  alignItems: 'center',
                  gap: '16px',
                  padding: '12px',
                  background: 'var(--bg-chassis)'
                }}>
                  <div className="screen-panel" style={{ width: '64px', height: '80px', flexShrink: 0, padding: 0 }}>
                    {t.best_frame_path ? (
                      <img src={t.best_frame_path} alt="" style={{ width: '100%', height: '100%', objectFit: 'cover' }} />
                    ) : (
                      <Crosshair size={24} style={{ opacity: 0.2, margin: '28px auto 0' }} />
                    )}
                  </div>
                  <div style={{ display: 'flex', flexDirection: 'column', gap: '4px' }}>
                    <span className="status-label">MODULE #{t.track_id}</span>
                    <p style={{ fontSize: '1.25rem', fontWeight: 800, color: 'var(--text-primary)', fontFamily: 'var(--font-mono)' }}>{(t.final_ranking_score * 100).toFixed(0)}%</p>
                    <span className="status-label">T: {t.best_timestamp_seconds.toFixed(1)}S</span>
                  </div>
                </div>
              ))}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};
