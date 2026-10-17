import React from 'react';
import { SearchResult, SessionStatus } from '../types';
import { X, Download, FileText } from 'lucide-react';
import { formatTime } from '../utils/time';

interface Props { status: SessionStatus | null; results: SearchResult[]; onClose: () => void; }

export const SARReportModal: React.FC<Props> = ({ status, results, onClose }) => {
  if (!status) return null;
  const confirmed = results.filter(result => result.human_feedback === 'confirmed').length;
  const rejected = results.filter(result => result.human_feedback === 'rejected').length;
  return <div className="modal-overlay"><div className="modal-content" role="dialog" aria-modal="true" aria-labelledby="report-title">
    <div className="row-between modal-heading">
      <div><h2 id="report-title" className="icon-line"><FileText size={22} />Evidence report</h2><p className="muted">Investigation {status.session_id}</p></div>
      <button onClick={onClose} className="btn-industrial" aria-label="Close report"><X size={20} /></button>
    </div>
    <p>{confirmed} confirmed · {rejected} rejected · {results.length} total sightings</p>
    {status.processing_mode && <p><strong>{status.processing_mode} scan</strong>{status.stage_timings?.total !== undefined ? ` · ${status.stage_timings.total.toFixed(2)} seconds total` : ''}</p>}
    <p className="form-hint" style={{ margin: '16px 0 24px' }}>Automated plate reads require review against the original footage. A missing result does not prove that a vehicle was absent.</p>
    <a href={`/api/sessions/${status.session_id}/report`} target="_blank" rel="noreferrer" className="btn-industrial"><Download size={16} />Open printable report</a>
    <section className="review-section"><h3 className="status-label section-label">Vehicle sightings ({results.length})</h3>
      <div className="report-grid">{results.map(result => <div className="report-candidate" key={result.result_id}>
        {result.best_frame_path && <img src={result.best_frame_path} alt="Vehicle evidence" />}
        <div><strong>{result.classification === 'strong_match' ? 'Supported plate match' : 'Review-only OCR'}</strong><p>{result.explanation}</p><p>{formatTime(result.best_timestamp_seconds)}</p></div>
      </div>)}</div>
      {!results.length && <p className="muted">No supported vehicle sightings were produced at the selected scan depth.</p>}
    </section>
  </div></div>;
};
