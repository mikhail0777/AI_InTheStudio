import React, { useState } from 'react';
import { TargetConfiguration } from '../types';
import { Search, FileVideo, Play } from 'lucide-react';

interface TargetFormProps {
  onStartSession: (config: TargetConfiguration, videoFile: File, srtFile?: File) => void;
  isProcessing: boolean;
}

export const TargetForm: React.FC<TargetFormProps> = ({ onStartSession, isProcessing }) => {
  const [description, setDescription] = useState('');
  const [videoFile, setVideoFile] = useState<File | null>(null);
  const [srtFile, setSrtFile] = useState<File | null>(null);
  const [processingMode, setProcessingMode] = useState<'fast' | 'balanced' | 'thorough'>('balanced');
  const [error, setError] = useState('');

  const handleSubmit = (event: React.FormEvent) => {
    event.preventDefault();
    setError('');
    if (!videoFile) { setError('Select an MP4, MOV, or MKV recording.'); return; }
    if (videoFile.size > 2 * 1024 ** 3) { setError('The recording must be smaller than 2 GB.'); return; }
    onStartSession({
      free_text_description: description.trim(),
      processing_mode: processingMode,
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
        <div><label className="field-label" htmlFor="target-description">What would you like to find in this video?</label>
          <textarea id="target-description" className="input-slot search-description" rows={5} value={description} onChange={e => setDescription(e.target.value)} placeholder="A woman pushing a stroller, a yellow car, or a person placing a package near a door." required />
          <small className="muted">Describe a visible entity, attribute, action, or relationship in ordinary language.</small>
        </div>
        <div><label className="field-label" htmlFor="processing-mode">Processing mode</label>
          <select id="processing-mode" className="input-slot" value={processingMode} onChange={event => setProcessingMode(event.target.value as typeof processingMode)}>
            <option value="fast">Fast · smallest evidence shortlist</option>
            <option value="balanced">Balanced · recommended</option>
            <option value="thorough">Thorough · widest evidence search</option>
          </select>
          <small className="muted">Modes change index density, retrieval breadth, localization frames, batching, and result limits.</small>
        </div>
        {error && <p role="alert" className="error-message">{error}</p>}
        <button type="submit" className="btn-industrial btn-primary" disabled={isProcessing}><Play size={18} />{isProcessing ? 'Analysis in progress' : 'Analyze recording'}</button>
      </fieldset>
    </form>
  </section>;
};
