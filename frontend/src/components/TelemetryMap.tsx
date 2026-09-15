import React, { useMemo } from 'react';
import { GPSPoint, TrackResult } from '../types';
import { MapPin } from 'lucide-react';
import { formatTime } from '../review';

interface TelemetryMapProps { tracks: TrackResult[]; points: GPSPoint[]; onSelectTrack: (track: TrackResult) => void; }
const validPoint = (p: GPSPoint) => Number.isFinite(p.latitude) && Number.isFinite(p.longitude) && Math.abs(p.latitude) <= 90 && Math.abs(p.longitude) <= 180;

export const TelemetryMap: React.FC<TelemetryMapProps> = ({ tracks, points, onSelectTrack }) => {
  const plotted = useMemo(() => {
    const chronological = points.filter(validPoint).slice().sort((a, b) => a.timestamp_seconds - b.timestamp_seconds);
    const locatedTracks = tracks.filter(t => t.gps_location && validPoint(t.gps_location));
    const all = [...chronological, ...locatedTracks.map(t => t.gps_location!)];
    if (!all.length) return null;
    let minLat = Infinity, maxLat = -Infinity, minLon = Infinity, maxLon = -Infinity;
    all.forEach(p => { minLat = Math.min(minLat, p.latitude); maxLat = Math.max(maxLat, p.latitude); minLon = Math.min(minLon, p.longitude); maxLon = Math.max(maxLon, p.longitude); });
    const middleLat = (minLat + maxLat) / 2, middleLon = (minLon + maxLon) / 2;
    const longitudeScale = Math.max(0.01, Math.cos(middleLat * Math.PI / 180));
    const scale = Math.min(300 / Math.max((maxLon - minLon) * longitudeScale, 0.00002), 180 / Math.max(maxLat - minLat, 0.00002));
    const project = (p: GPSPoint) => ({ x: 180 + (p.longitude - middleLon) * longitudeScale * scale, y: 110 - (p.latitude - middleLat) * scale });
    // Bound SVG size for long recordings while retaining chronological order and endpoints.
    const stride = Math.max(1, Math.ceil(chronological.length / 2000));
    const path = chronological.filter((_, i) => i % stride === 0 || i === chronological.length - 1).map(p => { const xy = project(p); return `${xy.x},${xy.y}`; }).join(' ');
    return { path, tracks: locatedTracks.map(track => ({ track, ...project(track.gps_location!) })), start: chronological[0] ? project(chronological[0]) : null };
  }, [tracks, points]);
  return <section className="card-module">
    <h2 className="icon-line" style={{ fontSize: '1.25rem', marginBottom: 16 }}><MapPin size={20} />Drone telemetry</h2>
    <div className="telemetry-map">
      <svg viewBox="0 0 360 220" role="img" aria-label="Chronological SRT drone flight path with capture positions">
        <text x="336" y="22" fill="#64748b" fontSize="11">N ↑</text>
        {plotted?.path && <polyline points={plotted.path} fill="none" stroke="#8294ac" strokeWidth="2" />}
        {plotted?.start && <circle cx={plotted.start.x} cy={plotted.start.y} r="4" fill="#64748b"><title>Start of SRT flight path</title></circle>}
        {plotted?.tracks.map(({ track, x, y }) => <g key={track.track_id} role="button" tabIndex={0} aria-label={`Review track ${track.track_id} at drone capture position`} onClick={() => onSelectTrack(track)} onKeyDown={e => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); onSelectTrack(track); } }} className="map-marker">
          <circle cx={x} cy={y} r="7" fill={track.human_feedback === 'confirmed' ? '#20714b' : '#bd6426'} stroke="white" strokeWidth="2" />
          <title>Track #{track.track_id} · {formatTime(track.best_timestamp_seconds)} · drone position</title>
          <text x={x + 9} y={y - 8} fill="#26364b" fontSize="10">#{track.track_id}</text>
        </g>)}
      </svg>
      {!plotted && <p className="telemetry-empty">No SRT coordinates available.</p>}
    </div>
    <p className="muted" style={{ fontSize: 12, marginTop: 12 }}>SRT flight path · dots mark drone positions when evidence was captured. Ground locations of people are not calculated.</p>
  </section>;
};
