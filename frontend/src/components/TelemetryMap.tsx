import React, { useRef, useEffect } from 'react';
import { TrackResult } from '../types';
import { Map, Navigation } from 'lucide-react';

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

    // Clear background grid
    ctx.fillStyle = '#0B0F19';
    ctx.fillRect(0, 0, width, height);

    // Draw tactical grid lines
    ctx.strokeStyle = '#1E293B';
    ctx.lineWidth = 1;
    for (let x = 0; x < width; x += 40) {
      ctx.beginPath();
      ctx.moveTo(x, 0);
      ctx.lineTo(x, height);
      ctx.stroke();
    }
    for (let y = 0; y < height; y += 40) {
      ctx.beginPath();
      ctx.moveTo(0, y);
      ctx.lineTo(width, y);
      ctx.stroke();
    }

    if (gpsTracks.length === 0) return;

    // Calculate GPS bounding box
    const lats = gpsTracks.map(t => t.gps_location!.latitude);
    const lons = gpsTracks.map(t => t.gps_location!.longitude);
    const minLat = Math.min(...lats);
    const maxLat = Math.max(...lats);
    const minLon = Math.min(...lons);
    const maxLon = Math.max(...lons);

    const padLat = Math.max(0.0001, (maxLat - minLat) * 0.2);
    const padLon = Math.max(0.0001, (maxLon - minLon) * 0.2);

    const mapMinLat = minLat - padLat;
    const mapMaxLat = maxLat + padLat;
    const mapMinLon = minLon - padLon;
    const mapMaxLon = maxLon + padLon;

    const toScreen = (lat: number, lon: number) => {
      const x = ((lon - mapMinLon) / (mapMaxLon - mapMinLon)) * (width - 80) + 40;
      const y = height - (((lat - mapMinLat) / (mapMaxLat - mapMinLat)) * (height - 80) + 40);
      return { x, y };
    };

    // Draw flight track line connecting sightings
    ctx.strokeStyle = '#0284C7';
    ctx.lineWidth = 2.5;
    ctx.setLineDash([5, 5]);
    ctx.beginPath();
    gpsTracks.forEach((t, i) => {
      const pt = toScreen(t.gps_location!.latitude, t.gps_location!.longitude);
      if (i === 0) ctx.moveTo(pt.x, pt.y);
      else ctx.lineTo(pt.x, pt.y);
    });
    ctx.stroke();
    ctx.setLineDash([]);

    // Draw candidate sighting markers
    gpsTracks.forEach((t) => {
      const pt = toScreen(t.gps_location!.latitude, t.gps_location!.longitude);
      const color = t.classification === 'strong_match' ? '#10B981' : (t.classification === 'possible_match' ? '#F59E0B' : '#EF4444');

      // Outer halo
      ctx.fillStyle = color;
      ctx.globalAlpha = 0.25;
      ctx.beginPath();
      ctx.arc(pt.x, pt.y, 14, 0, Math.PI * 2);
      ctx.fill();

      // Solid center dot
      ctx.globalAlpha = 1.0;
      ctx.beginPath();
      ctx.arc(pt.x, pt.y, 7, 0, Math.PI * 2);
      ctx.fill();
      ctx.strokeStyle = '#FFFFFF';
      ctx.lineWidth = 1.5;
      ctx.stroke();

      // Label text
      ctx.fillStyle = '#F8FAFC';
      ctx.font = '10px Inter, sans-serif';
      ctx.fillText(`Track #${t.track_id}`, pt.x + 12, pt.y + 4);
    });
  }, [gpsTracks]);

  return (
    <div className="panel" style={{ height: '240px' }}>
      <div className="panel-header">
        <span className="panel-title">
          <Map size={18} /> Tactical Flight Path & Sightings Map
        </span>
        <span style={{ fontSize: '0.75rem', color: 'var(--text-muted)' }}>
          {gpsTracks.length > 0 ? `${gpsTracks.length} GPS Correlated Points` : 'No Telemetry Data Attached'}
        </span>
      </div>

      <div style={{ position: 'relative', width: '100%', height: '100%', borderRadius: '6px', overflow: 'hidden' }}>
        <canvas ref={canvasRef} width={600} height={180} style={{ width: '100%', height: '100%' }} />
      </div>
    </div>
  );
};
