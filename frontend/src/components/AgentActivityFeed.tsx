import React, { useEffect, useRef } from 'react';
import { AgentLogEntry } from '../types';
import { Terminal, Activity } from 'lucide-react';

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
    <div className="card-module" style={{ height: '100%', overflow: 'hidden', display: 'flex', flexDirection: 'column', padding: '24px' }}>
      <div className="screws" />
      
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '24px', zIndex: 10 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
          <div style={{ padding: '8px', background: 'var(--bg-chassis)', boxShadow: 'var(--shadow-recessed)', borderRadius: 'var(--radius-full)' }}>
            <Terminal size={20} color="var(--accent-orange)" />
          </div>
          <div>
            <h2 style={{ fontSize: '1.25rem', margin: 0 }}>ACTIVITY STREAM</h2>
            <div className="status-label">DIAGNOSTIC TERMINAL</div>
          </div>
        </div>
        <div className="status-label" style={{ display: 'flex', alignItems: 'center', gap: '6px', background: 'var(--bg-panel)', padding: '6px 12px', borderRadius: 'var(--radius-sm)', boxShadow: 'var(--shadow-sharp)' }}>
          <span className={`led ${currentStage ? 'yellow animate-pulse-led' : 'red'}`} style={{ width: '8px', height: '8px' }} />
          {currentStage ? currentStage.replace('_', ' ') : 'STANDBY'}
        </div>
      </div>

      <div className="screen-panel" style={{
        flex: 1,
        overflowY: 'auto',
        padding: '16px',
        display: 'flex',
        flexDirection: 'column',
        gap: '8px',
        fontFamily: 'var(--font-mono)',
        fontSize: '13px',
        zIndex: 10
      }}>
        {logs.length === 0 ? (
          <div style={{ color: 'var(--accent-orange)', textAlign: 'center', margin: 'auto', padding: '32px', opacity: 0.8 }}>
            <Activity size={36} style={{ margin: '0 auto 16px' }} />
            <p style={{ fontWeight: 700, fontSize: '16px' }}>TERMINAL IDLE</p>
            <p style={{ fontSize: '12px', marginTop: '8px' }}>AWAITING COMMAND INPUT...</p>
          </div>
        ) : (
          logs.map((log, idx) => (
            <div
              key={idx}
              style={{
                display: 'flex',
                gap: '12px',
                alignItems: 'flex-start',
                lineHeight: '1.5',
                color: log.level === 'match' ? '#22c55e' : (log.level === 'warning' ? '#eab308' : '#f8fafc'),
                opacity: 0.9
              }}
            >
              <span style={{ color: '#94a3b8', flexShrink: 0 }}>[{log.timestamp}]</span>
              <span style={{ fontWeight: 700, flexShrink: 0, minWidth: '95px' }}>
                [{log.step}]
              </span>
              <span style={{ flex: 1, wordBreak: 'break-word', whiteSpace: 'pre-wrap' }}>{log.message}</span>
            </div>
          ))
        )}
        <div ref={logEndRef} />
      </div>
    </div>
  );
};
