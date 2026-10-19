import React, { useEffect, useState } from 'react';
import { History, MapPin, Search } from 'lucide-react';
import type { VehicleSighting } from '../types';

interface Props {
  sightings: VehicleSighting[];
  plate?: string;
  onSearch: (filters: Record<string, string | number | boolean | undefined>) => Promise<void>;
}

export const VehicleHistoryPanel: React.FC<Props> = ({ sightings, plate, onSearch }) => {
  const [plateFilter, setPlateFilter] = useState(plate || '');
  const [make, setMake] = useState(''); const [model, setModel] = useState('');
  const [year, setYear] = useState(''); const [color, setColor] = useState(''); const [bodyType, setBodyType] = useState('');
  const [afterHoursOnly, setAfterHoursOnly] = useState(false);
  const [pending, setPending] = useState(false);
  useEffect(() => { setPlateFilter(plate || ''); }, [plate]);
  const submit = async (event: React.FormEvent) => {
    event.preventDefault(); setPending(true);
    try { await onSearch({ plate: plateFilter, make, model, year: year ? Number(year) : undefined, color, body_type: bodyType, after_hours_only: afterHoursOnly }); }
    finally { setPending(false); }
  };
  return <section className="card-module history-panel">
    <div className="row-between"><div><div className="section-kicker"><History size={16} /> Cross-recording search</div><h2>Vehicle history</h2></div><span className="history-count">{sightings.length}</span></div>
    <form className="history-search" onSubmit={submit}>
      <input className="input-slot plate-input" value={plateFilter} onChange={e => setPlateFilter(e.target.value.toUpperCase())} placeholder="Full or partial plate" />
      <div className="form-row"><input className="input-slot" value={make} onChange={e => setMake(e.target.value)} placeholder="Make" /><input className="input-slot" value={model} onChange={e => setModel(e.target.value)} placeholder="Model" /></div>
      <div className="history-filter-row"><input className="input-slot" type="number" min="1900" max="2100" value={year} onChange={e => setYear(e.target.value)} placeholder="Year" /><input className="input-slot" value={color} onChange={e => setColor(e.target.value)} placeholder="Colour" /><input className="input-slot" value={bodyType} onChange={e => setBodyType(e.target.value)} placeholder="Body type" /></div>
      <label className="check-row"><input type="checkbox" checked={afterHoursOnly} onChange={e => setAfterHoursOnly(e.target.checked)} />After-hours sightings only</label>
      <button className="btn-industrial" disabled={pending}><Search size={14} />{pending ? 'Searching' : 'Search history'}</button>
    </form>
    {!sightings.length ? <p className="muted history-empty">No stored sightings match these filters. Complete recordings to build the ledger.</p> : <div className="history-list">{sightings.map(item => <article key={item.sighting_id} className="history-item">
      <div><strong>{item.observed_plate}</strong><span className={`match-dot ${item.match_kind}`} /></div>
      <p>{item.event_type.split('_').join(' ')}{item.camera_name ? ` · ${item.camera_name}` : ''}</p>
      {item.after_hours === 1 && <span className="after-hours-badge">After hours</span>}
      <small><MapPin size={12} />{item.captured_at ? new Date(item.captured_at).toLocaleString() : `Recording +${item.best_timestamp_seconds.toFixed(1)}s`}</small>
      {(item.vehicle_color || item.vehicle_body_type) && <small>AI observed: {[item.vehicle_color, item.vehicle_body_type].filter(Boolean).join(' · ')}{item.vehicle_detection_confidence ? ` · ${(item.vehicle_detection_confidence * 100).toFixed(0)}% vehicle confidence` : ''}</small>}
      {(item.requested_vehicle_year || item.requested_vehicle_make || item.requested_vehicle_model || item.requested_vehicle_color || item.requested_vehicle_body_type) && <small>Requested profile: {[item.requested_vehicle_year, item.requested_vehicle_color, item.requested_vehicle_make, item.requested_vehicle_model, item.requested_vehicle_body_type].filter(Boolean).join(' · ')}</small>}
    </article>)}</div>}
  </section>;
};
