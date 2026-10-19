import React, { useEffect, useRef, useState } from 'react';
import type { SearchResult, SessionStatus } from '../types';
import { Film, ShieldCheck } from 'lucide-react';
import { formatTime } from '../utils/time';

interface Props { videoUrl: string | null; status: SessionStatus | null; selectedResult: SearchResult | null; jumpTimestamp?: number | null; jumpKey?: number; }

export const VideoPlayer: React.FC<Props> = ({ videoUrl, status, selectedResult, jumpTimestamp, jumpKey }) => {
  const videoRef = useRef<HTMLVideoElement>(null);
  const [currentTime, setCurrentTime] = useState(0); const [duration, setDuration] = useState(0);
  const [dimensions, setDimensions] = useState({ width: 1, height: 1 }); const [error, setError] = useState('');
  useEffect(() => { setCurrentTime(0); setDuration(0); setError(''); }, [videoUrl]);
  useEffect(() => { if (jumpTimestamp == null || !videoRef.current) return; videoRef.current.currentTime = jumpTimestamp; void videoRef.current.play().catch(() => undefined); }, [jumpTimestamp, jumpKey]);
  const totalSeconds = duration || status?.total_duration_seconds || 0;
  const activeDetections = selectedResult?.entities.flatMap(entity => {
    const detection = entity.detections.reduce<typeof entity.detections[number] | null>((closest, item) => !closest || Math.abs(item.timestamp_seconds - currentTime) < Math.abs(closest.timestamp_seconds - currentTime) ? item : closest, null);
    return detection && Math.abs(detection.timestamp_seconds - currentTime) <= .65 ? [{ entity, detection }] : [];
  }) || [];
  return <section className="surface video-panel">
    <div className="row-between video-heading"><div><span className="eyebrow">Source footage</span><h2>Security recording</h2></div><div className="video-meta"><ShieldCheck size={14} /><span>Original preserved</span><strong>{formatTime(currentTime)} / {formatTime(totalSeconds)}</strong></div></div>
    <div className="video-stage">{videoUrl ? <><video ref={videoRef} src={videoUrl} controls preload="metadata" onTimeUpdate={e => setCurrentTime(e.currentTarget.currentTime)} onLoadedMetadata={e => { setDuration(Number.isFinite(e.currentTarget.duration) ? e.currentTarget.duration : 0); setDimensions({ width: e.currentTarget.videoWidth || 1, height: e.currentTarget.videoHeight || 1 }); }} onError={() => setError('This recording could not be played in the browser.')} /><div className="video-detection-overlay" aria-hidden="true">{activeDetections.map(({ entity, detection }) => { const [x1, y1, x2, y2] = detection.bbox; return <div key={`${entity.track_id}-${detection.detection_id}`} className="video-detection-box" style={{ left: `${x1 / dimensions.width * 100}%`, top: `${y1 / dimensions.height * 100}%`, width: `${(x2 - x1) / dimensions.width * 100}%`, height: `${(y2 - y1) / dimensions.height * 100}%` }}><span>{entity.label}</span></div>; })}</div></> : <div className="video-empty"><div className="video-empty-icon"><Film size={28} /></div><strong>No recording loaded</strong><p>Choose footage in case setup to begin the investigation.</p></div>}</div>
    {error && <p role="alert" className="error-message">{error}</p>}
  </section>;
};
