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
      case 'strong_match': return '#10B981';
      case 'possible_match': return '#F59E0B';
      case 'unlikely_match': return '#EF4444';
      default: return '#8B949E';
    }
  };

  return (
    <div className="modern-panel" style={{ padding: '1rem', gap: '0.85rem' }}>
      <div className="modern-panel-header" style={{ margin: '-1rem -1rem 0 -1rem' }}>
        <span className="modern-panel-title">
          <Crosshair size={16} color="#38BDF8" /> Flight Footage Player & Timeline
        </span>
        <span style={{ fontSize: '0.78rem', color: '#38BDF8', fontFamily: 'var(--font-mono)', fontWeight: 600 }}>
          {formatTime(currentTime)} / {formatTime(duration)}
        </span>
      </div>

      {/* Video Container */}
      <div style={{
        position: 'relative',
        background: '#000000',
        borderRadius: '6px',
        overflow: 'hidden',
        aspectRatio: '16/9',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        border: '1px solid #222C3E'
      }}>
        {videoUrl ? (
          <video
            ref={videoRef}
            src={videoUrl}
            style={{ width: '100%', height: '100%', objectFit: 'contain' }}
            onTimeUpdate={handleTimeUpdate}
            onLoadedMetadata={handleTimeUpdate}
            onEnded={() => setIsPlaying(false)}
          />
        ) : (
          <div style={{ color: '#6E7681', textAlign: 'center', padding: '2rem' }}>
            <Film size={36} color="#222C3E" style={{ marginBottom: '0.4rem' }} />
            <p style={{ fontSize: '0.85rem', fontWeight: 600, color: '#8B949E' }}>No Flight Video Loaded</p>
            <p style={{ fontSize: '0.75rem', color: '#6E7681' }}>Select or upload video file to start timeline player.</p>
          </div>
        )}

        {videoUrl && (
          <button
            onClick={togglePlay}
            style={{
              position: 'absolute',
              background: 'rgba(18, 23, 34, 0.85)',
              border: '1px solid #2D3A52',
              borderRadius: '50%',
              width: '48px',
              height: '48px',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              color: '#F0F6FC',
              cursor: 'pointer',
              opacity: isPlaying ? 0.25 : 1,
              transition: 'opacity 0.15s ease'
            }}
            onMouseEnter={(e) => (e.currentTarget.style.opacity = '1')}
            onMouseLeave={(e) => (e.currentTarget.style.opacity = isPlaying ? '0.25' : '1')}
          >
            {isPlaying ? <Pause size={20} /> : <Play size={20} style={{ marginLeft: '2px' }} />}
          </button>
        )}
      </div>

      {/* Modern Clean Timeline Bar */}
      <div style={{ background: '#0A0D14', padding: '0.6rem 0.85rem', borderRadius: '6px', border: '1px solid #222C3E' }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '0.72rem', fontWeight: 600, color: '#8B949E', marginBottom: '0.35rem' }}>
          <span>Candidate Sighting Markers</span>
          <span style={{ color: '#38BDF8' }}>{tracks.length} Detections</span>
        </div>

        <div style={{ position: 'relative', height: '24px', display: 'flex', alignItems: 'center' }}>
          <div style={{
            position: 'absolute',
            width: '100%',
            height: '4px',
            background: '#222C3E',
            borderRadius: '2px',
            overflow: 'hidden'
          }}>
            <div style={{
              width: duration > 0 ? `${(currentTime / duration) * 100}%` : '0%',
              height: '100%',
              background: '#38BDF8'
            }} />
          </div>

          {duration > 0 && tracks.map((t) => {
            const posPercent = (t.best_timestamp_seconds / duration) * 100;
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
                  width: isSelected ? '12px' : '8px',
                  height: isSelected ? '12px' : '8px',
                  borderRadius: '50%',
                  backgroundColor: markerColor,
                  border: isSelected ? '2px solid #FFFFFF' : '1px solid #0A0D14',
                  cursor: 'pointer',
                  zIndex: isSelected ? 10 : 5,
                  transition: 'all 0.15s ease'
                }}
              />
            );
          })}
        </div>
      </div>
    </div>
  );
};
