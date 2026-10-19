import React, { useEffect, useRef } from 'react';
import { Activity, ListChecks } from 'lucide-react';
import { AgentLogEntry } from '../types';

interface Props { logs: AgentLogEntry[]; currentStage: string; }

export const AgentActivityFeed: React.FC<Props> = ({ logs, currentStage }) => {
  const logEndRef = useRef<HTMLDivElement>(null);
  useEffect(() => { logEndRef.current?.scrollIntoView({ behavior: 'smooth' }); }, [logs]);
  return <section className="surface activity-panel">
    <div className="activity-header">
      <div><span className="eyebrow">Processing details</span><h2><ListChecks size={18} /> Analysis activity</h2></div>
      <span className={`stage-pill ${currentStage ? 'active' : ''}`}><span />{currentStage ? currentStage.replace(/_/g, ' ') : 'Waiting to start'}</span>
    </div>
    <div className="activity-log">
      {!logs.length ? <div className="activity-empty"><Activity size={22} /><span>Steps and model decisions will appear here during a search.</span></div> : logs.slice(-12).map((log, index) => <div key={index} className={`activity-entry ${log.level}`}><span className="activity-time">{log.timestamp}</span><strong>{log.step.replace(/_/g, ' ')}</strong><span>{log.message}</span></div>)}
      <div ref={logEndRef} />
    </div>
  </section>;
};
