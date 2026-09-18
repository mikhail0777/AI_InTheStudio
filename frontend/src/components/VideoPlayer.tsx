import React, { useRef, useEffect, useState } from 'react';
import { TrackResult, SessionStatus, SearchResult } from '../types';
import { Film } from 'lucide-react';
import { candidateLabels, formatTime, reviewLabel } from '../review';

interface VideoPlayerProps {
  videoUrl: string | null;
  tracks: TrackResult[];
  status: SessionStatus | null;
  selectedTrack: TrackResult | null;
  selectedResult: SearchResult | null;
  onSelectTrack: (track: TrackResult) => void;
  jumpTimestamp?: number | null;
  jumpKey?: number;
}

export const VideoPlayer: React.FC<VideoPlayerProps> = ({ videoUrl, tracks, status, selectedTrack, selectedResult, onSelectTrack, jumpTimestamp, jumpKey }) => {
  const videoRef = useRef<HTMLVideoElement>(null);
  const [currentTime, setCurrentTime] = useState(0);
  const [duration, setDuration] = useState(0);
  const [dimensions, setDimensions] = useState({ width: 1, height: 1 });
  const [error, setError] = useState('');
  useEffect(() => { setCurrentTime(0); setDuration(0); setError(''); }, [videoUrl]);
  useEffect(() => {
    if (jumpTimestamp == null || !videoRef.current) return;
    videoRef.current.currentTime = jumpTimestamp;
    void videoRef.current.play().catch(() => { /* Native controls remain available if autoplay is blocked. */ });
  }, [jumpTimestamp, jumpKey]);
  const totalSeconds = duration || status?.total_duration_seconds || 0;
  const activeDetections = selectedResult?.entities.flatMap(entity => {
    const detection = entity.detections.reduce<typeof entity.detections[number] | null>((closest, item) =>
      !closest || Math.abs(item.timestamp_seconds - currentTime) < Math.abs(closest.timestamp_seconds - currentTime) ? item : closest, null);
    return detection && Math.abs(detection.timestamp_seconds - currentTime) <= .65 ? [{ entity, detection }] : [];
  }) || [];
  return <section className="card-module">
    <div className="row-between section-label"><h2 className="icon-line" style={{ fontSize: '1.25rem' }}><Film size={20} />Flight footage</h2><span className="muted">{formatTime(currentTime)} / {formatTime(totalSeconds)}</span></div>
    <div className="video-stage">
      {videoUrl ? <><video ref={videoRef} src={videoUrl} controls preload="metadata" onTimeUpdate={event => setCurrentTime(event.currentTarget.currentTime)} onLoadedMetadata={event => { setDuration(Number.isFinite(event.currentTarget.duration) ? event.currentTarget.duration : 0); setDimensions({ width: event.currentTarget.videoWidth || 1, height: event.currentTarget.videoHeight || 1 }); }} onError={() => setError('This recording could not be played in the browser. Check the file or use a browser-compatible MP4 encoding.')} />
        <div className="video-detection-overlay" aria-hidden="true">{activeDetections.map(({ entity, detection }) => {
          const [x1, y1, x2, y2] = detection.bbox;
          return <div key={`${entity.track_id}-${detection.detection_id}`} className="video-detection-box" style={{ left: `${x1 / dimensions.width * 100}%`, top: `${y1 / dimensions.height * 100}%`, width: `${(x2 - x1) / dimensions.width * 100}%`, height: `${(y2 - y1) / dimensions.height * 100}%` }}><span>{entity.label}</span></div>;
        })}</div></> : <div className="empty-state"><Film size={32} /><p>Your recording will appear here.</p></div>}
    </div>
    {error && <p role="alert" className="error-message">{error}</p>}
    <div className="row-between" style={{ marginTop: 20, marginBottom: 10 }}><span className="status-label">Evidence timeline</span><span className="muted" style={{ fontSize: 12 }}>{tracks.length} shown tracks</span></div>
    <div className="evidence-timeline">
      {totalSeconds > 0 && tracks.map(track => <button key={track.track_id} className={`timeline-marker ${track.classification} ${selectedTrack?.track_id === track.track_id ? 'selected' : ''}`} style={{ left: `${Math.min(99, Math.max(1, track.best_timestamp_seconds / totalSeconds * 100))}%` }} title={`Track #${track.track_id} · ${candidateLabels[track.classification]} · ${reviewLabel(track)} · ${formatTime(track.best_timestamp_seconds)}`} aria-label={`Review track ${track.track_id} at ${formatTime(track.best_timestamp_seconds)}`} onClick={() => { onSelectTrack(track); if (videoRef.current) videoRef.current.currentTime = track.best_timestamp_seconds; }} />)}
    </div>
  </section>;
};
