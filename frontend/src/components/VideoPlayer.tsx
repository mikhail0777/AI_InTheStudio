import React, { useRef, useEffect, useState } from 'react';
import { TrackResult, SessionStatus } from '../types';
import { Play, Pause, Crosshair, Film } from 'lucide-react';

interface VideoPlayerProps {
  videoUrl: string | null;
  tracks: TrackResult[];
  status: SessionStatus | null;
  selectedTrack: TrackResult | null;
  onSelectTrack: (track: TrackResult) => void;
  jumpTimestamp?: number | null;
}

export const VideoPlayer: React.FC<VideoPlayerProps> = ({
  videoUrl,
  tracks,
  status,
  selectedTrack,
  onSelectTrack,
  jumpTimestamp
}) => {
  const videoRef = useRef<HTMLVideoElement>(null);
  const [isPlaying, setIsPlaying] = useState(false);
  const [currentTime, setCurrentTime] = useState(0);
  const [duration, setDuration] = useState(0);

  useEffect(() => {
    if (jumpTimestamp !== null && jumpTimestamp !== undefined && videoRef.current) {
      videoRef.current.currentTime = jumpTimestamp;
      videoRef.current.play();
      setIsPlaying(true);
    }
  }, [jumpTimestamp]);

  const togglePlay = () => {
    if (videoRef.current) {
      if (isPlaying) {
        videoRef.current.pause();
      } else {
        videoRef.current.play();
      }
      setIsPlaying(!isPlaying);
    }
  };

  const handleTimeUpdate = () => {
    if (videoRef.current) {
      setCurrentTime(videoRef.current.currentTime);
      setDuration(videoRef.current.duration || 0);
    }
  };

  const formatTime = (seconds: number) => {
    const m = Math.floor(seconds / 60);
    const s = Math.floor(seconds % 60);
    return `${m.toString().padStart(2, '0')}:${s.toString().padStart(2, '0')}`;
  };

  const getMarkerColor = (classification: string) => {
    switch (classification) {
      case 'strong_match': return '#22c55e';
      case 'possible_match': return '#eab308';
      case 'unlikely_match': return 'var(--accent-orange)';
      default: return 'var(--text-muted)';
    }
  };

  return (
    <div className="card-module" style={{ padding: '24px', display: 'flex', flexDirection: 'column', gap: '24px' }}>
      <div className="screws" />
      <div className="vent-slots">
        <div className="vent-slot" />
        <div className="vent-slot" />
        <div className="vent-slot" />
      </div>

      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', paddingRight: '24px' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
          <div style={{ padding: '8px', background: 'var(--bg-chassis)', boxShadow: 'var(--shadow-recessed)', borderRadius: 'var(--radius-full)' }}>
            <Crosshair size={20} color="var(--accent-orange)" />
          </div>
          <div>
            <h2 style={{ fontSize: '1.25rem', margin: 0 }}>FLIGHT FOOTAGE</h2>
            <div className="status-label">MAIN FEED / TIMELINE</div>
          </div>
        </div>
        <div className="input-slot" style={{ width: 'auto', padding: '8px 16px', display: 'flex', alignItems: 'center', gap: '8px', color: 'var(--accent-orange)', fontWeight: 700 }}>
          <span className={`led ${isPlaying ? 'green animate-pulse-led' : 'red'}`} />
          {formatTime(currentTime)} / {formatTime(duration)}
        </div>
      </div>

      <div style={{ display: 'flex', flexDirection: 'column', gap: '24px' }}>
        {/* Video Container (CRT Style) */}
        <div className="screen-panel" style={{
          aspectRatio: '16/9',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          border: '12px solid #0f172a'
        }}>
          {videoUrl ? (
            <video
              ref={videoRef}
              src={videoUrl}
              style={{ width: '100%', height: '100%', objectFit: 'contain', zIndex: 10, position: 'relative' }}
              onTimeUpdate={handleTimeUpdate}
              onLoadedMetadata={handleTimeUpdate}
              onEnded={() => setIsPlaying(false)}
            />
          ) : (
            <div style={{ color: 'var(--accent-orange)', textAlign: 'center', zIndex: 10, display: 'flex', flexDirection: 'column', gap: '16px', alignItems: 'center' }} className="font-mono">
              <Film size={48} style={{ opacity: 0.5 }} />
              <div>
                <p style={{ fontSize: '18px', fontWeight: 700 }}>NO SIGNAL DETECTED</p>
                <p style={{ fontSize: '12px', opacity: 0.7, marginTop: '8px' }}>AWAITING VIDEO STREAM INPUT</p>
              </div>
            </div>
          )}

          {videoUrl && (
            <button
              onClick={togglePlay}
              className="btn-industrial"
              style={{
                position: 'absolute',
                bottom: '24px',
                right: '24px',
                width: '64px',
                height: '64px',
                borderRadius: 'var(--radius-full)',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                padding: '0',
                zIndex: 20
              }}
            >
              {isPlaying ? <Pause size={28} /> : <Play size={28} style={{ marginLeft: '4px' }} />}
            </button>
          )}
        </div>

        {/* Industrial Timeline Bar */}
        <div style={{ padding: '16px', background: 'var(--bg-panel)', borderRadius: 'var(--radius-md)', boxShadow: 'var(--shadow-sharp)' }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '16px' }}>
            <span className="status-label">CANDIDATE SIGHTING MARKERS</span>
            <span className="status-label" style={{ color: 'var(--text-primary)' }}>{tracks.length} DETECTIONS</span>
          </div>

          <div className="input-slot" style={{ position: 'relative', height: '24px', padding: '0 4px', display: 'flex', alignItems: 'center', background: '#e2e8f0' }}>
            <div style={{
              width: duration > 0 ? `${(currentTime / duration) * 100}%` : '0%',
              height: '8px',
              background: 'var(--accent-orange)',
              borderRadius: 'var(--radius-full)',
              boxShadow: 'var(--shadow-glow)'
            }} />

            {(status?.total_duration_seconds || duration) > 0 && tracks.map((t) => {
              const totalSec = status?.total_duration_seconds || duration;
              const posPercent = (t.best_timestamp_seconds / totalSec) * 100;
              const isSelected = selectedTrack?.track_id === t.track_id;
              const markerColor = getMarkerColor(t.classification);

              return (
                <button
                  key={t.track_id}
                  onClick={() => {
                    onSelectTrack(t);
                    if (videoRef.current) {
                      videoRef.current.currentTime = t.best_timestamp_seconds;
                    }
                  }}
                  title={`Track #${t.track_id} - Score: ${(t.final_ranking_score * 100).toFixed(0)}% at ${t.best_timestamp_seconds.toFixed(1)}s`}
                  style={{
                    position: 'absolute',
                    left: `${posPercent}%`,
                    transform: 'translateX(-50%)',
                    width: isSelected ? '16px' : '12px',
                    height: isSelected ? '32px' : '24px',
                    backgroundColor: markerColor,
                    borderRadius: 'var(--radius-sm)',
                    boxShadow: isSelected ? '0 0 10px rgba(0,0,0,0.5)' : 'var(--shadow-floating)',
                    border: '2px solid var(--bg-chassis)',
                    cursor: 'pointer',
                    zIndex: isSelected ? 10 : 5,
                    transition: 'all 150ms cubic-bezier(0.175, 0.885, 0.32, 1.275)'
                  }}
                />
              );
            })}
          </div>
        </div>
      </div>
    </div>
  );
};
