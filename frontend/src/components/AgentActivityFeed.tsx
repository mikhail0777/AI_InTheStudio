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
    <div className="card-module activity-panel">
      <div className="screws" />
      
      <div className="activity-header">
        <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
          <div style={{ padding: '8px', background: 'var(--bg-chassis)', boxShadow: 'var(--shadow-recessed)', borderRadius: 'var(--radius-full)' }}>
            <Terminal size={20} color="var(--accent-orange)" />
          </div>
          <div>
            <h2 style={{ fontSize: '1.15rem', margin: 0 }}>Analysis activity</h2>
          </div>
        </div>
        <div className="status-label" style={{ display: 'flex', alignItems: 'center', gap: '6px', background: 'var(--bg-panel)', padding: '6px 12px', borderRadius: 'var(--radius-sm)', boxShadow: 'var(--shadow-sharp)' }}>
          <span className={`led ${currentStage ? 'yellow animate-pulse-led' : 'red'}`} style={{ width: '8px', height: '8px' }} />
          {currentStage ? currentStage.replace('_', ' ') : 'STANDBY'}
        </div>
      </div>

      <div className="activity-log">
        {logs.length === 0 ? (
          <div style={{ color: 'var(--accent-orange)', textAlign: 'center', margin: 'auto', padding: '32px', opacity: 0.8 }}>
            <Activity size={36} style={{ margin: '0 auto 16px' }} />
            <p style={{ fontWeight: 700, fontSize: '16px' }}>TERMINAL IDLE</p>
            <p style={{ fontSize: '12px', marginTop: '8px' }}>AWAITING COMMAND INPUT...</p>
          </div>
        ) : (
          logs.slice(-12).map((log, idx) => (
            <div key={idx} className={`activity-entry ${log.level}`}>
              <span className="activity-time">{log.timestamp}</span>
              <strong>{log.step.replace(/_/g, ' ')}</strong>
              <span>{log.message}</span>
            </div>
          ))
        )}
        <div ref={logEndRef} />
      </div>
    </div>
  );
};
