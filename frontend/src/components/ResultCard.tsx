import React, { useState } from 'react';
import { CheckCircle2, Clock, Maximize2, PlayCircle, X, XCircle } from 'lucide-react';
import type { SearchResult } from '../types';
import { formatTime } from '../utils/time';

const labels: Record<SearchResult['classification'], string> = {
  strong_match: 'Supported plate match', possible_match: 'Review-only OCR',
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
  const plateReadings = result.entities.flatMap(entity => entity.detections.flatMap(detection => {
    const readings = detection.attributes.license_plate_readings;
    return Array.isArray(readings) ? readings as Array<{ text?: string; confidence?: number }> : [];
  }));
  const requestedPlate = result.entities.map(entity => entity.attributes.requested_plate).find(Boolean);
  const sourceCrops = Array.from(new Set(result.entities.flatMap(entity => entity.detections.map(detection => detection.crop_path).filter((path): path is string => !!path))));
  const observedPlates = Array.from(new Set(plateReadings.map(reading => reading.text).filter(Boolean)));
  const observedVehicle = result.entities.map(entity => ({
    color: entity.attributes.vehicle_color,
    category: entity.attributes.vehicle_body_type,
    detected: entity.attributes.vehicle_detected,
  })).find(item => item.detected);
  const resultLabel = requestedPlate ? labels[result.classification] : (
    result.classification === 'strong_match' ? 'Supported vehicle sighting'
      : result.classification === 'possible_match' ? 'Review vehicle sighting'
        : labels[result.classification]
  );

  return <article className="result-card">
    <div className="row-between">
      <span className="status-label">Sighting · {requestedPlate ? String(requestedPlate) : 'vehicle profile'}</span>
      <span className={`candidate-badge ${result.classification}`}>{resultLabel}</span>
    </div>
    {result.best_frame_path && <button className="result-frame-button" onClick={() => setShowImage(true)} aria-label="Open full-size annotated evidence">
      <img className="result-frame" src={result.best_frame_path} alt="Annotated vehicle evidence" />
      <span><Maximize2 size={15} />View full size</span>
    </button>}
    <div className="track-summary">
      <button className="result-time-link" onClick={playOriginal}><Clock size={15} />{formatTime(result.start_seconds)}–{formatTime(result.end_seconds)} · play at {formatTime(result.best_timestamp_seconds)}</button>
      {!!observedPlates.length && <div className="plate-readout"><span>OCR read</span><strong>{observedPlates.join(' · ')}</strong></div>}
      {observedVehicle && <div className="vehicle-observation"><span>AI-observed vehicle</span><strong>{[observedVehicle.color, observedVehicle.category].filter(Boolean).join(' · ') || 'Vehicle detected'}</strong></div>}
      <span className="muted">{resultLabel}</span>
      <strong>{result.explanation}</strong>
      {result.evidence.map(item => <p key={item.criterion_id} className={`evidence-${item.assessment}`}>{item.explanation}</p>)}
      {result.clip_path && !clipError && <video className="result-clip" controls preload="metadata" src={result.clip_path} onError={() => setClipError(true)} />}
      {!!sourceCrops.length && <div className="result-crops" aria-label="Stored model crops">{sourceCrops.slice(0,4).map(path=><img key={path} src={path} alt="Stored model crop for this sighting"/>)}</div>}
      {clipError && <div className="clip-fallback"><span>The saved clip could not be played in this browser.</span><button className="btn-industrial" onClick={playOriginal}><PlayCircle size={16} />Play original footage</button></div>}
    </div>
    <div className="track-actions">
      <button className="btn-industrial" aria-pressed={result.human_feedback === 'confirmed'} onClick={() => onFeedback(result.result_id, 'confirmed')}><CheckCircle2 size={16} />Confirmed</button>
      <button className="btn-industrial" aria-pressed={result.human_feedback === 'rejected'} onClick={() => onFeedback(result.result_id, 'rejected')}><XCircle size={16} />Not this vehicle</button>
      <button className="btn-industrial" aria-label="Play result in original footage" onClick={playOriginal}><PlayCircle size={17} />Play</button>
    </div>
    {showImage && result.best_frame_path && <div className="evidence-lightbox" role="dialog" aria-modal="true" aria-label="Full-size annotated evidence" onClick={() => setShowImage(false)}>
      <div className="evidence-lightbox-content" onClick={event => event.stopPropagation()}>
        <button className="lightbox-close" onClick={() => setShowImage(false)} aria-label="Close full-size evidence"><X size={22} /></button>
        <img src={result.best_frame_path} alt="Full-size annotated vehicle evidence" />
        <button className="button button-primary" onClick={() => { setShowImage(false); playOriginal(); }}><PlayCircle size={17} />Play original at {formatTime(result.best_timestamp_seconds)}</button>
      </div>
    </div>}
  </article>;
};
