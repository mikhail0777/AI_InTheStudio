import React, { useRef, useEffect, useState } from 'react';
import { TrackResult, SessionStatus } from '../types';
import { Play, Pause, RotateCcw, Crosshair, MapPin } from 'lucide-react';

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
      default: return '#94A3B8';
    }
  };

  return (
    <div className="panel" style={{ gap: '0.8rem' }}>
      <div className="panel-header">
        <span className="panel-title">
          <Crosshair size={18} /> Drone Flight Footage Player & Interactive Timeline
        </span>
        <span style={{ fontSize: '0.8rem', color: 'var(--text-muted)', fontFamily: 'var(--font-mono)' }}>
          {formatTime(currentTime)} / {formatTime(duration)}
        </span>
      </div>

      {/* Video Container */}
      <div style={{
        position: 'relative',
        background: '#000000',
        borderRadius: '8px',
        overflow: 'hidden',
        aspectRatio: '16/9',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        border: '1px solid var(--border-color)'
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
          <div style={{ textAlign: 'center', color: 'var(--text-muted)', padding: '2rem' }}>
            <Crosshair size={48} color="#334155" style={{ marginBottom: '0.5rem' }} />
            <p style={{ fontWeight: 600 }}>No Drone Flight Video Loaded</p>
            <p style={{ fontSize: '0.8rem' }}>Upload video recording to launch analysis</p>
          </div>
        )}
      </div>

      {/* Interactive Detection Timeline */}
      <div style={{ display: 'flex', flexDirection: 'column', gap: '0.4rem' }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '0.75rem', color: 'var(--text-muted)' }}>
          <span>Detection Timeline (Click marker to jump to timestamp)</span>
          <span>{tracks.length} Candidate Sightings Found</span>
        </div>

        <div style={{
          position: 'relative',
          height: '24px',
          background: 'var(--bg-dark)',
          borderRadius: '6px',
          border: '1px solid var(--border-color)',
          cursor: 'pointer'
        }}
        onClick={(e) => {
          if (duration > 0 && videoRef.current) {
            const rect = e.currentTarget.getBoundingClientRect();
            const clickRatio = (e.clientX - rect.left) / rect.width;
            const newTime = clickRatio * duration;
            videoRef.current.currentTime = newTime;
          }
        }}>
          {/* Progress bar overlay */}
          <div style={{
            position: 'absolute',
            left: 0,
            top: 0,
            bottom: 0,
            width: `${duration > 0 ? (currentTime / duration) * 100 : 0}%`,
            background: 'rgba(56, 189, 248, 0.2)',
            borderRight: '2px solid #38BDF8',
            borderRadius: '6px 0 0 6px'
          }} />

          {/* Sighting markers */}
          {tracks.map((t) => {
            const leftPct = duration > 0 ? (t.best_timestamp_seconds / duration) * 100 : 0;
            const color = getMarkerColor(t.classification);
            const isSelected = selectedTrack?.track_id === t.track_id;

            return (
              <div
                key={t.track_id}
                title={`Track #${t.track_id} at ${t.best_timestamp_seconds}s (${t.classification})`}
                onClick={(e) => {
                  e.stopPropagation();
                  onSelectTrack(t);
                  if (videoRef.current) {
                    videoRef.current.currentTime = t.best_timestamp_seconds;
                    videoRef.current.play();
                    setIsPlaying(true);
                  }
                }}
                style={{
                  position: 'absolute',
                  left: `${leftPct}%`,
                  top: '50%',
                  transform: 'translate(-50%, -50%)',
                  width: isSelected ? '14px' : '10px',
                  height: isSelected ? '14px' : '10px',
                  borderRadius: '50%',
                  backgroundColor: color,
                  border: isSelected ? '2px solid #FFFFFF' : '1px solid #000000',
                  boxShadow: isSelected ? `0 0 10px ${color}` : 'none',
                  zIndex: isSelected ? 10 : 2,
                  transition: 'all 0.2s ease'
                }}
              />
            );
          })}
        </div>
      </div>
    </div>
  );
};
