import React from 'react';
import { CheckCircle2, Clock, Eye, XCircle } from 'lucide-react';
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
  onFeedback: (id: string, status: 'confirmed' | 'rejected' | 'needs_research') => void;
}

export const ResultCard: React.FC<Props> = ({ result, onJumpToTime, onFeedback }) => (
  <article className="card-module track-card result-card">
    <div className="row-between">
      <span className="status-label">{result.entities.map(entity => entity.label).join(', ') || 'Event'}</span>
      <span className={`candidate-badge ${result.classification}`}>{labels[result.classification]}</span>
    </div>
    {result.best_frame_path && <img className="result-frame" src={result.best_frame_path} alt="Annotated matching evidence" />}
    <div className="track-summary">
      <span className="icon-line"><Clock size={15} />{formatTime(result.start_seconds)}–{formatTime(result.end_seconds)}</span>
      <div className="entity-chips" aria-label="Highlighted participants">{result.entities.map(entity => <span key={entity.track_id}>{entity.label} · {entity.track_id}</span>)}</div>
      <span className="muted">Ranking score {(result.overall_score * 100).toFixed(0)}%</span>
      <strong>{result.explanation}</strong>
      {result.evidence.map(item => <p key={item.criterion_id} className={`evidence-${item.assessment}`}>
        {item.kind}: {item.explanation}
      </p>)}
      {result.clip_path && <video className="result-clip" controls preload="metadata" src={result.clip_path} />}
    </div>
    <div className="track-actions">
      <button className="btn-industrial" aria-pressed={result.human_feedback === 'confirmed'} onClick={() => onFeedback(result.result_id, 'confirmed')}><CheckCircle2 size={16} />Correct</button>
      <button className="btn-industrial" aria-pressed={result.human_feedback === 'rejected'} onClick={() => onFeedback(result.result_id, 'rejected')}><XCircle size={16} />Incorrect</button>
      <button className="btn-industrial" aria-label="Play result in original footage" onClick={() => onJumpToTime(result.best_timestamp_seconds)}><Eye size={17} /></button>
    </div>
  </article>
);
