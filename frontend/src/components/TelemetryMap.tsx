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

    // Background fill
    ctx.fillStyle = '#0A0D14';
    ctx.fillRect(0, 0, width, height);

    // Grid Lines
    ctx.strokeStyle = '#1D2535';
    ctx.lineWidth = 1;
    for (let x = 0; x < width; x += 30) {
      ctx.beginPath();
      ctx.moveTo(x, 0);
      ctx.lineTo(x, height);
      ctx.stroke();
    }
    for (let y = 0; y < height; y += 30) {
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
    ctx.strokeStyle = '#38BDF8';
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
      const color = t.classification === 'strong_match' ? '#10B981' : (t.classification === 'possible_match' ? '#F59E0B' : '#EF4444');

      ctx.fillStyle = color;
      ctx.beginPath();
      ctx.arc(pt.x, pt.y, 5, 0, Math.PI * 2);
      ctx.fill();
      ctx.strokeStyle = '#FFFFFF';
      ctx.lineWidth = 1.5;
      ctx.stroke();

      ctx.fillStyle = '#8B949E';
      ctx.font = '600 9px Inter';
      ctx.fillText(`#${t.track_id}`, pt.x + 8, pt.y - 4);
    });
  }, [tracks]);

  return (
    <div className="modern-panel" style={{ padding: '1rem', gap: '0.75rem' }}>
      <div className="modern-panel-header" style={{ margin: '-1rem -1rem 0 -1rem' }}>
        <span className="modern-panel-title">
          <Map size={16} color="#38BDF8" /> Tactical Flight GPS Radar
        </span>
        <span className="status-tag status-tag-blue" style={{ fontSize: '0.68rem' }}>
          {gpsTracks.length} GPS Points
        </span>
      </div>

      <div style={{ position: 'relative', width: '100%', aspectRatio: '16/9', borderRadius: '4px', overflow: 'hidden', border: '1px solid #222C3E' }}>
        <canvas
          ref={canvasRef}
          width={360}
          height={202}
          style={{ width: '100%', height: '100%', display: 'block' }}
        />
        {gpsTracks.length === 0 && (
          <div style={{ position: 'absolute', inset: 0, display: 'flex', alignItems: 'center', justifyContent: 'center', color: '#6E7681', fontSize: '0.78rem' }}>
            No Telemetry Log Attached
          </div>
        )}
      </div>
    </div>
  );
};
