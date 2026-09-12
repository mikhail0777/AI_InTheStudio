import React, { useState } from 'react';
import { TargetConfiguration } from '../types';
import { Search, FileVideo, Cpu, ShieldCheck } from 'lucide-react';

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

  const [reqAttrs] = useState<string[]>(['red upper clothing']);
  const [optAttrs] = useState<string[]>(['blue backpack', 'black pants']);
  const [negAttrs] = useState<string[]>(['bright green jacket', 'hat']);

  const [videoFile, setVideoFile] = useState<File | null>(null);
  const [srtFile, setSrtFile] = useState<File | null>(null);

  const applyPreset = (desc: string, upperC: string, lowerC: string, bp: string) => {
    setDescription(desc);
    setUpperColor(upperC);
    setLowerColor(lowerC);
    setBackpack(bp);
  };

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
    <div className="modern-panel" style={{ padding: '1rem', gap: '1rem' }}>
      <div className="modern-panel-header" style={{ margin: '-1rem -1rem 0 -1rem' }}>
        <span className="modern-panel-title">
          <Search size={16} color="#38BDF8" /> Target Profile & Video Ingestion
        </span>
      </div>

      <form onSubmit={handleSubmit} style={{ display: 'flex', flexDirection: 'column', gap: '0.9rem' }}>
        {/* Drone Recording Upload */}
        <div>
          <label style={{ display: 'block', fontSize: '0.78rem', fontWeight: 600, color: '#8B949E', marginBottom: '0.4rem' }}>
            Flight Video Recording (.MP4, .MOV, .MKV)
          </label>
          <div style={{
            border: videoFile ? '1px solid #10B981' : '1px dashed #222C3E',
            borderRadius: '6px',
            padding: '0.85rem',
            textAlign: 'center',
            background: videoFile ? 'rgba(16, 185, 129, 0.05)' : '#0A0D14',
            cursor: 'pointer'
          }}>
            <input
              type="file"
              accept=".mp4,.mov,.mkv"
              onChange={(e) => setVideoFile(e.target.files?.[0] || null)}
              style={{ display: 'none' }}
              id="video-upload"
            />
            <label htmlFor="video-upload" style={{ cursor: 'pointer', display: 'flex', flexDirection: 'column', alignItems: 'center', gap: '0.3rem' }}>
              <FileVideo size={22} color={videoFile ? '#10B981' : '#38BDF8'} />
              <span style={{ fontSize: '0.82rem', fontWeight: 600, color: videoFile ? '#10B981' : '#F0F6FC' }}>
                {videoFile ? videoFile.name : 'Select or Drop Drone Flight Video'}
              </span>
              <span style={{ fontSize: '0.72rem', color: '#6E7681' }}>
                {videoFile ? `${(videoFile.size / (1024 * 1024)).toFixed(1)} MB` : '1080p / 4K MP4, MOV up to 2GB'}
              </span>
            </label>
          </div>
        </div>

        {/* Optional Telemetry */}
        <div>
          <label style={{ display: 'block', fontSize: '0.78rem', fontWeight: 600, color: '#8B949E', marginBottom: '0.3rem' }}>
            Optional DJI Telemetry Log (.SRT)
          </label>
          <input
            type="file"
            accept=".srt,.txt,.csv"
            className="modern-input"
            onChange={(e) => setSrtFile(e.target.files?.[0] || null)}
          />
          {srtFile && (
            <span style={{ fontSize: '0.72rem', color: '#10B981', display: 'flex', alignItems: 'center', gap: '0.3rem', marginTop: '0.25rem' }}>
              <ShieldCheck size={12} /> Log attached: {srtFile.name}
            </span>
          )}
        </div>

        {/* Free Text Description & Quick Chips */}
        <div>
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '0.35rem' }}>
            <label style={{ fontSize: '0.78rem', fontWeight: 600, color: '#8B949E' }}>
              Target Description
            </label>
          </div>

          <textarea
            className="modern-input"
            rows={3}
            value={description}
            onChange={(e) => setDescription(e.target.value)}
            placeholder="Describe missing person clothing, accessories, color traits..."
            style={{ resize: 'none' }}
            required
          />

          {/* Quick Prompt Chips */}
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: '0.35rem', marginTop: '0.5rem' }}>
            <button type="button" className="quick-chip" onClick={() => applyPreset('Locate missing hiker wearing a red hoodie, dark pants, and blue backpack.', 'red', 'black', 'blue backpack')}>
              Red Hoodie & Blue Backpack
            </button>
            <button type="button" className="quick-chip" onClick={() => applyPreset('Locate missing skier wearing a yellow jacket and black snow pants.', 'yellow', 'black', 'none')}>
              Yellow Jacket & Dark Pants
            </button>
            <button type="button" className="quick-chip" onClick={() => applyPreset('Locate individual in blue coat carrying blue backpack.', 'blue', 'blue', 'blue backpack')}>
              Blue Coat & Backpack
            </button>
          </div>
        </div>

        {/* Structured Specs Grid */}
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '0.6rem' }}>
          <div>
            <label style={{ display: 'block', fontSize: '0.75rem', fontWeight: 600, color: '#8B949E', marginBottom: '0.25rem' }}>Upper Color</label>
            <select className="modern-input" value={upperColor} onChange={(e) => setUpperColor(e.target.value)}>
              <option value="red">Red</option>
              <option value="blue">Blue</option>
              <option value="green">Green</option>
              <option value="yellow">Yellow</option>
              <option value="dark">Dark / Black</option>
              <option value="white">White</option>
            </select>
          </div>

          <div>
            <label style={{ display: 'block', fontSize: '0.75rem', fontWeight: 600, color: '#8B949E', marginBottom: '0.25rem' }}>Lower Color</label>
            <select className="modern-input" value={lowerColor} onChange={(e) => setLowerColor(e.target.value)}>
              <option value="black">Black / Dark</option>
              <option value="blue">Blue Jeans</option>
              <option value="khaki">Khaki / Beige</option>
              <option value="red">Red</option>
            </select>
          </div>
        </div>

        <div>
          <label style={{ display: 'block', fontSize: '0.75rem', fontWeight: 600, color: '#8B949E', marginBottom: '0.25rem' }}>Backpack / Accessories</label>
          <input
            type="text"
            className="modern-input"
            value={backpack}
            onChange={(e) => setBackpack(e.target.value)}
            placeholder="e.g. blue backpack"
          />
        </div>

        {/* Confidence Threshold */}
        <div>
          <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '0.75rem', fontWeight: 600, color: '#8B949E', marginBottom: '0.25rem' }}>
            <span>Min Match Confidence</span>
            <span style={{ color: '#38BDF8', fontWeight: 700 }}>{(minConfidence * 100).toFixed(0)}%</span>
          </div>
          <input
            type="range"
            min="0.40"
            max="0.90"
            step="0.05"
            value={minConfidence}
            onChange={(e) => setMinConfidence(parseFloat(e.target.value))}
            style={{ width: '100%', accentColor: '#38BDF8', cursor: 'pointer' }}
          />
        </div>

        {/* Start Button */}
        <button
          type="submit"
          className="btn-modern-primary"
          disabled={isProcessing}
          style={{ width: '100%', padding: '0.75rem', marginTop: '0.3rem' }}
        >
          <Cpu size={16} /> {isProcessing ? 'Processing Flight Analysis...' : 'Run SAR Flight Analysis'}
        </button>
      </form>
    </div>
  );
};
