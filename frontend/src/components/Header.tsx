import React from 'react';
import { Shield, Radio, FileText, RefreshCw, AlertTriangle } from 'lucide-react';
import { SessionStatus } from '../types';

interface HeaderProps {
  status: SessionStatus | null;
  onNewMission: () => void;
  onOpenReport: () => void;
}

export const Header: React.FC<HeaderProps> = ({ status, onNewMission, onOpenReport }) => {
  return (
    <header style={{
      background: 'rgba(15, 23, 42, 0.95)',
      borderBottom: '1px solid #1E293B',
      padding: '0.8rem 1.5rem',
      display: 'flex',
      alignItems: 'center',
      justifyContent: 'space-between',
      position: 'sticky',
      top: 0,
      zIndex: 100
    }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: '1rem' }}>
        <div style={{
          background: 'linear-gradient(135deg, #0284C7, #38BDF8)',
          width: '38px',
          height: '38px',
          borderRadius: '8px',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          color: '#FFFFFF'
        }}>
          <Shield size={22} />
        </div>
        <div>
          <h1 style={{ fontSize: '1.25rem', fontWeight: 800, color: '#F8FAFC', letterSpacing: '-0.02em', display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
            AI(EYE) <span style={{ color: '#38BDF8', fontWeight: 500 }}>in the sky</span>
          </h1>
          <p style={{ fontSize: '0.75rem', color: '#94A3B8' }}>
            Agentic Post-Flight Drone Footage SAR Analysis Platform
          </p>
        </div>
      </div>

      <div style={{ display: 'flex', alignItems: 'center', gap: '1.2rem' }}>
        {status && (
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.6rem', background: '#111827', padding: '0.4rem 0.8rem', borderRadius: '6px', border: '1px solid #1E293B' }}>
            <div className={status.status === 'analyzing' ? 'pulse-dot' : ''} style={{
              width: '8px',
              height: '8px',
              borderRadius: '50%',
              backgroundColor: status.status === 'completed' ? '#10B981' : (status.status === 'analyzing' ? '#38BDF8' : '#94A3B8')
            }} />
            <span style={{ fontSize: '0.8rem', fontWeight: 600, color: '#F8FAFC', textTransform: 'uppercase' }}>
              {status.status} ({status.progress_percent.toFixed(0)}%)
            </span>
          </div>
        )}

        {status?.status === 'completed' && (
          <button className="btn btn-primary" onClick={onOpenReport}>
            <FileText size={16} /> View SAR Report
          </button>
        )}

        <button className="btn btn-secondary" onClick={onNewMission}>
          <RefreshCw size={16} /> New Mission
        </button>
      </div>
    </header>
  );
};
