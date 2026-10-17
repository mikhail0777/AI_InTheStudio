import React from 'react';
import { CarFront, FileText, Plus, Pause, Play, Square, Trash2 } from 'lucide-react';
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
  <div className="brand-lockup"><div className="brand-mark"><CarFront size={25} /></div><div><h1>LotTrace</h1><p>Dealership video investigation</p></div></div>
  <div className="header-actions">
    {status && <div className="session-progress" role="status"><strong>{isUploading ? 'Uploading' : status.status}</strong><span>{isUploading ? 'Preparing recording' : `${status.progress_percent.toFixed(0)}% · ${status.current_stage.replace(/_/g, ' ')}`}</span>{status.processing_mode && <span>{status.processing_mode} scan</span>}</div>}
    {status && !isUploading && ['queued', 'analyzing', 'paused'].includes(status.status) && <>
      <button className="btn-industrial" disabled={controlPending || status.status === 'queued'} onClick={() => onControl(status.status === 'paused' ? 'resume' : 'pause')}>{status.status === 'paused' ? <Play size={16} /> : <Pause size={16} />}{status.status === 'paused' ? 'Resume' : 'Pause'}</button>
      <button className="btn-industrial" disabled={controlPending} onClick={() => onControl('cancel')}><Square size={16} />Cancel</button>
    </>}
    {status?.status === 'completed' && <button className="btn-industrial" onClick={onOpenReport}><FileText size={17} />Evidence report</button>}
    {status && ['completed', 'error', 'cancelled'].includes(status.status) && <button className="btn-industrial danger-button" onClick={onDeleteCase}><Trash2 size={16} />Delete case</button>}
    <button className="btn-industrial" disabled={isProcessing} onClick={onNewMission}><Plus size={17} />New investigation</button>
  </div>
</header>;
