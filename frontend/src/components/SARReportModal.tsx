import React from 'react';
import { SessionStatus, TrackResult } from '../types';
import { X, Download, FileText, Shield } from 'lucide-react';

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
        maxWidth: '880px',
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
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem' }}>
            <FileText size={20} color="#38BDF8" />
            <div>
              <h2 style={{ fontSize: '1.15rem', fontWeight: 700, color: '#F0F6FC' }}>
                Post-Flight SAR Search Report
              </h2>
              <p style={{ fontSize: '0.75rem', color: '#8B949E' }}>
                Mission Session ID: {status.session_id}
              </p>
            </div>
          </div>
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem' }}>
            <a
              href={`/reports/report_${status.session_id}.html`}
              target="_blank"
              rel="noreferrer"
              className="btn-modern-primary"
              style={{ textDecoration: 'none' }}
            >
              <Download size={14} /> Download HTML Report
            </a>
            <button onClick={onClose} style={{ background: '#0A0D14', border: '1px solid #222C3E', borderRadius: '4px', color: '#8B949E', cursor: 'pointer', padding: '0.35rem' }}>
              <X size={18} />
            </button>
          </div>
        </div>

        {/* Report Content Body */}
        <div style={{ padding: '1.25rem', display: 'flex', flexDirection: 'column', gap: '1.25rem' }}>
          {/* Actionable Recommendations Callout */}
          <div style={{
            background: 'rgba(56, 189, 248, 0.06)',
            borderLeft: '3px solid #38BDF8',
            padding: '1rem',
            borderRadius: '4px',
            border: '1px solid #222C3E'
          }}>
            <h3 style={{ fontSize: '0.9rem', fontWeight: 600, color: '#38BDF8', display: 'flex', alignItems: 'center', gap: '0.4rem', marginBottom: '0.5rem' }}>
              <Shield size={16} /> Actionable SAR Recommendations
            </h3>
            <ul style={{ paddingLeft: '1.1rem', fontSize: '0.82rem', lineHeight: 1.6, color: '#F0F6FC' }}>
              {strongMatches.length > 0 ? (
                <li>
                  <b>Dispatch Ground Team:</b> Immediate ground team dispatch recommended to Track #{strongMatches[0].track_id}
                  {strongMatches[0].gps_location && ` at GPS (${strongMatches[0].gps_location.latitude.toFixed(5)}, ${strongMatches[0].gps_location.longitude.toFixed(5)})`} at timestamp {strongMatches[0].best_timestamp_seconds}s.
                </li>
              ) : possibleMatches.length > 0 ? (
                <li>
                  <b>Priority Sighting Review:</b> Confirm candidate sighting Track #{possibleMatches[0].track_id} at timestamp {possibleMatches[0].best_timestamp_seconds}s. Upper clothing and backpack match target profile.
                </li>
              ) : (
                <li>
                  <b>Expand Search Radius:</b> No high-confidence target candidates identified in current flight recording. Expand search grid to adjacent sectors.
                </li>
              )}
            </ul>
          </div>

          {/* Top Ranked Candidates Grid */}
          <div>
            <h3 style={{ fontSize: '0.88rem', fontWeight: 600, color: '#F0F6FC', marginBottom: '0.75rem' }}>
              Top Ranked Candidates ({tracks.length} Total Sighting Tracks)
            </h3>
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(240px, 1fr))', gap: '0.75rem' }}>
              {tracks.slice(0, 4).map((t) => (
                <div key={t.track_id} style={{
                  background: '#0A0D14',
                  border: '1px solid #222C3E',
                  borderRadius: '4px',
                  padding: '0.75rem',
                  display: 'flex',
                  alignItems: 'center',
                  gap: '0.75rem'
                }}>
                  <div style={{ width: '50px', height: '72px', borderRadius: '4px', overflow: 'hidden', background: '#000', flexShrink: 0 }}>
                    {t.best_frame_path ? (
                      <img src={t.best_frame_path} alt="" style={{ width: '100%', height: '100%', objectFit: 'cover' }} />
                    ) : null}
                  </div>
                  <div>
                    <span style={{ fontSize: '0.72rem', fontWeight: 600, color: '#38BDF8' }}>Track #{t.track_id}</span>
                    <p style={{ fontSize: '1.1rem', fontWeight: 700, color: '#F0F6FC' }}>{(t.final_ranking_score * 100).toFixed(0)}%</p>
                    <span style={{ fontSize: '0.7rem', color: '#8B949E' }}>Timestamp: {t.best_timestamp_seconds.toFixed(1)}s</span>
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
