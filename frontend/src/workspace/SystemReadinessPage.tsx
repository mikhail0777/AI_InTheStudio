import {useEffect,useState} from 'react';
import {RefreshCw,Server,ShieldAlert} from 'lucide-react';
import {getSystemReadiness,type SystemReadiness} from '../api';
import {Badge,PageHeading} from './ui';

const title=(value:string)=>value.split('_').map(part=>part[0].toUpperCase()+part.slice(1)).join(' ');

export function SystemReadinessPage(){
 const [data,setData]=useState<SystemReadiness|null>(null),[error,setError]=useState(''),[loading,setLoading]=useState(true),[reload,setReload]=useState(0);
 useEffect(()=>{let active=true;setLoading(true);setError('');getSystemReadiness().then(value=>{if(active)setData(value);}).catch(failure=>{if(active)setError(failure instanceof Error?failure.message:'Could not load readiness.');}).finally(()=>{if(active)setLoading(false);});return()=>{active=false;};},[reload]);
 return <><PageHeading title="System readiness" description="Runtime health, implemented capabilities, and the remaining production blockers."><button className="button" disabled={loading} onClick={()=>setReload(value=>value+1)}><RefreshCw size={17}/> Refresh</button></PageHeading>
 {error?<div className="notice notice-warning" role="alert"><strong>Readiness check unavailable</strong><p>{error}</p></div>:loading?<div className="empty" role="status">Checking runtime health…</div>:data&&<>
  <div className="notice notice-warning"><strong><ShieldAlert size={18}/> Not production certified</strong><p>{data.accuracy_note}</p></div>
  <section className="panel"><div className="section-heading"><div><h2>Runtime checks</h2><p>Whether this installation can safely accept local work right now.</p></div><Badge tone={data.runtime_status==='healthy'?'green':'amber'}><Server size={13}/> {data.runtime_status}</Badge></div><div className="readiness-grid">{Object.entries(data.checks).map(([name,check])=><div key={name}><strong>{title(name)}</strong><Badge tone={check.ok?'green':'amber'}>{check.ok?'Passing':'Attention required'}</Badge></div>)}</div></section>
  <section className="panel"><div className="section-heading"><div><h2>Production capabilities</h2><p>Missing items remain visible; runtime health never substitutes for accuracy.</p></div></div><div className="readiness-list">{Object.entries(data.capabilities).map(([name,available])=><div key={name}><span>{title(name)}</span><Badge tone={available?'green':'amber'}>{available?'Implemented':'Missing / uncertified'}</Badge></div>)}</div></section>
  <section className="panel"><div className="section-heading"><div><h2>Release blockers</h2><p>These must be resolved and independently verified before deployment.</p></div></div><ol className="blocker-list">{data.release_blockers.map(item=><li key={item}>{item}</li>)}</ol></section>
 </>}
 </>;
}
