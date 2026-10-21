import { TargetConfiguration, SessionStatus, SearchResult, SightingReviewAction, VehicleSighting } from './types';

const API_BASE = '/api';
export interface AuthUser {user_id:string;dealership_id:string;email:string;display_name:string;role:'viewer'|'reviewer'|'manager'|'administrator'|'auditor'}
export interface VehicleRecord {vehicle_id:string;normalized_plate:string|null;vin:string|null;stock_number:string|null;make:string|null;model:string|null;year:number|null;color:string|null;body_type:string|null;status:string;notes:string|null;updated_at:string}
export interface TimelineItem {type:'sighting'|'plate_alias'|'audit';at:string;data:Record<string,unknown>}
export interface VehicleEvent {
 event_id:string;event_type:'arrival'|'departure';occurred_at:string;timezone:string;
 consensus_plate:string|null;plate_match_state:string;matched_vehicle_id:string|null;
 review_state:'confirmed'|'requires_review';review_reason:string|null;camera_name:string;
 boundary_name:string;best_vehicle_crop:string|null;best_plate_crop:string|null;
 previous_status:string|null;new_status:string|null;
}
async function json<T>(url:string,init?:RequestInit):Promise<T>{const res=await fetch(url,init);if(!res.ok)throw new Error((await res.json().catch(()=>null))?.detail||await res.text()||`Request failed (${res.status}).`);return res.json();}
export const getAuthStatus=()=>json<{configured:boolean;user:AuthUser|null}>(`${API_BASE}/auth/status`);
export const bootstrapAuth=(body:Record<string,string>)=>json<{user:AuthUser}>(`${API_BASE}/auth/bootstrap`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});
export const loginAuth=(email:string,password:string)=>json<{user:AuthUser}>(`${API_BASE}/auth/login`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({email,password})});
export const logoutAuth=()=>json(`${API_BASE}/auth/logout`,{method:'POST'});
export const getVehicles=()=>json<VehicleRecord[]>(`${API_BASE}/vehicles`);
export const createVehicleRecord=(body:Record<string,unknown>)=>json<VehicleRecord>(`${API_BASE}/vehicles`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});
export const getVehicleTimeline=(id:string)=>json<TimelineItem[]>(`${API_BASE}/vehicles/${encodeURIComponent(id)}/timeline`);
export const getVehicleEvents=(review_state?:string)=>json<VehicleEvent[]>(`${API_BASE}/vehicle-events${review_state?`?review_state=${encodeURIComponent(review_state)}`:''}`);
export const linkSighting=(sightingId:string,vehicle_id:string,reason:string)=>json(`${API_BASE}/vehicle-sightings/${encodeURIComponent(sightingId)}/link`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({vehicle_id,reason})});
export interface InspectionMedia {media_id:string;viewpoint:string;source_filename:string;sha256:string;width:number;height:number;evidence_url:string|null}
export interface Inspection {inspection_id:string;vehicle_id:string;inspection_type:'arrival'|'departure';status:string;captured_at:string;device_label:string|null;media_count?:number;media?:InspectionMedia[];annotations?:Array<Record<string,unknown>>;required_viewpoints?:string[]}
export interface Incident {incident_id:string;vehicle_id:string|null;title:string;summary:string|null;priority:string;status:string;created_at:string;evidence?:Array<Record<string,unknown>>;notes?:Array<Record<string,unknown>>;approvals?:Array<Record<string,unknown>>;holds?:Array<Record<string,unknown>>;attachments?:Array<Record<string,unknown>>}
export const getInspections=(vehicle_id?:string)=>json<Inspection[]>(`${API_BASE}/inspections${vehicle_id?`?vehicle_id=${encodeURIComponent(vehicle_id)}`:''}`);
export const createInspection=(body:Record<string,unknown>)=>json<Inspection>(`${API_BASE}/inspections`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});
export const getInspection=(id:string)=>json<Inspection>(`${API_BASE}/inspections/${encodeURIComponent(id)}`);
export async function uploadInspectionMedia(id:string,viewpoint:string,file:File){const body=new FormData();body.append('file',file);return json<InspectionMedia>(`${API_BASE}/inspections/${encodeURIComponent(id)}/media?viewpoint=${encodeURIComponent(viewpoint)}`,{method:'POST',body});}
export const completeInspection=(id:string)=>json<Inspection>(`${API_BASE}/inspections/${encodeURIComponent(id)}/complete`,{method:'POST'});
export const annotateInspectionMedia=(id:string,body:Record<string,unknown>)=>json(`${API_BASE}/inspection-media/${encodeURIComponent(id)}/annotations`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});
export const getIncidents=()=>json<Incident[]>(`${API_BASE}/incidents`);
export const createIncident=(body:Record<string,unknown>)=>json<Incident>(`${API_BASE}/incidents`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});
export const getIncident=(id:string)=>json<Incident>(`${API_BASE}/incidents/${encodeURIComponent(id)}`);
export const addIncidentEvidence=(id:string,body:Record<string,unknown>)=>json(`${API_BASE}/incidents/${encodeURIComponent(id)}/evidence`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});
export const addIncidentNote=(id:string,note:string)=>json(`${API_BASE}/incidents/${encodeURIComponent(id)}/notes`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({note})});
export const decideIncident=(id:string,action:'approve'|'reopen',reason:string)=>json<Incident>(`${API_BASE}/incidents/${encodeURIComponent(id)}/decision`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({action,reason})});
export const holdIncident=(id:string,reason:string)=>json(`${API_BASE}/incidents/${encodeURIComponent(id)}/holds`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({reason})});
export async function uploadIncidentAttachment(id:string,file:File){const body=new FormData();body.append('file',file);return json(`${API_BASE}/incidents/${encodeURIComponent(id)}/attachments`,{method:'POST',body});}
export async function exportIncident(id:string){const response=await fetch(`${API_BASE}/incidents/${encodeURIComponent(id)}/exports`,{method:'POST'});if(!response.ok)throw new Error((await response.json().catch(()=>null))?.detail||'Export failed.');const blob=await response.blob();const url=URL.createObjectURL(blob);const anchor=document.createElement('a');anchor.href=url;anchor.download=`lottrace-${id}.zip`;anchor.click();URL.revokeObjectURL(url);return {manifestHash:response.headers.get('X-Manifest-SHA256'),archiveHash:response.headers.get('X-Archive-SHA256')};}

export async function createSession(target_config?: TargetConfiguration): Promise<SessionStatus> {
  const res = await fetch(`${API_BASE}/sessions`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(target_config || {})
  });
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}
export async function uploadVideo(sessionId: string, file: File, onProgress?: (percent: number) => void, signal?: AbortSignal): Promise<any> {
  return new Promise((resolve, reject) => {
    const request = new XMLHttpRequest();
    const abort = () => request.abort();
    const cleanup = () => signal?.removeEventListener('abort', abort);
    request.open('POST', `${API_BASE}/sessions/${sessionId}/video`);
    request.upload.onprogress = event => {
      if (event.lengthComputable) onProgress?.(Math.round(event.loaded / event.total * 100));
    };
    request.onload = () => {
      cleanup();
      if (request.status >= 200 && request.status < 300) {
        try { resolve(JSON.parse(request.responseText)); }
        catch { reject(new Error('The upload response was invalid.')); }
      } else reject(new Error(request.responseText || `Upload failed (${request.status}).`));
    };
    request.onerror = () => { cleanup(); reject(new Error('The recording upload was interrupted.')); };
    request.onabort = () => { cleanup(); reject(new DOMException('Upload cancelled.', 'AbortError')); };
    signal?.addEventListener('abort', abort, { once: true });
    const formData = new FormData(); formData.append('file', file);
    request.send(formData);
  });
}

export async function cancelAnalysis(sessionId: string): Promise<any> {
  const res = await fetch(`${API_BASE}/sessions/${sessionId}/cancel`, { method: 'POST' });
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

export async function startAnalysis(sessionId: string, target_config?: TargetConfiguration): Promise<any> {
  const res = await fetch(`${API_BASE}/sessions/${sessionId}/analyze`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(target_config || null)
  });
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

export async function pauseAnalysis(sessionId: string): Promise<any> {
  const res = await fetch(`${API_BASE}/sessions/${sessionId}/pause`, { method: 'POST' });
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

export async function resumeAnalysis(sessionId: string): Promise<any> {
  const res = await fetch(`${API_BASE}/sessions/${sessionId}/resume`, { method: 'POST' });
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

export async function getSessionStatus(sessionId: string): Promise<SessionStatus> {
  const res = await fetch(`${API_BASE}/sessions/${sessionId}/status`);
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

export async function getResults(sessionId: string): Promise<SearchResult[]> {
  const res = await fetch(`${API_BASE}/sessions/${sessionId}/results`);
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

export async function getVehicleSightings(filters: Record<string, string | number | boolean | undefined>, signal?: AbortSignal): Promise<VehicleSighting[]> {
  const params = new URLSearchParams();
  Object.entries(filters).forEach(([key, value]) => {
    if (value !== undefined && value !== '') params.set(key, String(value));
  });
  const res = await fetch(`${API_BASE}/vehicle-sightings?${params}`, { signal });
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

export async function reviewVehicleSighting(
  sightingId: string,
  action: SightingReviewAction,
  values: { corrected_plate?: string; note?: string; reason?: string } = {}
): Promise<VehicleSighting> {
  const res = await fetch(`${API_BASE}/vehicle-sightings/${encodeURIComponent(sightingId)}/review`, {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ action, ...values })
  });
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

export async function deleteSession(sessionId: string): Promise<void> {
  const res = await fetch(`${API_BASE}/sessions/${sessionId}`, { method: 'DELETE' });
  if (!res.ok) throw new Error(await res.text());
}

export async function submitResultFeedback(
  sessionId: string,
  resultId: string,
  status: 'confirmed' | 'rejected' | 'needs_research',
  notes?: string
): Promise<SearchResult> {
  const res = await fetch(`${API_BASE}/sessions/${sessionId}/results/${encodeURIComponent(resultId)}/feedback`, {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ status, notes })
  });
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}
