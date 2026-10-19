import React, { useState } from 'react';
import { Camera, CarFront, Check, ChevronDown, FileVideo, Search, UploadCloud } from 'lucide-react';
import { TargetConfiguration } from '../types';

interface Props { onStartSession: (config: TargetConfiguration, videoFile: File) => void; isProcessing: boolean; }
const normalizePlate = (value: string) => value.toUpperCase().replace(/[^A-Z0-9]/g, '');
const colors = ['Black', 'White', 'Silver', 'Grey', 'Red', 'Blue', 'Green', 'Yellow', 'Orange', 'Brown', 'Beige / Tan', 'Gold', 'Bronze', 'Purple', 'Pink', 'Burgundy / Maroon', 'Teal / Turquoise', 'Two-tone', 'Other / Unknown'];
const makes = ['Acura', 'Audi', 'BMW', 'Buick', 'Cadillac', 'Chevrolet', 'Chrysler', 'Dodge', 'Ford', 'Genesis', 'GMC', 'Honda', 'Hyundai', 'Infiniti', 'Jeep', 'Kia', 'Land Rover', 'Lexus', 'Lincoln', 'Mazda', 'Mercedes-Benz', 'Mitsubishi', 'Nissan', 'Porsche', 'Ram', 'Subaru', 'Tesla', 'Toyota', 'Volkswagen', 'Volvo'];

export const TargetForm: React.FC<Props> = ({ onStartSession, isProcessing }) => {
  const [videoFile, setVideoFile] = useState<File | null>(null);
  const [plate, setPlate] = useState('');
  const [plateMode, setPlateMode] = useState<'exact' | 'partial'>('exact');
  const [color, setColor] = useState(''); const [bodyType, setBodyType] = useState('');
  const [make, setMake] = useState(''); const [model, setModel] = useState(''); const [year, setYear] = useState('');
  const [cameraName, setCameraName] = useState('');
  const [cameraRole, setCameraRole] = useState<NonNullable<TargetConfiguration['camera_role']>>('unknown');
  const [recordedStart, setRecordedStart] = useState('');
  const [businessOpen, setBusinessOpen] = useState('08:00'); const [businessClose, setBusinessClose] = useState('20:00');
  const [fromSeconds, setFromSeconds] = useState(''); const [toSeconds, setToSeconds] = useState('');
  const [processingMode, setProcessingMode] = useState<'fast' | 'balanced' | 'thorough'>('balanced');
  const [error, setError] = useState('');

  const handleSubmit = (event: React.FormEvent) => {
    event.preventDefault(); setError('');
    const normalizedPlate = normalizePlate(plate);
    if (!videoFile) return setError('Select an MP4, MOV, or MKV security recording.');
    if (videoFile.size > 4 * 1024 ** 3) return setError('The recording must be smaller than 4 GB.');
    if (normalizedPlate && (normalizedPlate.length < 3 || normalizedPlate.length > 10)) return setError('Enter 3–10 letters or numbers for a full or partial licence plate.');
    if (!normalizedPlate && !color && !bodyType && !make && !model && !year) return setError('Enter a plate or at least one vehicle detail.');
    if (fromSeconds && toSeconds && Number(toSeconds) <= Number(fromSeconds)) return setError('The end of the search window must be after the start.');
    const description = [color, year, make, model, bodyType || 'vehicle', normalizedPlate ? `with licence plate ${normalizedPlate}` : ''].filter(Boolean).join(' ');
    onStartSession({
      free_text_description: description, processing_mode: processingMode,
      required_attributes: [], optional_attributes: [], negative_attributes: [], min_alert_confidence: 0.65,
      plate_number: normalizedPlate || undefined, plate_match_mode: plateMode, vehicle_make: make || undefined,
      vehicle_model: model || undefined, vehicle_year: year ? Number(year) : undefined,
      vehicle_color: color || undefined, vehicle_body_type: bodyType || undefined,
      camera_name: cameraName || undefined, camera_role: cameraRole,
      recorded_start_at: recordedStart || undefined, business_open_time: businessOpen,
      business_close_time: businessClose, search_start_seconds: fromSeconds ? Number(fromSeconds) : undefined,
      search_end_seconds: toSeconds ? Number(toSeconds) : undefined,
    }, videoFile);
  };

  return <section className="surface investigation-form">
    <div className="form-heading"><div className="form-icon"><CarFront size={20} /></div><div><span className="eyebrow">Case setup</span><h2>Find a vehicle</h2></div></div>
    <p className="muted form-intro">Add the footage, then enter only what you know. Search by plate, vehicle details, or both.</p>
    <form onSubmit={handleSubmit}><fieldset disabled={isProcessing} className="target-fields">
      <div className="form-section"><div className="form-section-title"><span>1</span><h3><FileVideo size={15} /> Recording</h3></div>
        <label className={`upload-dropzone ${videoFile ? 'has-file' : ''}`} htmlFor="video-upload"><input id="video-upload" type="file" accept=".mp4,.mov,.mkv" onChange={e => setVideoFile(e.target.files?.[0] || null)} required /><div className="upload-icon">{videoFile ? <Check size={21} /> : <UploadCloud size={21} />}</div><div><strong>{videoFile ? videoFile.name : 'Choose a security recording'}</strong><span>{videoFile ? `${(videoFile.size / 1024 / 1024).toFixed(1)} MB · ready to scan` : 'MP4, MOV or MKV · up to 4 GB'}</span></div></label>
        <details className="advanced-panel"><summary>Recording details <ChevronDown size={15} /></summary><div className="advanced-fields">
          <div className="form-row"><div><label className="field-label">Recording begins</label><input className="input-slot" type="datetime-local" value={recordedStart} onChange={e => setRecordedStart(e.target.value)} /></div><div><label className="field-label">Camera name</label><input className="input-slot" value={cameraName} onChange={e => setCameraName(e.target.value)} placeholder="North gate" /></div></div>
          <label className="field-label">Camera role</label><select className="input-slot" value={cameraRole} onChange={e => setCameraRole(e.target.value as typeof cameraRole)}><option value="unknown">Unspecified / general view</option><option value="lot_entry">Lot entrance</option><option value="lot_exit">Lot exit</option><option value="service_entry">Service entrance</option><option value="service_exit">Service exit</option><option value="lot_area">Inventory / lot area</option></select>
          <div className="form-row"><div><label className="field-label">Business opens</label><input className="input-slot" type="time" value={businessOpen} onChange={e => setBusinessOpen(e.target.value)} /></div><div><label className="field-label">Business closes</label><input className="input-slot" type="time" value={businessClose} onChange={e => setBusinessClose(e.target.value)} /></div></div>
        </div></details>
      </div>
      <div className="form-section"><div className="form-section-title"><span>2</span><h3><Search size={15} /> Known plate</h3><em>Optional</em></div>
        <label className="field-label" htmlFor="plate">Licence plate or known fragment</label><input id="plate" className="input-slot plate-input" value={plate} maxLength={12} onChange={e => setPlate(e.target.value.toUpperCase())} placeholder="e.g. ABC1234" />
        <div className="segmented-control"><button type="button" aria-pressed={plateMode === 'exact'} onClick={() => setPlateMode('exact')}>Full plate</button><button type="button" aria-pressed={plateMode === 'partial'} onClick={() => setPlateMode('partial')}>Partial plate</button></div>
        <div className="form-row"><div><label className="field-label">From second</label><input className="input-slot" type="number" min="0" step="0.1" value={fromSeconds} onChange={e => setFromSeconds(e.target.value)} placeholder="Start" /></div><div><label className="field-label">To second</label><input className="input-slot" type="number" min="0" step="0.1" value={toSeconds} onChange={e => setToSeconds(e.target.value)} placeholder="End" /></div></div>
      </div>
      <details className="form-section vehicle-details"><summary><Camera size={15} /><strong>Search by vehicle details</strong><span>Colour, make, model</span><ChevronDown size={15} /></summary><div className="advanced-fields">
        <div className="form-row"><div><label className="field-label">Make</label><input list="vehicle-makes" className="input-slot" value={make} onChange={e => setMake(e.target.value)} placeholder="Any make" /><datalist id="vehicle-makes">{makes.map(item => <option key={item} value={item} />)}</datalist></div><div><label className="field-label">Model</label><input className="input-slot" value={model} onChange={e => setModel(e.target.value)} placeholder="Model" /></div></div>
        <div className="form-row"><div><label className="field-label">Year</label><input className="input-slot" type="number" min="1900" max="2100" value={year} onChange={e => setYear(e.target.value)} placeholder="Approx." /></div><div><label className="field-label">Colour</label><input list="vehicle-colors" className="input-slot" value={color} onChange={e => setColor(e.target.value)} placeholder="Any colour" /><datalist id="vehicle-colors">{colors.map(item => <option key={item} value={item} />)}</datalist></div></div>
        <label className="field-label">Body type</label><select className="input-slot" value={bodyType} onChange={e => setBodyType(e.target.value)}><option value="">Any vehicle</option><option>Sedan</option><option>SUV / Crossover</option><option>Pickup truck</option><option>Coupe</option><option>Hatchback</option><option>Wagon</option><option>Minivan</option><option>Cargo van</option><option>Convertible</option><option>Motorcycle</option><option>Commercial truck</option><option>Other / Unknown</option></select>
      </div></details>
      <div><label className="field-label">Scan depth</label><div className="scan-options">{(['fast', 'balanced', 'thorough'] as const).map(mode => <button key={mode} type="button" aria-pressed={processingMode === mode} onClick={() => setProcessingMode(mode)}><strong>{mode}</strong><span>{mode === 'fast' ? 'Quick pass' : mode === 'balanced' ? 'Recommended' : 'Max coverage'}</span></button>)}</div></div>
      <p className="form-hint">AI observations are leads, not conclusions. Confirm every result against the original footage.</p>
      {error && <p role="alert" className="error-message">{error}</p>}
      <button type="submit" className="button button-primary start-search" disabled={isProcessing}><Search size={18} />{isProcessing ? 'Investigation in progress' : 'Start vehicle search'}</button>
    </fieldset></form>
  </section>;
};
