import React, { useEffect, useRef } from 'react';
import { Activity, ListChecks } from 'lucide-react';
import { AgentLogEntry } from '../types';

interface Props { logs: AgentLogEntry[]; currentStage: string; }

export const AgentActivityFeed: React.FC<Props> = ({ logs, currentStage }) => {
  const logRef = useRef<HTMLDivElement>(null);
  const followLog = useRef(true);
  useEffect(() => {
    const log = logRef.current;
    if (log && followLog.current) log.scrollTop = log.scrollHeight;
  }, [logs]);
  return <section className="surface activity-panel">
    <div className="activity-header">
      <div><span className="eyebrow">Processing details</span><h2><ListChecks size={18} /> Analysis activity</h2></div>
      <span className={`stage-pill ${currentStage ? 'active' : ''}`}><span />{currentStage ? currentStage.replace(/_/g, ' ') : 'Waiting to start'}</span>
    </div>
    <div className="activity-log" ref={logRef} onScroll={event => {
      const log = event.currentTarget;
      followLog.current = log.scrollHeight - log.scrollTop - log.clientHeight < 48;
    }}>
      {!logs.length ? <div className="activity-empty"><Activity size={22} /><span>Steps and model decisions will appear here during a search.</span></div> : logs.slice(-12).map((log, index) => <div key={index} className={`activity-entry ${log.level}`}><span className="activity-time">{log.timestamp}</span><strong>{log.step.replace(/_/g, ' ')}</strong><span>{log.message}</span></div>)}
    </div>
  </section>;
};
