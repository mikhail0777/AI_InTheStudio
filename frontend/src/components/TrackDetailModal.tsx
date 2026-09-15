import React, { useEffect, useState } from 'react';
import { TrackResult } from '../types';
import { X, CheckCircle2, XCircle, AlertTriangle, MapPin } from 'lucide-react';
import { attributeLabel, candidateLabels, formatTime, reviewLabel } from '../review';

interface TrackDetailModalProps {
  track: TrackResult | null;
  onClose: () => void;
  onFeedback: (trackId: number, status: 'confirmed' | 'rejected' | 'needs_research', notes?: string) => void;
}

export const TrackDetailModal: React.FC<TrackDetailModalProps> = ({ track, onClose, onFeedback }) => {
  const [notes, setNotes] = useState('');
  useEffect(() => { setNotes(track?.human_notes || ''); }, [track?.session_id, track?.track_id, track?.human_notes]);
  useEffect(() => {
    if (!track) return;
    const handleKey = (event: KeyboardEvent) => { if (event.key === 'Escape') onClose(); };
    document.addEventListener('keydown', handleKey);
    return () => document.removeEventListener('keydown', handleKey);
  }, [track, onClose]);
  if (!track) return null;
  const crops = track.cropped_samples.length ? track.cropped_samples : track.best_frame_path ? [track.best_frame_path] : [];

  return <div className="modal-overlay">
    <div className="modal-content" role="dialog" aria-modal="true" aria-labelledby="evidence-title">
      <div className="row-between modal-heading">
        <div><h2 id="evidence-title">Review evidence</h2><p className="muted">Track #{track.track_id} · {formatTime(track.first_seen_seconds)}–{formatTime(track.last_seen_seconds)}</p></div>
        <button onClick={onClose} className="btn-industrial" aria-label="Close evidence review"><X size={20} /></button>
      </div>
      <div className="evidence-layout">
        <section>
          <h3 className="status-label section-label">Original crops ({crops.length})</h3>
          <div className="crop-grid">{crops.map((path, index) => <a key={`${path}-${index}`} href={path} target="_blank" rel="noreferrer" className={`evidence-crop ${path === track.best_frame_path ? 'best' : ''}`} title="Open original image">
            <img src={path} alt={`Track ${track.track_id}, sample ${index + 1}`} />
            {path === track.best_frame_path && <span>Selected view</span>}
          </a>)}</div>
          {!crops.length && <p className="muted">No evidence images available.</p>}
        </section>
        <section className="evidence-summary">
          <span className={`candidate-badge ${track.classification}`}>{candidateLabels[track.classification]}</span>
          <strong>{reviewLabel(track)}</strong><p>{track.explanation}</p>
          <p className="muted">Automated visual comparison. Review the original footage before confirming a sighting.</p>
          {track.gps_location ? <div className="telemetry-reading">
            <strong className="icon-line"><MapPin size={16} />Drone position at capture</strong>
            <span>{track.gps_location.latitude.toFixed(5)}, {track.gps_location.longitude.toFixed(5)}</span>
            <span>SRT time: {track.gps_location.timestamp_seconds.toFixed(3)} s</span>
            {track.gps_location.relative_altitude_m != null && <span>Relative altitude: {track.gps_location.relative_altitude_m.toFixed(1)} m</span>}
            {track.gps_location.altitude_m != null && <span>Recorded altitude: {track.gps_location.altitude_m.toFixed(1)} m</span>}
            <small className="muted">The person's ground location has not been calculated.</small>
          </div> : <p className="muted">No aligned SRT position for this capture.</p>}
        </section>
      </div>
      <section className="review-section">
        <h3 className="status-label section-label">Visible attributes</h3>
        <div className="table-scroll"><table className="attribute-table">
          <thead><tr><th>Attribute</th><th>Description</th><th>Observed</th><th>Assessment</th></tr></thead>
          <tbody>{Object.entries(track.attributes).map(([key, detail]) => <tr key={key}>
            <th scope="row">{key.replace(/_/g, ' ')}</th><td>{detail.expected || 'Not specified'}</td><td>{detail.observed}<small className="muted">{detail.visibility.replace(/_/g, ' ')}</small></td>
            <td className={`assessment-${detail.assessment || 'unknown'}`}>{attributeLabel(detail)}
              {detail.evidence_paths?.map((path, i) => <small key={path}><a href={path} target="_blank" rel="noreferrer">View at {(detail.evidence_timestamps?.[i] ?? 0).toFixed(2)} s</a></small>)}
            </td>
          </tr>)}</tbody>
        </table></div>
      </section>
      {track.conflicting_evidence.length > 0 && <section className="review-section"><h3 className="status-label section-label">Conflicting evidence</h3><ul className="evidence-list">{track.conflicting_evidence.map((item, i) => <li key={i}>{item}</li>)}</ul></section>}
      {track.unknown_attributes.length > 0 && <p className="muted review-section">Not established: {track.unknown_attributes.map(a => a.replace(/_/g, ' ')).join(', ')}.</p>}
      <section className="review-section">
        <h3 className="status-label section-label">Reviewer decision</h3>
        <label className="field-label" htmlFor="review-notes">Review notes</label>
        <textarea id="review-notes" className="input-slot" rows={3} value={notes} onChange={e => setNotes(e.target.value)} placeholder="What did you verify in the original footage?" />
        <div className="review-actions">
          <button className="btn-industrial" aria-pressed={track.human_feedback === 'confirmed'} onClick={() => onFeedback(track.track_id, 'confirmed', notes)}><CheckCircle2 size={18} />Confirm sighting</button>
          <button className="btn-industrial" aria-pressed={track.human_feedback === 'rejected'} onClick={() => onFeedback(track.track_id, 'rejected', notes)}><XCircle size={18} />Reject sighting</button>
          <button className="btn-industrial" aria-pressed={track.human_feedback === 'needs_research'} onClick={() => onFeedback(track.track_id, 'needs_research', notes)}><AlertTriangle size={18} />Needs review</button>
        </div>
      </section>
    </div>
  </div>;
};
