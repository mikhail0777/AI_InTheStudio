import React, { useRef, useEffect } from 'react';
import { TrackResult } from '../types';
import { Map } from 'lucide-react';

interface TelemetryMapProps {
  tracks: TrackResult[];
  onSelectTrack: (track: TrackResult) => void;
}

export const TelemetryMap: React.FC<TelemetryMapProps> = ({ tracks, onSelectTrack }) => {
  const canvasRef = useRef<HTMLCanvasElement>(null);

  const gpsTracks = tracks.filter(t => t.gps_location !== null && t.gps_location !== undefined);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext('2d');
    if (!ctx) return;

    const width = canvas.width;
    const height = canvas.height;

    // Background fill (Deep radar blue/gray)
    ctx.fillStyle = '#1e293b';
    ctx.fillRect(0, 0, width, height);

    // Grid Lines (Blueprint grid)
    ctx.strokeStyle = 'rgba(255, 255, 255, 0.05)';
    ctx.lineWidth = 1;
    for (let x = 0; x < width; x += 20) {
      ctx.beginPath();
      ctx.moveTo(x, 0);
      ctx.lineTo(x, height);
      ctx.stroke();
    }
    for (let y = 0; y < height; y += 20) {
      ctx.beginPath();
      ctx.moveTo(0, y);
      ctx.lineTo(width, y);
      ctx.stroke();
    }

    if (gpsTracks.length === 0) return;

    // Bounding Box
    const lats = gpsTracks.map(t => t.gps_location!.latitude);
    const lons = gpsTracks.map(t => t.gps_location!.longitude);
    const minLat = Math.min(...lats);
    const maxLat = Math.max(...lats);
    const minLon = Math.min(...lons);
    const maxLon = Math.max(...lons);

    const padLat = Math.max(0.0001, (maxLat - minLat) * 0.25);
    const padLon = Math.max(0.0001, (maxLon - minLon) * 0.25);

    const mapMinLat = minLat - padLat;
    const mapMaxLat = maxLat + padLat;
    const mapMinLon = minLon - padLon;
    const mapMaxLon = maxLon + padLon;

    const toScreen = (lat: number, lon: number) => {
      const x = ((lon - mapMinLon) / (mapMaxLon - mapMinLon)) * (width - 60) + 30;
      const y = height - (((lat - mapMinLat) / (mapMaxLat - mapMinLat)) * (height - 60) + 30);
      return { x, y };
    };

    // Flight Path Line
    ctx.strokeStyle = 'rgba(255, 255, 255, 0.2)';
    ctx.lineWidth = 2;
    ctx.setLineDash([4, 4]);
    ctx.beginPath();
    gpsTracks.forEach((t, i) => {
      const pt = toScreen(t.gps_location!.latitude, t.gps_location!.longitude);
      if (i === 0) ctx.moveTo(pt.x, pt.y);
      else ctx.lineTo(pt.x, pt.y);
    });
    ctx.stroke();
    ctx.setLineDash([]);

    // Candidate Points
    gpsTracks.forEach((t) => {
      const pt = toScreen(t.gps_location!.latitude, t.gps_location!.longitude);
      const color = t.classification === 'strong_match' ? '#22c55e' : (t.classification === 'possible_match' ? '#eab308' : '#ff4757');

      ctx.fillStyle = color;
      ctx.beginPath();
      ctx.arc(pt.x, pt.y, 4, 0, Math.PI * 2);
      ctx.fill();

      // Inner dot
      ctx.fillStyle = '#ffffff';
      ctx.beginPath();
      ctx.arc(pt.x, pt.y, 1.5, 0, Math.PI * 2);
      ctx.fill();

      ctx.fillStyle = 'rgba(255, 255, 255, 0.7)';
      ctx.font = '700 10px "JetBrains Mono"';
      ctx.fillText(`M${t.track_id}`, pt.x + 8, pt.y - 4);
    });
  }, [tracks]);

  return (
    <div className="card-module" style={{ padding: '24px', display: 'flex', flexDirection: 'column', gap: '24px' }}>
      <div className="screws" />
      <div className="vent-slots">
        <div className="vent-slot" />
        <div className="vent-slot" />
        <div className="vent-slot" />
      </div>

      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', zIndex: 10 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
          <div style={{ padding: '8px', background: 'var(--bg-chassis)', boxShadow: 'var(--shadow-recessed)', borderRadius: 'var(--radius-full)' }}>
            <Map size={20} color="var(--accent-orange)" />
          </div>
          <div>
            <h2 style={{ fontSize: '1.25rem', margin: 0 }}>TELEMETRY</h2>
            <div className="status-label">GPS RADAR</div>
          </div>
        </div>
        <div className="input-slot" style={{ width: 'auto', padding: '6px 12px', display: 'flex', alignItems: 'center', gap: '8px', color: 'var(--text-primary)', fontWeight: 700 }}>
          <span className={`led ${gpsTracks.length > 0 ? 'green animate-pulse-led' : 'red'}`} />
          {gpsTracks.length} NODES
        </div>
      </div>

      <div className="screen-panel" style={{ position: 'relative', width: '100%', aspectRatio: '16/9', zIndex: 10 }}>
        <canvas
          ref={canvasRef}
          width={360}
          height={202}
          style={{ width: '100%', height: '100%', display: 'block', cursor: 'crosshair', position: 'relative', zIndex: 5 }}
        />
        {gpsTracks.length === 0 && (
          <div style={{ position: 'absolute', inset: 0, display: 'flex', alignItems: 'center', justifyContent: 'center', color: 'var(--text-muted)', fontSize: '13px', zIndex: 10 }} className="font-mono font-bold">
            NO TELEMETRY LOG ATTACHED
          </div>
        )}
      </div>
    </div>
  );
};
