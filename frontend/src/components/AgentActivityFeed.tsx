import React, { useEffect, useRef } from 'react';
import { AgentLogEntry } from '../types';
import { Terminal, Cpu, CheckCircle, AlertCircle, Info, Activity } from 'lucide-react';

interface AgentActivityFeedProps {
  logs: AgentLogEntry[];
  currentStage: string;
}

export const AgentActivityFeed: React.FC<AgentActivityFeedProps> = ({ logs, currentStage }) => {
  const logEndRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    logEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [logs]);

  const getLogIcon = (level: string) => {
    switch (level) {
      case 'match': return <CheckCircle size={14} color="#10B981" />;
      case 'warning': return <AlertCircle size={14} color="#F59E0B" />;
      case 'action': return <Activity size={14} color="#38BDF8" />;
      default: return <Info size={14} color="#94A3B8" />;
    }
  };

  const getLogLevelColor = (level: string) => {
    switch (level) {
      case 'match': return '#10B981';
      case 'warning': return '#F59E0B';
      case 'action': return '#38BDF8';
      default: return '#94A3B8';
    }
  };

  return (
    <div className="panel agent-feed-panel" style={{ height: '100%', overflow: 'hidden', display: 'flex', flexDirection: 'column' }}>
      <div className="panel-header">
        <span className="panel-title">
          <Terminal size={18} /> Autonomous Agent Activity Stream
        </span>
        <span style={{ fontSize: '0.75rem', color: '#38BDF8', fontWeight: 600, textTransform: 'uppercase' }}>
          {currentStage.replace('_', ' ')}
        </span>
      </div>

      {/* Log Feed List */}
      <div style={{
        flex: 1,
        overflowY: 'auto',
        background: '#0B0F19',
        borderRadius: '6px',
        padding: '0.8rem',
        border: '1px solid #1E293B',
        display: 'flex',
        flexDirection: 'column',
        gap: '0.5rem',
        fontFamily: 'var(--font-mono)',
        fontSize: '0.8rem'
      }}>
        {logs.length === 0 ? (
          <div style={{ color: 'var(--text-dim)', textAlign: 'center', paddingTop: '2rem' }}>
            Agent idle. Waiting for video flight ingestion...
          </div>
        ) : (
          logs.map((log, idx) => (
            <div
              key={idx}
              style={{
                display: 'flex',
                gap: '0.5rem',
                alignItems: 'flex-start',
                lineHeight: 1.4,
                borderBottom: '1px dotted #1E293B',
                paddingBottom: '0.4rem'
              }}
            >
              <span style={{ color: '#64748B', flexShrink: 0 }}>[{log.timestamp}]</span>
              <span style={{ color: getLogLevelColor(log.level), fontWeight: 700, flexShrink: 0, minWidth: '90px' }}>
                [{log.step}]
              </span>
              <span style={{ color: '#F8FAFC', flex: 1 }}>{log.message}</span>
            </div>
          ))
        )}
        <div ref={logEndRef} />
      </div>
    </div>
  );
};
