import React from 'react';
import { SearchResult, SessionStatus, TrackResult } from '../types';
import { X, Download, FileText } from 'lucide-react';
import { candidateLabels, formatTime, isReviewCandidate, reviewLabel } from '../review';

interface SARReportModalProps { status: SessionStatus | null; tracks: TrackResult[]; results: SearchResult[]; onClose: () => void; }

export const SARReportModal: React.FC<SARReportModalProps> = ({ status, tracks, results, onClose }) => {
  if (!status) return null;
  const candidates = tracks.filter(isReviewCandidate);
  const confirmed = tracks.filter(t => t.human_feedback === 'confirmed');
  const rejected = tracks.filter(t => t.human_feedback === 'rejected');
  const generic = !!status.search_query;
  return <div className="modal-overlay"><div className="modal-content" role="dialog" aria-modal="true" aria-labelledby="report-title">
    <div className="row-between modal-heading">
      <div><h2 id="report-title" className="icon-line"><FileText size={22} />Recording review</h2><p className="muted">Session {status.session_id}</p></div>
      <button onClick={onClose} className="btn-industrial" aria-label="Close report"><X size={20} /></button>
    </div>
    <p>{confirmed.length} confirmed by a reviewer · {rejected.length} rejected · {tracks.length} total tracks</p>
    <p className="form-hint" style={{ margin: '16px 0 24px' }}>Automated candidates require review against the original footage. No candidates does not establish that the recording contains no person. Positions describe the drone at capture.</p>
    <a href={`/api/sessions/${status.session_id}/report`} target="_blank" rel="noreferrer" className="btn-industrial"><Download size={16} />Open full evidence report</a>
    {!generic && <section className="review-section"><h3 className="status-label section-label">Candidates for review ({candidates.length})</h3>
      <div className="report-grid">{candidates.map(t => <div className="report-candidate" key={t.track_id}>
        {t.best_frame_path && <img src={t.best_frame_path} alt={`Track ${t.track_id} evidence`} />}
        <div><strong>Track #{t.track_id}</strong><p>{candidateLabels[t.classification]}</p><p className="muted">{reviewLabel(t)}</p><p>{formatTime(t.best_timestamp_seconds)}</p></div>
      </div>)}</div>
      {!candidates.length && <p className="muted">No candidates in the review queue. The full report includes low-similarity and rejected tracks.</p>}
    </section>}
    {generic && <section className="review-section"><h3 className="status-label section-label">Ranked results ({results.length})</h3>
      <div className="report-grid">{results.map(result => <div className="report-candidate" key={result.result_id}>
        {result.best_frame_path && <img src={result.best_frame_path} alt="Search evidence" />}
        <div><strong>{result.classification.replace(/_/g, ' ')}</strong><p>{result.explanation}</p><p>{formatTime(result.best_timestamp_seconds)}</p></div>
      </div>)}</div>
      {!results.length && <p className="muted">No localized candidates were produced from the analyzed frames.</p>}
    </section>}
  </div></div>;
};
