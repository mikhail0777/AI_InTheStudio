import React, {useState} from 'react';
import {Camera, Check, FileVideo, Play, UploadCloud} from 'lucide-react';
import {TargetConfiguration} from '../types';

interface Props {
  onStartSession: (config: TargetConfiguration, videoFile: File) => void;
  isProcessing: boolean;
  onPreviewFile?: (file: File | null) => void;
}

export const TargetForm: React.FC<Props> = ({onStartSession, isProcessing, onPreviewFile}) => {
  const [videoFile, setVideoFile] = useState<File | null>(null);
  const [cameraName, setCameraName] = useState('');
  const [cameraRole, setCameraRole] = useState<NonNullable<TargetConfiguration['camera_role']>>('unknown');
  const [recordedStart, setRecordedStart] = useState('');
  const [error, setError] = useState('');

  const submit = (event: React.FormEvent) => {
    event.preventDefault();
    setError('');
    if (!videoFile) return setError('Select an MP4, MOV, or MKV security recording.');
    if (videoFile.size > 4 * 1024 ** 3) return setError('The recording must be smaller than 4 GB.');
    onStartSession({
      free_text_description: 'Detect and record every supported vehicle in this recording.',
      processing_mode: 'balanced',
      inventory_scan: true,
      required_attributes: [],
      optional_attributes: [],
      negative_attributes: [],
      min_alert_confidence: 0.65,
      camera_name: cameraName.trim() || undefined,
      camera_role: cameraRole,
      recorded_start_at: recordedStart || undefined,
    }, videoFile);
  };

  return <section className="surface investigation-form">
    <div className="form-heading"><div className="form-icon"><Camera size={20}/></div><div><span className="eyebrow">Recording setup</span><h2>Analyse all vehicles</h2></div></div>
    <p className="muted form-intro">LotTrace will find every supported vehicle, group repeat frames, read visible plates, and attach colour and vehicle candidates.</p>
    <form onSubmit={submit}><fieldset disabled={isProcessing} className="target-fields">
      <div className="form-section">
        <div className="form-section-title"><span>1</span><h3><FileVideo size={15}/> Recording</h3></div>
        <label className={`upload-dropzone ${videoFile ? 'has-file' : ''}`} htmlFor="video-upload">
          <input id="video-upload" type="file" accept=".mp4,.mov,.mkv" onChange={event => {
            const file = event.target.files?.[0] || null;
            setVideoFile(file);
            onPreviewFile?.(file);
          }} required/>
          <div className="upload-icon">{videoFile ? <Check size={21}/> : <UploadCloud size={21}/>}</div>
          <div><strong>{videoFile ? videoFile.name : 'Choose a security recording'}</strong><span>{videoFile ? `${(videoFile.size / 1024 / 1024).toFixed(1)} MB · ready to analyse` : 'MP4, MOV or MKV · up to 4 GB'}</span></div>
        </label>
      </div>
      <div className="form-section">
        <div className="form-section-title"><span>2</span><h3><Camera size={15}/> Camera context</h3></div>
        <label className="field-label" htmlFor="camera-name">Camera name</label>
        <input id="camera-name" className="input-slot" value={cameraName} onChange={event => setCameraName(event.target.value)} placeholder="Main gate"/>
        <label className="field-label" htmlFor="camera-role">Movement</label>
        <select id="camera-role" className="input-slot" value={cameraRole} onChange={event => setCameraRole(event.target.value as typeof cameraRole)}>
          <option value="unknown">General view / direction unknown</option>
          <option value="lot_entry">Entering the lot</option>
          <option value="lot_exit">Leaving the lot</option>
          <option value="service_entry">Entering service</option>
          <option value="service_exit">Leaving service</option>
          <option value="lot_area">Observed on the lot</option>
        </select>
        <label className="field-label" htmlFor="recorded-start">Recording start time</label>
        <input id="recorded-start" className="input-slot" type="datetime-local" value={recordedStart} onChange={event => setRecordedStart(event.target.value)}/>
        <p className="form-hint">When no clock time is provided, sightings use the timestamp inside the video.</p>
      </div>
      <div className="analysis-summary">
        <strong>Automatic processing</strong>
        <span>Frame selection adapts to each vehicle track. Clear, independent plate views receive more weight than repeated blurry frames.</span>
      </div>
      {error && <p role="alert" className="error-message">{error}</p>}
      <button type="submit" className="button button-primary start-search" disabled={isProcessing}><Play size={18}/>{isProcessing ? 'Analysis in progress' : 'Analyse recording'}</button>
    </fieldset></form>
  </section>;
};
