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
    <div className="card-module">
      <div className="screws" />
      <div className="vent-slots">
        <div className="vent-slot" />
        <div className="vent-slot" />
        <div className="vent-slot" />
      </div>

      <div style={{ marginBottom: '24px', display: 'flex', alignItems: 'center', gap: '12px' }}>
        <div style={{ padding: '8px', background: 'var(--bg-chassis)', boxShadow: 'var(--shadow-recessed)', borderRadius: 'var(--radius-full)' }}>
          <Search size={20} color="var(--accent-orange)" />
        </div>
        <div>
          <h2 style={{ fontSize: '1.25rem', margin: 0 }}>TARGET PROFILE</h2>
          <div className="status-label">DATA INGESTION MODULE</div>
        </div>
      </div>

      <form onSubmit={handleSubmit} style={{ display: 'flex', flexDirection: 'column', gap: '24px' }}>
        {/* Drone Recording Upload */}
        <div>
          <label className="status-label" style={{ display: 'block', marginBottom: '8px' }}>
            FLIGHT VIDEO RECORDING (.MP4, .MOV, .MKV)
          </label>
          <div className="input-slot" style={{
            padding: '32px',
            textAlign: 'center',
            cursor: 'pointer',
            display: 'flex',
            flexDirection: 'column',
            alignItems: 'center',
            gap: '12px'
          }}>
            <input
              type="file"
              accept=".mp4,.mov,.mkv"
              onChange={(e) => setVideoFile(e.target.files?.[0] || null)}
              style={{ display: 'none' }}
              id="video-upload"
            />
            <label htmlFor="video-upload" style={{ cursor: 'pointer', display: 'flex', flexDirection: 'column', alignItems: 'center', width: '100%' }}>
              <div style={{ 
                width: '64px', height: '64px', 
                borderRadius: 'var(--radius-full)', 
                background: 'var(--bg-chassis)',
                boxShadow: videoFile ? 'var(--shadow-pressed)' : 'var(--shadow-floating)',
                display: 'flex', alignItems: 'center', justifyContent: 'center',
                color: videoFile ? 'var(--accent-orange)' : 'var(--text-muted)',
                marginBottom: '16px',
                transition: 'all 300ms ease'
              }}>
                <FileVideo size={28} />
              </div>
              <span style={{ fontWeight: 700, fontSize: '16px', color: videoFile ? 'var(--text-primary)' : 'var(--text-muted)' }}>
                {videoFile ? videoFile.name : 'MOUNT MEDIA DRIVE'}
              </span>
              <span className="status-label" style={{ marginTop: '8px' }}>
                {videoFile ? `${(videoFile.size / (1024 * 1024)).toFixed(1)} MB` : 'MAX CAPACITY: 2GB'}
              </span>
            </label>
          </div>
        </div>

        {/* Optional Telemetry */}
        <div>
          <label className="status-label" style={{ display: 'block', marginBottom: '8px' }}>
            OPTIONAL DJI TELEMETRY LOG (.SRT)
          </label>
          <input
            type="file"
            accept=".srt,.txt,.csv"
            className="input-slot"
            onChange={(e) => setSrtFile(e.target.files?.[0] || null)}
          />
          {srtFile && (
            <span className="status-label" style={{ color: 'var(--accent-orange)', display: 'flex', alignItems: 'center', gap: '4px', marginTop: '8px' }}>
              <ShieldCheck size={14} /> LOG ATTACHED: {srtFile.name}
            </span>
          )}
        </div>

        <div style={{ height: '2px', background: 'var(--shadow-dark)', opacity: 0.2, margin: '8px 0' }} />

        {/* Free Text Description & Quick Chips */}
        <div>
          <label className="status-label" style={{ display: 'block', marginBottom: '8px' }}>
            TARGET DESCRIPTION (NATURAL LANGUAGE)
          </label>

          <textarea
            className="input-slot"
            rows={3}
            value={description}
            onChange={(e) => setDescription(e.target.value)}
            style={{ resize: 'none' }}
            required
          />

          {/* Quick Prompt Chips */}
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: '12px', marginTop: '16px' }}>
            <button type="button" className="btn-industrial" style={{ padding: '8px 12px', fontSize: '11px' }} onClick={() => applyPreset('Locate missing hiker wearing a red hoodie, dark pants, and blue backpack.', 'red', 'black', 'blue backpack')}>
              PRESET: RED/BLUE
            </button>
            <button type="button" className="btn-industrial" style={{ padding: '8px 12px', fontSize: '11px' }} onClick={() => applyPreset('Locate missing skier wearing a yellow jacket and black snow pants.', 'yellow', 'black', 'none')}>
              PRESET: YELLOW/BLACK
            </button>
            <button type="button" className="btn-industrial" style={{ padding: '8px 12px', fontSize: '11px' }} onClick={() => applyPreset('Locate individual in blue coat carrying blue backpack.', 'blue', 'blue', 'blue backpack')}>
              PRESET: BLUE/BLUE
            </button>
          </div>
        </div>

        {/* Structured Specs Grid */}
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '16px' }}>
          <div>
            <label className="status-label" style={{ display: 'block', marginBottom: '8px' }}>UPPER COLOR</label>
            <select className="input-slot" value={upperColor} onChange={(e) => setUpperColor(e.target.value)}>
              <option value="red">RED</option>
              <option value="blue">BLUE</option>
              <option value="green">GREEN</option>
              <option value="yellow">YELLOW</option>
              <option value="dark">DARK / BLACK</option>
              <option value="white">WHITE</option>
            </select>
          </div>

          <div>
            <label className="status-label" style={{ display: 'block', marginBottom: '8px' }}>LOWER COLOR</label>
            <select className="input-slot" value={lowerColor} onChange={(e) => setLowerColor(e.target.value)}>
              <option value="black">BLACK / DARK</option>
              <option value="blue">BLUE JEANS</option>
              <option value="khaki">KHAKI / BEIGE</option>
              <option value="red">RED</option>
            </select>
          </div>
        </div>

        <div>
          <label className="status-label" style={{ display: 'block', marginBottom: '8px' }}>BACKPACK / ACCESSORIES</label>
          <input
            type="text"
            className="input-slot"
            value={backpack}
            onChange={(e) => setBackpack(e.target.value)}
          />
        </div>

        {/* Confidence Threshold */}
        <div style={{ background: 'var(--bg-panel)', padding: '16px', borderRadius: 'var(--radius-md)', boxShadow: 'var(--shadow-sharp)' }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '12px' }}>
            <span className="status-label">MIN MATCH CONFIDENCE</span>
            <span style={{ color: 'var(--accent-orange)', fontWeight: 700, fontFamily: 'var(--font-mono)' }}>{(minConfidence * 100).toFixed(0)}%</span>
          </div>
          <input
            type="range"
            min="0.40"
            max="0.90"
            step="0.05"
            value={minConfidence}
            onChange={(e) => setMinConfidence(parseFloat(e.target.value))}
            style={{ 
              width: '100%', 
              accentColor: 'var(--accent-orange)',
              height: '8px',
              borderRadius: 'var(--radius-full)',
              background: 'var(--bg-recessed)',
              appearance: 'none',
              boxShadow: 'var(--shadow-recessed)'
            }}
          />
        </div>

        {/* Start Button */}
        <button
          type="submit"
          className="btn-industrial btn-primary"
          disabled={isProcessing}
          style={{ width: '100%', padding: '16px', marginTop: '8px' }}
        >
          {isProcessing ? (
            <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
              <span className="led yellow animate-pulse-led" /> PROCESSING FLIGHT DATA...
            </div>
          ) : (
            <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
              <Cpu size={20} /> RUN SAR FLIGHT ANALYSIS
            </div>
          )}
        </button>
      </form>
    </div>
  );
};
