import React from 'react';
import { Eye, FileText, RefreshCw, Power } from 'lucide-react';
import { SessionStatus } from '../types';

interface HeaderProps {
  status: SessionStatus | null;
  onNewMission: () => void;
  onOpenReport: () => void;
}

export const Header: React.FC<HeaderProps> = ({ status, onNewMission, onOpenReport }) => {
  return (
    <header className="card-module" style={{ 
      margin: '24px 24px 0 24px', 
      padding: '20px 32px',
      display: 'flex',
      alignItems: 'center',
      justifyContent: 'space-between',
      borderBottomLeftRadius: 0,
      borderBottomRightRadius: 0
    }}>
      <div className="screws" />
      
      <div style={{ display: 'flex', alignItems: 'center', gap: '24px' }}>
        <div style={{
          width: '48px',
          height: '48px',
          borderRadius: 'var(--radius-full)',
          background: 'var(--bg-chassis)',
          boxShadow: 'var(--shadow-floating)',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          color: 'var(--accent-orange)'
        }}>
          <Eye size={24} />
        </div>
        <div>
          <h1 style={{ fontSize: '1.75rem', margin: 0, display: 'flex', gap: '12px', alignItems: 'center' }}>
            AI(EYE) IN THE SKY
            <div className="status-label" style={{ display: 'flex', alignItems: 'center', gap: '6px', background: 'var(--bg-recessed)', padding: '6px 12px', borderRadius: 'var(--radius-full)' }}>
              <span className="led green animate-pulse-led" />
              SYSTEM ONLINE
            </div>
          </h1>
          <p className="status-label" style={{ marginTop: '4px', color: 'var(--text-muted)' }}>
            POST-FLIGHT SAR INTELLIGENCE TERMINAL V1.0
          </p>
        </div>
      </div>
      
      <div style={{ display: 'flex', alignItems: 'center', gap: '24px' }}>
        {status && (
          <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'flex-end' }}>
            <span className="status-label">MISSION STATUS</span>
            <div style={{ display: 'flex', alignItems: 'center', gap: '8px', fontWeight: 700 }}>
              <span className={`led ${status.status === 'completed' ? 'green' : 'yellow animate-pulse-led'}`} />
              <span style={{ textTransform: 'uppercase' }}>
                {status.status.replace('_', ' ')} ({status.progress_percent.toFixed(0)}%)
              </span>
            </div>
          </div>
        )}
        
        <div style={{ display: 'flex', gap: '16px', borderLeft: '2px solid var(--shadow-dark)', paddingLeft: '24px', marginLeft: '8px' }}>
          {status?.status === 'completed' && (
            <button className="btn-industrial btn-primary" onClick={onOpenReport}>
              <FileText size={18} /> SAR REPORT
            </button>
          )}

          <button className="btn-industrial" onClick={onNewMission}>
            <Power size={18} color="var(--accent-orange)" /> RESET
          </button>
        </div>
      </div>
    </header>
  );
};
