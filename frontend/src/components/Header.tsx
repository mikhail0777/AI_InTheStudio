import React from 'react';
import { Eye, FileText, RefreshCw, Activity } from 'lucide-react';
import { SessionStatus } from '../types';

interface HeaderProps {
  status: SessionStatus | null;
  onNewMission: () => void;
  onOpenReport: () => void;
}

export const Header: React.FC<HeaderProps> = ({ status, onNewMission, onOpenReport }) => {
  return (
    <header style={{
      background: '#121722',
      borderBottom: '1px solid #222C3E',
      padding: '0.75rem 1.5rem',
      display: 'flex',
      alignItems: 'center',
      justifyContent: 'space-between',
      position: 'sticky',
      top: 0,
      zIndex: 100
    }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: '1rem' }}>
        <div style={{
          background: '#1A2130',
          border: '1px solid #2D3A52',
          width: '36px',
          height: '36px',
          borderRadius: '6px',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          color: '#38BDF8'
        }}>
          <Eye size={20} />
        </div>
        <div>
          <h1 style={{ fontSize: '1.15rem', fontWeight: 700, color: '#F0F6FC', letterSpacing: '-0.01em', display: 'flex', alignItems: 'center', gap: '0.4rem' }}>
            AI(EYE) <span style={{ color: '#38BDF8', fontWeight: 500 }}>in the sky</span>
          </h1>
          <p style={{ fontSize: '0.75rem', color: '#8B949E', fontWeight: 400 }}>
            Post-Flight Drone Search & Rescue Intelligence Platform
          </p>
        </div>
      </div>

      <div style={{ display: 'flex', alignItems: 'center', gap: '0.85rem' }}>
        {status && (
          <div className="status-tag status-tag-blue" style={{ padding: '0.35rem 0.75rem' }}>
            <Activity size={12} />
            <span>{status.status.replace('_', ' ')} ({status.progress_percent.toFixed(0)}%)</span>
          </div>
        )}

        {status?.status === 'completed' && (
          <button className="btn-modern-primary" onClick={onOpenReport}>
            <FileText size={15} /> View SAR Report
          </button>
        )}

        <button className="btn-modern-secondary" onClick={onNewMission}>
          <RefreshCw size={14} /> New Mission
        </button>
      </div>
    </header>
  );
};
