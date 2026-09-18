import React, { useState } from 'react';
import { CheckCircle2, Clock, Maximize2, PlayCircle, X, XCircle } from 'lucide-react';
import type { SearchResult } from '../types';
import { formatTime } from '../review';

const labels: Record<SearchResult['classification'], string> = {
  strong_match: 'Strong match', possible_match: 'Possible match',
  unlikely_match: 'Unlikely match', insufficient_visibility: 'Insufficient visibility',
  unsupported_query: 'Unsupported query',
};

interface Props {
  result: SearchResult;
  onJumpToTime: (seconds: number) => void;
  onSelectResult: (result: SearchResult) => void;
  onFeedback: (id: string, status: 'confirmed' | 'rejected' | 'needs_research') => void;
}

export const ResultCard: React.FC<Props> = ({ result, onJumpToTime, onSelectResult, onFeedback }) => {
  const [showImage, setShowImage] = useState(false);
  const [clipError, setClipError] = useState(false);
  const playOriginal = () => { onSelectResult(result); onJumpToTime(result.best_timestamp_seconds); };
  return <article className="card-module track-card result-card">
    <div className="row-between">
      <span className="status-label">{result.entities.map(entity => entity.label).join(', ') || 'Event'}</span>
      <span className={`candidate-badge ${result.classification}`}>{labels[result.classification]}</span>
    </div>
    {result.best_frame_path && <button className="result-frame-button" onClick={() => setShowImage(true)} aria-label="Open full-size annotated evidence">
      <img className="result-frame" src={result.best_frame_path} alt="Annotated matching evidence" />
      <span><Maximize2 size={15} />View full size</span>
    </button>}
    <div className="track-summary">
      <button className="result-time-link" onClick={playOriginal}><Clock size={15} />{formatTime(result.start_seconds)}–{formatTime(result.end_seconds)} · play at {formatTime(result.best_timestamp_seconds)}</button>
      <div className="entity-chips" aria-label="Highlighted participants">{result.entities.map(entity => <span key={entity.track_id}>{entity.label} · {entity.track_id}</span>)}</div>
      <span className="muted">Evidence score {(result.overall_score * 100).toFixed(0)}% · interpreted within the {labels[result.classification].toLowerCase()} class</span>
      <strong>{result.explanation}</strong>
      {result.evidence.map(item => <p key={item.criterion_id} className={`evidence-${item.assessment}`}>
        {item.kind}: {item.explanation}
      </p>)}
      {result.clip_path && !clipError && <video className="result-clip" controls preload="metadata" src={result.clip_path} onError={() => setClipError(true)} />}
      {clipError && <div className="clip-fallback"><span>This saved clip uses an older browser-incompatible encoding.</span><button className="btn-industrial" onClick={playOriginal}><PlayCircle size={16} />Play in original footage</button></div>}
    </div>
    <div className="track-actions">
      <button className="btn-industrial" aria-pressed={result.human_feedback === 'confirmed'} onClick={() => onFeedback(result.result_id, 'confirmed')}><CheckCircle2 size={16} />Correct</button>
      <button className="btn-industrial" aria-pressed={result.human_feedback === 'rejected'} onClick={() => onFeedback(result.result_id, 'rejected')}><XCircle size={16} />Incorrect</button>
      <button className="btn-industrial" aria-label="Play result in original footage" onClick={playOriginal}><PlayCircle size={17} />Play</button>
    </div>
    {showImage && result.best_frame_path && <div className="evidence-lightbox" role="dialog" aria-modal="true" aria-label="Full-size annotated evidence" onClick={() => setShowImage(false)}>
      <div className="evidence-lightbox-content" onClick={event => event.stopPropagation()}>
        <button className="lightbox-close" onClick={() => setShowImage(false)} aria-label="Close full-size evidence"><X size={22} /></button>
        <img src={result.best_frame_path} alt="Full-size annotated matching evidence" />
        <button className="btn-industrial btn-primary" onClick={() => { setShowImage(false); playOriginal(); }}><PlayCircle size={17} />Play original at {formatTime(result.best_timestamp_seconds)}</button>
      </div>
    </div>}
  </article>;
};
