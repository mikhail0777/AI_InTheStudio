import React, { useState } from 'react';
import { TargetConfiguration } from '../types';
import { Search, Upload, FileVideo, Cpu, AlertCircle, Plus, Trash2 } from 'lucide-react';

interface TargetFormProps {
  onStartSession: (config: TargetConfiguration, videoFile: File, srtFile?: File) => void;
  isProcessing: boolean;
}

export const TargetForm: React.FC<TargetFormProps> = ({ onStartSession, isProcessing }) => {
  const [description, setDescription] = useState(
    'Locate a missing person wearing a red hoodie, dark pants, and carrying a blue backpack.'
  );
  const [upperColor, setUpperColor] = useState('red');
  const [upperType, setUpperType] = useState('hoodie');
  const [lowerColor, setLowerColor] = useState('black');
  const [lowerType, setLowerType] = useState('pants');
  const [backpack, setBackpack] = useState('blue backpack');
  const [hairColor, setHairColor] = useState('dark');
  const [minConfidence, setMinConfidence] = useState(0.65);

  const [reqAttrs, setReqAttrs] = useState<string[]>(['red upper clothing']);
  const [optAttrs, setOptAttrs] = useState<string[]>(['blue backpack', 'black pants']);
  const [negAttrs, setNegAttrs] = useState<string[]>(['bright green jacket', 'hat']);

  const [videoFile, setVideoFile] = useState<File | null>(null);
  const [srtFile, setSrtFile] = useState<File | null>(null);
  const [newAttr, setNewAttr] = useState('');

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!videoFile) {
      alert('Please select a drone MP4/MOV/MKV video recording.');
      return;
    }

    const config: TargetConfiguration = {
      free_text_description: description,
      upper_clothing_color: upperColor,
      upper_clothing_type: upperType,
      lower_clothing_color: lowerColor,
      lower_clothing_type: lowerType,
      backpack: backpack,
      hair_color: hairColor,
      required_attributes: reqAttrs,
      optional_attributes: optAttrs,
      negative_attributes: negAttrs,
      min_alert_confidence: minConfidence
    };

    onStartSession(config, videoFile, srtFile || undefined);
  };

  return (
    <div className="panel" style={{ height: '100%', overflowY: 'auto' }}>
      <div className="panel-header">
        <span className="panel-title">
          <Search size={18} /> Mission Target Configuration
        </span>
      </div>

      <form onSubmit={handleSubmit} style={{ display: 'flex', flexDirection: 'column', gap: '1rem' }}>
        {/* Drone Recording Upload */}
        <div className="form-group">
          <label className="form-label">📹 Drone Recording File (.MP4, .MOV, .MKV)</label>
          <div style={{
            border: '2px dashed var(--border-bright)',
            borderRadius: '8px',
            padding: '1rem',
            textAlign: 'center',
            background: 'var(--bg-dark)',
            cursor: 'pointer'
          }}>
            <input
              type="file"
              accept=".mp4,.mov,.mkv"
              onChange={(e) => setVideoFile(e.target.files?.[0] || null)}
              style={{ display: 'none' }}
              id="video-upload"
            />
            <label htmlFor="video-upload" style={{ cursor: 'pointer', display: 'flex', flexDirection: 'column', alignItems: 'center', gap: '0.4rem' }}>
              <FileVideo size={28} color="#38BDF8" />
              <span style={{ fontSize: '0.85rem', fontWeight: 600 }}>
                {videoFile ? videoFile.name : 'Select or Drop Drone Flight Video'}
              </span>
              <span style={{ fontSize: '0.75rem', color: 'var(--text-muted)' }}>
                {videoFile ? `${(videoFile.size / (1024*1024)).toFixed(1)} MB` : 'MP4, MOV, MKV up to 2 GB'}
              </span>
            </label>
          </div>
        </div>

        {/* Optional Telemetry */}
        <div className="form-group">
          <label className="form-label">📡 Optional Telemetry Log (.SRT)</label>
          <input
            type="file"
            accept=".srt,.txt,.csv"
            className="input"
            onChange={(e) => setSrtFile(e.target.files?.[0] || null)}
          />
          {srtFile && (
            <span style={{ fontSize: '0.75rem', color: '#10B981' }}>
              Attached: {srtFile.name}
            </span>
          )}
        </div>

        {/* Free Text Description */}
        <div className="form-group">
          <label className="form-label">Target Appearance Description</label>
          <textarea
            className="textarea"
            rows={3}
            value={description}
            onChange={(e) => setDescription(e.target.value)}
            placeholder="Describe missing person appearance, clothing, accessories..."
            required
          />
        </div>

        {/* Structured Clothing Specs */}
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '0.6rem' }}>
          <div className="form-group">
            <label className="form-label">Upper Color</label>
            <select className="select" value={upperColor} onChange={(e) => setUpperColor(e.target.value)}>
              <option value="red">Red</option>
              <option value="blue">Blue</option>
              <option value="green">Green</option>
              <option value="yellow">Yellow</option>
              <option value="dark">Dark/Black</option>
              <option value="white">White</option>
            </select>
          </div>
          <div className="form-group">
            <label className="form-label">Upper Type</label>
            <select className="select" value={upperType} onChange={(e) => setUpperType(e.target.value)}>
              <option value="hoodie">Hoodie / Jacket</option>
              <option value="t-shirt">T-Shirt / Top</option>
              <option value="coat">Heavy Coat</option>
            </select>
          </div>
        </div>

        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '0.6rem' }}>
          <div className="form-group">
            <label className="form-label">Lower Color</label>
            <select className="select" value={lowerColor} onChange={(e) => setLowerColor(e.target.value)}>
              <option value="black">Black / Dark</option>
              <option value="blue">Blue Jeans</option>
              <option value="khaki">Khaki / Beige</option>
              <option value="red">Red</option>
            </select>
          </div>
          <div className="form-group">
            <label className="form-label">Backpack</label>
            <input
              type="text"
              className="input"
              value={backpack}
              onChange={(e) => setBackpack(e.target.value)}
              placeholder="e.g. blue backpack"
            />
          </div>
        </div>

        {/* Confidence Threshold */}
        <div className="form-group">
          <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '0.85rem' }}>
            <label className="form-label">Minimum Alert Score</label>
            <span style={{ color: '#38BDF8', fontWeight: 700 }}>{(minConfidence * 100).toFixed(0)}%</span>
          </div>
          <input
            type="range"
            min="0.40"
            max="0.90"
            step="0.05"
            value={minConfidence}
            onChange={(e) => setMinConfidence(parseFloat(e.target.value))}
          />
        </div>

        {/* Start Analysis Button */}
        <button
          type="submit"
          className="btn btn-primary"
          disabled={isProcessing}
          style={{ width: '100%', padding: '0.8rem', marginTop: '0.5rem' }}
        >
          <Cpu size={18} /> {isProcessing ? 'Analyzing Drone Flight...' : 'Start Agentic Flight Analysis'}
        </button>
      </form>
    </div>
  );
};
