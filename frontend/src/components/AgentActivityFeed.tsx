import React, { useEffect, useRef } from 'react';
import { AgentLogEntry } from '../types';
import { Terminal, Activity, CheckCircle, AlertTriangle, Info } from 'lucide-react';

interface AgentActivityFeedProps {
  logs: AgentLogEntry[];
  currentStage: string;
}

export const AgentActivityFeed: React.FC<AgentActivityFeedProps> = ({ logs, currentStage }) => {
  const logEndRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    logEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [logs]);

  return (
    <div className="modern-panel" style={{ height: '100%', overflow: 'hidden' }}>
      <div className="modern-panel-header">
        <span className="modern-panel-title">
          <Terminal size={16} color="#38BDF8" /> Agent Activity & Reasoning Stream
        </span>
        <span className="status-tag status-tag-blue" style={{ fontSize: '0.68rem' }}>
          {currentStage ? currentStage.replace('_', ' ') : 'Standby'}
        </span>
      </div>

      <div style={{
        flex: 1,
        overflowY: 'auto',
        background: '#0A0D14',
        padding: '0.75rem',
        display: 'flex',
        flexDirection: 'column',
        gap: '0.4rem',
        fontFamily: 'var(--font-mono)',
        fontSize: '0.78rem'
      }}>
        {logs.length === 0 ? (
          <div style={{ color: 'var(--text-muted)', textAlign: 'center', margin: 'auto', padding: '2rem 1rem' }}>
            <Activity size={28} color="#222C3E" style={{ marginBottom: '0.5rem' }} />
            <p style={{ fontSize: '0.82rem', fontWeight: 500, color: 'var(--text-secondary)' }}>Agent Stream Idle</p>
            <p style={{ fontSize: '0.72rem', color: 'var(--text-muted)', marginTop: '0.2rem' }}>Target profile & drone video required to start analysis.</p>
          </div>
        ) : (
          logs.map((log, idx) => (
            <div
              key={idx}
              style={{
                display: 'flex',
                gap: '0.6rem',
                alignItems: 'flex-start',
                lineHeight: '1.4',
                padding: '0.35rem 0.5rem',
                borderRadius: '4px',
                background: log.level === 'match' ? 'rgba(16, 185, 129, 0.08)' : (log.level === 'warning' ? 'rgba(245, 158, 11, 0.08)' : 'rgba(255, 255, 255, 0.02)'),
                borderLeft: log.level === 'match' ? '2.5px solid #10B981' : (log.level === 'warning' ? '2.5px solid #F59E0B' : '2.5px solid #222C3E')
              }}
            >
              <span style={{ color: '#6E7681', flexShrink: 0 }}>[{log.timestamp}]</span>
              <span style={{ color: log.level === 'match' ? '#10B981' : (log.level === 'warning' ? '#F59E0B' : '#38BDF8'), fontWeight: 600, flexShrink: 0, minWidth: '85px' }}>
                [{log.step}]
              </span>
              <span style={{ color: '#F0F6FC', flex: 1 }}>{log.message}</span>
            </div>
          ))
        )}
        <div ref={logEndRef} />
      </div>
    </div>
  );
};
