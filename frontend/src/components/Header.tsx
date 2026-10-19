import React from 'react';
import { FileText, Pause, Play, Plus, ScanLine, Square, Trash2 } from 'lucide-react';
import { SessionStatus } from '../types';

interface HeaderProps {
  status: SessionStatus | null;
  onNewMission: () => void;
  onOpenReport: () => void;
  isProcessing: boolean;
  isUploading: boolean;
  controlPending: boolean;
  onControl: (action: 'pause' | 'resume' | 'cancel') => void;
  onDeleteCase: () => void;
}

export const Header: React.FC<HeaderProps> = ({ status, onNewMission, onOpenReport, isProcessing, isUploading, controlPending, onControl, onDeleteCase }) => <header className="app-header">
  <div className="brand-lockup">
    <div className="brand-mark"><ScanLine size={23} /></div>
    <div><h1>LotTrace</h1><p>Vehicle evidence workspace</p></div>
  </div>
  <div className="header-actions">
    {status && <div className="session-progress" role="status">
      <div className="status-row"><span className={`status-dot status-${status.status}`} /><strong>{isUploading ? 'Uploading' : status.status}</strong><span>{isUploading ? 'Preparing recording' : `${status.progress_percent.toFixed(0)}% · ${status.current_stage.replace(/_/g, ' ')}`}</span></div>
      <div className="progress-track"><span style={{ width: `${isUploading ? 8 : status.progress_percent}%` }} /></div>
    </div>}
    {status && !isUploading && ['queued', 'analyzing', 'paused'].includes(status.status) && <>
      <button className="button button-secondary" disabled={controlPending || status.status === 'queued'} onClick={() => onControl(status.status === 'paused' ? 'resume' : 'pause')}>{status.status === 'paused' ? <Play size={16} /> : <Pause size={16} />}{status.status === 'paused' ? 'Resume' : 'Pause'}</button>
      <button className="button button-secondary" disabled={controlPending} onClick={() => onControl('cancel')}><Square size={15} />Cancel</button>
    </>}
    {status?.status === 'completed' && <button className="button button-secondary" onClick={onOpenReport}><FileText size={16} />Report</button>}
    {status && ['completed', 'error', 'cancelled'].includes(status.status) && <button className="button button-quiet danger-button" onClick={onDeleteCase}><Trash2 size={16} />Delete</button>}
    <button className="button button-primary" disabled={isProcessing} onClick={onNewMission}><Plus size={17} />New investigation</button>
  </div>
</header>;
