import React from 'react';
import { SessionStatus, TrackResult } from '../types';
import { X, Download, FileText, CheckCircle2, AlertTriangle, Shield, MapPin } from 'lucide-react';

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
      background: 'rgba(0,0,0,0.85)',
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
        maxWidth: '900px',
        width: '100%',
        maxHeight: '90vh',
        overflowY: 'auto',
        display: 'flex',
        flexDirection: 'column',
        boxShadow: '0 25px 60px rgba(0,0,0,0.9)'
      }}>
        {/* Header */}
        <div style={{
          padding: '1.2rem 1.5rem',
          borderBottom: '1px solid #1E293B',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          background: '#0F172A'
        }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.8rem' }}>
            <FileText size={24} color="#38BDF8" />
            <div>
              <h2 style={{ fontSize: '1.25rem', fontWeight: 800, color: '#F8FAFC' }}>
                Post-Flight SAR Search Report
              </h2>
              <p style={{ fontSize: '0.8rem', color: '#94A3B8' }}>
                Mission Session ID: {status.session_id}
              </p>
            </div>
          </div>
          <div style={{ display: 'flex', gap: '0.8rem' }}>
            <a
              href={`/reports/report_${status.session_id}.html`}
              target="_blank"
              rel="noreferrer"
              className="btn btn-primary"
              style={{ textDecoration: 'none' }}
            >
              <Download size={16} /> Download HTML Report
            </a>
            <button onClick={onClose} style={{ background: 'none', border: 'none', color: '#94A3B8', cursor: 'pointer' }}>
              <X size={24} />
            </button>
          </div>
        </div>

        {/* Report Content Body */}
        <div style={{ padding: '1.5rem', display: 'flex', flexDirection: 'column', gap: '1.5rem' }}>
          {/* Actionable Recommendations Callout */}
          <div style={{
            background: 'rgba(56, 189, 248, 0.08)',
            borderLeft: '4px solid #38BDF8',
            padding: '1.2rem',
            borderRadius: '6px'
          }}>
            <h3 style={{ fontSize: '0.95rem', fontWeight: 700, color: '#38BDF8', display: 'flex', alignItems: 'center', gap: '0.5rem', marginBottom: '0.6rem' }}>
              <Shield size={18} /> Actionable SAR Recommendations for Ground Team
            </h3>
            <ul style={{ paddingLeft: '1.2rem', fontSize: '0.88rem', lineHeight: 1.6, color: '#F8FAFC' }}>
              {strongMatches.length > 0 ? (
                <li>
                  <b>Dispatch SAR Team:</b> Immediate ground team dispatch recommended to Track #{strongMatches[0].track_id}
                  {strongMatches[0].gps_location && ` at GPS (${strongMatches[0].gps_location.latitude}, ${strongMatches[0].gps_location.longitude})`} at timestamp {strongMatches[0].best_timestamp_seconds}s.
                </li>
              ) : possibleMatches.length > 0 ? (
                <li>
                  <b>Priority Review:</b> Confirm candidate sighting Track #{possibleMatches[0].track_id} at timestamp {possibleMatches[0].best_timestamp_seconds}s. Red upper clothing and blue backpack match missing person target description.
                </li>
              ) : (
                <li>
                  <b>Expand Search Grid:</b> No conclusive match detected in this recording sector. Recommend re-flying adjacent grid or relaxing optional color shade constraints.
                </li>
              )}
              <li>
                <b>Re-flight Recommendation:</b> Re-fly dense canopy sector at 30m altitude with 45-degree camera pitch to eliminate vegetation shadow occlusion.
              </li>
            </ul>
          </div>

          {/* Mission Statistics */}
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: '1rem' }}>
            <div style={{ background: '#0F172A', padding: '1rem', borderRadius: '8px', border: '1px solid #1E293B', textAlign: 'center' }}>
              <span style={{ fontSize: '0.75rem', color: '#94A3B8', textTransform: 'uppercase' }}>Total Flight Time</span>
              <p style={{ fontSize: '1.4rem', fontWeight: 800, color: '#F8FAFC' }}>{status.total_duration_seconds}s</p>
            </div>
            <div style={{ background: '#0F172A', padding: '1rem', borderRadius: '8px', border: '1px solid #1E293B', textAlign: 'center' }}>
              <span style={{ fontSize: '0.75rem', color: '#94A3B8', textTransform: 'uppercase' }}>People Detected</span>
              <p style={{ fontSize: '1.4rem', fontWeight: 800, color: '#38BDF8' }}>{status.people_detected_count}</p>
            </div>
            <div style={{ background: '#0F172A', padding: '1rem', borderRadius: '8px', border: '1px solid #1E293B', textAlign: 'center' }}>
              <span style={{ fontSize: '0.75rem', color: '#94A3B8', textTransform: 'uppercase' }}>Unique Tracks</span>
              <p style={{ fontSize: '1.4rem', fontWeight: 800, color: '#F8FAFC' }}>{status.unique_tracks_count}</p>
            </div>
            <div style={{ background: '#0F172A', padding: '1rem', borderRadius: '8px', border: '1px solid #1E293B', textAlign: 'center' }}>
              <span style={{ fontSize: '0.75rem', color: '#94A3B8', textTransform: 'uppercase' }}>Top Rank Score</span>
              <p style={{ fontSize: '1.4rem', fontWeight: 800, color: '#10B981' }}>
                {tracks.length > 0 ? `${(tracks[0].final_ranking_score * 100).toFixed(0)}%` : '0%'}
              </p>
            </div>
          </div>

          {/* Ranked Sightings List */}
          <div>
            <h3 style={{ fontSize: '0.95rem', fontWeight: 700, color: '#38BDF8', marginBottom: '0.8rem' }}>
              Ranked Candidate Sightings Summary
            </h3>
            <div style={{ display: 'flex', flexDirection: 'column', gap: '0.6rem' }}>
              {tracks.map((t) => (
                <div key={t.track_id} style={{
                  background: '#0F172A',
                  border: '1px solid #1E293B',
                  borderRadius: '6px',
                  padding: '0.8rem 1rem',
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'space-between'
                }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: '1rem' }}>
                    <span className={`badge ${t.classification === 'strong_match' ? 'badge-strong' : (t.classification === 'possible_match' ? 'badge-possible' : 'badge-unlikely')}`}>
                      {t.classification.replace('_', ' ')}
                    </span>
                    <div>
                      <b style={{ color: '#F8FAFC' }}>Track #{t.track_id}</b> @ {t.best_timestamp_seconds}s
                      {t.gps_location && <span style={{ color: '#10B981', marginLeft: '8px', fontSize: '0.8rem' }}>GPS: ({t.gps_location.latitude}, {t.gps_location.longitude})</span>}
                    </div>
                  </div>
                  <div style={{ fontSize: '0.9rem', fontWeight: 800, color: '#38BDF8' }}>
                    Score: {(t.final_ranking_score * 100).toFixed(0)}%
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
