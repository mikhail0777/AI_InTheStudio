import React from 'react';
import { Eye, FileText, Plus, Pause, Play, Square } from 'lucide-react';
import { SessionStatus } from '../types';

interface HeaderProps {
  status: SessionStatus | null;
  onNewMission: () => void;
  onOpenReport: () => void;
  isProcessing: boolean;
  isUploading: boolean;
  controlPending: boolean;
  onControl: (action: 'pause' | 'resume' | 'cancel') => void;
}

export const Header: React.FC<HeaderProps> = ({ status, onNewMission, onOpenReport, isProcessing, isUploading, controlPending, onControl }) => <header className="app-header">
  <div className="icon-line"><Eye size={30} color="var(--accent-orange)" /><div><h1>AI in the Sky</h1><p className="muted">Flight footage · Evidence review</p></div></div>
  <div className="header-actions">
    {status && <div className="session-progress" role="status"><strong>{isUploading ? 'Uploading' : status.status}</strong><span>{isUploading ? 'Preparing recording' : `${status.progress_percent.toFixed(0)}% · ${status.current_stage.replace(/_/g, ' ')}`}</span>{status.processing_mode && <span>{status.processing_mode} mode</span>}</div>}
    {status && !isUploading && ['queued', 'analyzing', 'paused'].includes(status.status) && <>
      <button className="btn-industrial" disabled={controlPending || status.status === 'queued'} onClick={() => onControl(status.status === 'paused' ? 'resume' : 'pause')}>{status.status === 'paused' ? <Play size={16} /> : <Pause size={16} />}{status.status === 'paused' ? 'Resume' : 'Pause'}</button>
      <button className="btn-industrial" disabled={controlPending} onClick={() => onControl('cancel')}><Square size={16} />Cancel</button>
    </>}
    {status?.status === 'completed' && <button className="btn-industrial" onClick={onOpenReport}><FileText size={17} />Report</button>}
    <button className="btn-industrial" disabled={isProcessing} onClick={onNewMission}><Plus size={17} />New analysis</button>
  </div>
</header>;
