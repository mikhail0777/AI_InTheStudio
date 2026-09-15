import React, { useState } from 'react';
import { TargetConfiguration } from '../types';
import { Search, FileVideo, Play } from 'lucide-react';

interface TargetFormProps {
  onStartSession: (config: TargetConfiguration, videoFile: File, srtFile?: File) => void;
  isProcessing: boolean;
}

const colors = ['black', 'white', 'gray', 'red', 'orange', 'yellow', 'green', 'blue', 'purple', 'pink', 'brown', 'beige'];

export const TargetForm: React.FC<TargetFormProps> = ({ onStartSession, isProcessing }) => {
  const [description, setDescription] = useState('');
  const [upperColor, setUpperColor] = useState('');
  const [lowerColor, setLowerColor] = useState('');
  const [backpack, setBackpack] = useState('');
  const [videoFile, setVideoFile] = useState<File | null>(null);
  const [srtFile, setSrtFile] = useState<File | null>(null);
  const [error, setError] = useState('');

  const handleSubmit = (event: React.FormEvent) => {
    event.preventDefault();
    setError('');
    if (!videoFile) { setError('Select an MP4, MOV, or MKV recording.'); return; }
    if (videoFile.size > 2 * 1024 ** 3) { setError('The recording must be smaller than 2 GB.'); return; }
    onStartSession({
      free_text_description: description.trim(),
      upper_clothing_color: upperColor || undefined,
      lower_clothing_color: lowerColor || undefined,
      backpack: backpack ? `${backpack} backpack` : undefined,
      required_attributes: [], optional_attributes: [], negative_attributes: [],
      min_alert_confidence: 0.65,
    }, videoFile, srtFile || undefined);
  };

  return <section className="card-module">
    <h2 className="icon-line" style={{ fontSize: '1.25rem', marginBottom: 20 }}><Search size={20} /> Search profile</h2>
    <form onSubmit={handleSubmit}>
      <fieldset disabled={isProcessing} className="target-fields">
        <div><label className="field-label" htmlFor="video-upload"><FileVideo size={15} /> Flight recording</label>
          <input id="video-upload" type="file" accept=".mp4,.mov,.mkv" className="input-slot" onChange={e => setVideoFile(e.target.files?.[0] || null)} required />
          <small className="muted">MP4, MOV, or MKV · Up to 2 GB</small>
        </div>
        <div><label className="field-label" htmlFor="telemetry-upload">Drone telemetry (optional)</label>
          <input id="telemetry-upload" type="file" accept=".srt" className="input-slot" onChange={e => setSrtFile(e.target.files?.[0] || null)} />
          <small className="muted">SRT from the same recording supplies drone position and altitude.</small>
        </div>
        <div><label className="field-label" htmlFor="target-description">Description for the reviewer</label>
          <textarea id="target-description" className="input-slot" rows={3} value={description} onChange={e => setDescription(e.target.value)} placeholder="For example: green long-sleeve top, black pants, black backpack." />
        </div>
        <div className="form-hint">Clothing colors and backpacks can be read from simple descriptions. Selections below override extracted colors. Hair, gender, identity, and clothing style are not inferred.</div>
        <div className="form-color-grid">
          <div><label className="field-label" htmlFor="upper-color">Upper clothing</label><select id="upper-color" className="input-slot" value={upperColor} onChange={e => setUpperColor(e.target.value)}><option value="">Not specified</option>{colors.map(c => <option key={c} value={c}>{c}</option>)}</select></div>
          <div><label className="field-label" htmlFor="lower-color">Lower clothing</label><select id="lower-color" className="input-slot" value={lowerColor} onChange={e => setLowerColor(e.target.value)}><option value="">Not specified</option>{colors.map(c => <option key={c} value={c}>{c}</option>)}</select></div>
        </div>
        <div><label className="field-label" htmlFor="backpack-color">Backpack color</label><select id="backpack-color" className="input-slot" value={backpack} onChange={e => setBackpack(e.target.value)}><option value="">Not specified</option>{colors.map(c => <option key={c} value={c}>{c}</option>)}</select>
          <small className="muted">An obscured or undetected backpack remains unknown.</small>
        </div>
        {error && <p role="alert" className="error-message">{error}</p>}
        <button type="submit" className="btn-industrial btn-primary" disabled={isProcessing}><Play size={18} />{isProcessing ? 'Analysis in progress' : 'Analyze recording'}</button>
      </fieldset>
    </form>
  </section>;
};
