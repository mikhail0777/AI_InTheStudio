import {useEffect,useState} from 'react';
import {Camera,CheckCircle2,ChevronRight,PlayCircle,RefreshCw,RotateCcw,Search,Upload,XCircle} from 'lucide-react';
import {getVehicleSightings,reviewVehicleSighting} from '../api';
import type {SightingReviewAction,VehicleSighting} from '../types';
import {Badge,Empty,Modal,PageHeading} from './ui';
import {useWorkspace} from './store';

const initialFilters={plate:'',camera:'',date_from:'',date_to:'',color:'',body_type:''};
const eventLabel=(value:string)=>value.split('_').join(' ');
const captured=(row:VehicleSighting)=>row.captured_at?new Date(row.captured_at).toLocaleString():`Recording +${row.best_timestamp_seconds.toFixed(1)}s`;
const displayPlate=(row:VehicleSighting)=>row.corrected_plate||row.observed_plate||'Unread plate';
function Frame({row}:{row:VehicleSighting}){
 const [failed,setFailed]=useState(false);
 return row.evidence_frame&&!failed?<img src={row.evidence_frame} alt={`Source frame for ${displayPlate(row)}`} onError={()=>setFailed(true)}/>:<div className="source-unavailable"><Camera size={24}/><span>Source frame unavailable</span></div>;
}
export function LocalSightingsPage(){
 const {navigate}=useWorkspace();
 const [draft,setDraft]=useState(initialFilters),[applied,setApplied]=useState(initialFilters),[refresh,setRefresh]=useState(0);
 const [rows,setRows]=useState<VehicleSighting[]>([]),[loading,setLoading]=useState(true),[error,setError]=useState(''),[selected,setSelected]=useState<VehicleSighting|null>(null);
 const [plate,setPlate]=useState(''),[reason,setReason]=useState(''),[note,setNote]=useState(''),[saving,setSaving]=useState(false),[reviewError,setReviewError]=useState('');
 const invalid=!!(draft.date_from&&draft.date_to&&draft.date_from>draft.date_to);
 useEffect(()=>{
  const controller=new AbortController();let disposed=false,timedOut=false;
  const timer=setTimeout(()=>{timedOut=true;controller.abort();},15000);
  setLoading(true);setError('');setRows([]);setSelected(null);
  getVehicleSightings({...applied,date_from:applied.date_from?`${applied.date_from}T00:00:00`:undefined,date_to:applied.date_to?`${applied.date_to}T23:59:59.999`:undefined,limit:200},controller.signal)
   .then(result=>{if(!disposed){if(!Array.isArray(result))throw new Error('Invalid response');setRows(result);}})
   .catch(()=>{if(!disposed)setError(timedOut?'The backend did not respond in time. Try again.':'Could not load saved sightings. Check that the LotTrace backend is running, then retry.');})
   .finally(()=>{clearTimeout(timer);if(!disposed)setLoading(false);});
  return()=>{disposed=true;clearTimeout(timer);controller.abort();};
 },[applied,refresh]);
 const field=(key:keyof typeof draft,value:string)=>setDraft(old=>({...old,[key]:value}));
 const choose=(row:VehicleSighting)=>{setSelected(row);setPlate(displayPlate(row));setReason('');setNote(row.review_notes||'');setReviewError('');};
 const act=async(action:SightingReviewAction,values:{corrected_plate?:string;reason?:string;note?:string}={})=>{
  if(!selected||saving)return;setSaving(true);setReviewError('');
  try{const updated=await reviewVehicleSighting(selected.sighting_id,action,values);setSelected(updated);setRows(old=>old.map(row=>row.sighting_id===updated.sighting_id?updated:row));if(action==='correct')setReason('');}
  catch(failure){setReviewError(failure instanceof Error?failure.message:'Review could not be saved.');}
  finally{setSaving(false);}
 };
 return <>
  <PageHeading title="Saved sightings" description="Search vehicle observations from your processed recordings.">
   <button className="button" disabled={loading} onClick={()=>setRefresh(n=>n+1)}><RefreshCw size={17}/> Refresh</button>
   <button className="button button-primary" onClick={()=>navigate('recording')}><Upload size={17}/> Analyse recording</button>
  </PageHeading>
  <form className="local-search panel" onSubmit={e=>{e.preventDefault();if(!invalid)setApplied({...draft});}}>
   <div className="search-input-wrap"><Search size={22}/><input aria-label="Search saved plate" placeholder="Full or partial plate" value={draft.plate} onChange={e=>field('plate',e.target.value)}/><button className="button button-primary" disabled={invalid||loading}>Search</button></div>
   <div className="local-filter-grid"><label>Camera<input value={draft.camera} onChange={e=>field('camera',e.target.value)} placeholder="Any camera"/></label><label>From date<input type="date" value={draft.date_from} onChange={e=>field('date_from',e.target.value)}/></label><label>To date<input type="date" min={draft.date_from} value={draft.date_to} onChange={e=>field('date_to',e.target.value)}/></label><label>Colour<input value={draft.color} onChange={e=>field('color',e.target.value)} placeholder="Any colour"/></label><label>Coarse category<select value={draft.body_type} onChange={e=>field('body_type',e.target.value)}><option value="">Any vehicle</option><option value="car">Car</option><option value="truck">Truck</option><option value="bus">Bus</option><option value="motorcycle">Motorcycle</option></select></label></div>
   <div className="local-filter-footer">{invalid?<span role="alert">End date must be on or after the start date.</span>:<span>Make, model, and year are unavailable until an evaluated model exists.</span>}<button type="button" className="text-button" onClick={()=>{setDraft(initialFilters);setApplied({...initialFilters});}}>Clear filters</button></div>
  </form>
  {loading?<div className="empty" role="status">Loading saved sightings…</div>:error?<div className="notice notice-warning" role="alert"><div><strong>Saved sightings unavailable</strong><p>{error}</p><button className="button" onClick={()=>setRefresh(n=>n+1)}>Retry</button></div></div>:rows.length===0?<Empty title="No saved sightings" action={<button className="button button-primary" onClick={()=>navigate('recording')}><Upload size={17}/> Analyse a recording</button>}>Process a recording to add sightings, or clear your search filters.</Empty>:<section className="panel"><div className="section-heading"><h2>{rows.length} saved sightings</h2><span className="fine-print">Latest 200 matching records</span></div><div className="table-scroll"><table className="sightings-table"><thead><tr><th>Plate</th><th>Camera</th><th>Captured</th><th>Event</th><th>Review</th><th><span className="sr-only">View source</span></th></tr></thead><tbody>{rows.map(row=><tr key={row.sighting_id} onClick={()=>setSelected(row)}><td><button className="vehicle-row-button" onClick={()=>setSelected(row)}><strong>{row.observed_plate||'Unread plate'}</strong></button><small>{[row.vehicle_color,row.vehicle_make,row.vehicle_model].filter(Boolean).join(' · ')||'Vehicle details unavailable'}</small></td><td>{row.camera_name||'Unspecified camera'}</td><td>{captured(row)}</td><td>{eventLabel(row.event_type)}</td><td><Badge tone={row.review_status==='confirmed'?'green':'neutral'}>{row.review_status==='confirmed'?'Verified':row.review_status==='rejected'?'Rejected':'Needs review'}</Badge></td><td><button className="icon-button" aria-label={`Open sighting ${row.sighting_id}`} onClick={()=>setSelected(row)}><ChevronRight size={18}/></button></td></tr>)}</tbody></table></div></section>}
  {selected&&<Modal title={selected.observed_plate||'Vehicle sighting'} wide onClose={()=>setSelected(null)}><div className="local-source-frame"><Frame key={selected.sighting_id} row={selected}/></div><dl className="detail-facts"><div><dt>Camera</dt><dd>{selected.camera_name||'Unspecified'}</dd></div><div><dt>Captured</dt><dd>{captured(selected)}</dd></div><div><dt>Event</dt><dd>{eventLabel(selected.event_type)}</dd></div><div><dt>Recording reference</dt><dd>{selected.session_id}</dd></div></dl><p className="fine-print">Original backend record. Review a recording’s results to confirm or reject a match.</p></Modal>}
 </>;
}
