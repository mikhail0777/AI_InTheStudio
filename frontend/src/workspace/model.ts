export type ReviewStatus = 'pending' | 'confirmed' | 'unrelated';
export type Role = 'staff' | 'manager';
export type View = 'overview' | 'search' | 'sightings' | 'history' | 'incidents' | 'activity' | 'recording' | 'events' | 'records' | 'inspections' | 'readiness';
export type Rect = [number, number, number, number];
export interface ImageAsset { file: string; region: Rect; alt: string }
export interface Vehicle { id: string; plate: string; make: string; model: string; colour: string; year: number; image: ImageAsset }
export interface Sighting {
  id: string; vehicleId: string | null; plate: string; originalPlate: string; camera: string;
  direction: 'Arrival' | 'Departure' | 'Sighting'; at: string; status: ReviewStatus;
  observed: Pick<Vehicle,'make'|'model'|'colour'>; image: ImageAsset; plateRegion: Rect; vehicleBox: Rect;
}
export interface LogEntry { id: string; text: string; at: string; actor: string; vehicleId: string | null; sightingId?: string }
export interface Note { id: string; text: string; actor: string; at: string }
export interface DemoState { version: 2; sightings: Sighting[]; log: LogEntry[]; notes: Note[]; incident: 'open' | 'reviewed' }
export interface SearchFilters { query: string; camera: string; direction: string; colour: string; make: string; model: string; from: string; to: string; review: string; sort: string }
export const emptyFilters: SearchFilters = {query:'',camera:'',direction:'',colour:'',make:'',model:'',from:'',to:'',review:'',sort:'newest'};
export const imageAsset = (sheet: 'dealership'|'fleet', quadrant: number, alt: string): ImageAsset => ({file:`/demo/${sheet}.png`,region:[quadrant%2*768,Math.floor(quadrant/2)*512,768,512],alt});
export const vehicles: Vehicle[] = [
  {id:'range',plate:'KJ72 XLM',make:'Land Rover',model:'Range Rover Sport',colour:'Blue',year:2022,image:imageAsset('dealership',0,'Blue Range Rover at the entrance')},
  {id:'bmw',plate:'KJ72 VDE',make:'BMW',model:'3 Series',colour:'White',year:2022,image:imageAsset('fleet',0,'White BMW arriving')},
  {id:'golf',plate:'KJ72 HZG',make:'Volkswagen',model:'Golf',colour:'Black',year:2022,image:imageAsset('fleet',1,'Black Volkswagen beside the service bay')},
  {id:'camry',plate:'BC42 RNV',make:'Toyota',model:'Camry',colour:'Silver',year:2021,image:imageAsset('fleet',2,'Silver Toyota leaving at dusk')},
  {id:'mazda',plate:'MA21 LPA',make:'Mazda',model:'CX-5',colour:'Red',year:2021,image:imageAsset('fleet',3,'Red Mazda at the entrance')},
];
export const inspections = [imageAsset('dealership',2,'Arrival inspection of the front left bumper, unmarked'),imageAsset('dealership',3,'Pre-departure inspection of the same bumper, with a possible scrape')];
const rawSightings = [
  ['7842','range','Main entrance','Arrival','2026-10-19T08:14:00','KJ72 XLM',0],
  ['7843','bmw','Main entrance','Arrival','2026-10-19T09:18:03','KJ72 VDE',0],
  ['7844','golf','Service bay','Sighting','2026-10-19T09:42:11','KJ72 H?G',1],
  ['7845','range','Main entrance','Sighting','2026-10-19T11:27:00','KJ72 XLM',0],
  ['7846','mazda','Main entrance','Arrival','2026-10-19T13:09:20','MA21 LPA',3],
  ['7847','camry','Service exit','Departure','2026-10-19T18:02:15','BC42 R?V',2],
  ['7848','range','Main exit','Departure','2026-10-19T18:28:00','KJ72 XLM',1],
  ['7838','range','Main entrance','Arrival','2026-10-18T08:40:00','KJ72 XLM',0],
  ['7839','bmw','Main entrance','Sighting','2026-10-18T10:21:09','KJ72 VDE',0],
  ['7840','camry','Service exit','Departure','2026-10-18T18:35:45','BC42 RNV',2],
] as const;
const regions: Record<string,Rect>={range:[348,370,77,24],rear:[1040,308,75,24],bmw:[366,339,88,29],golf:[980,346,90,38],camry:[329,803,91,27],mazda:[1126,856,90,29]};
const boxes: Record<string,Rect>={range:[34,34,33,51],rear:[25,39,52,49],bmw:[34,23,40,57],golf:[19,29,60,55],camry:[29,32,42,47],mazda:[31,21,39,57]};
export function initialState(): DemoState {
  return {version:2,sightings:rawSightings.map(([id,vehicleId,camera,direction,at,plate,q])=>{
    const v=vehicles.find(v=>v.id===vehicleId)!; const key=vehicleId==='range'&&q===1?'rear':vehicleId;
    return {id,vehicleId,plate,originalPlate:plate,camera,direction,at,status:id==='7838'?'confirmed':'pending',observed:{make:v.make,model:v.model,colour:v.colour},image:imageAsset(vehicleId==='range'?'dealership':'fleet',q,v.image.alt),plateRegion:regions[key],vehicleBox:boxes[key]};
  }),log:[],notes:[{id:'initial',text:'Possible pale mark on the front left bumper in the pre-departure photo. Compare with the arrival inspection.',actor:'Liam Carter · Lot attendant (sample)',at:'2026-10-19T18:22:00'}],incident:'open'};
}
export const normalizePlate = (s: string) => s.toUpperCase().replace(/[^A-Z0-9?]/g,'');
export function plateMatches(plate: string, query: string): boolean {
  const p=normalizePlate(plate),q=normalizePlate(query);if(!q)return true;
  for(let i=0;i<=p.length-q.length;i++)if([...q].every((c,j)=>c==='?'||p[i+j]==='?'||p[i+j]===c))return true;
  return false;
}
export function searchSightings(sightings:Sighting[],f:SearchFilters): Sighting[] {
  if(f.from&&f.to&&f.from>f.to)return [];
  return sightings.filter(s=>plateMatches(s.plate,f.query)&&(!f.camera||s.camera===f.camera)&&(!f.direction||s.direction===f.direction)&&(!f.colour||s.observed.colour===f.colour)&&(!f.make||s.observed.make===f.make)&&(!f.model||s.observed.model===f.model)&&(!f.from||s.at.slice(0,10)>=f.from)&&(!f.to||s.at.slice(0,10)<=f.to)&&(!f.review||s.status===f.review)).sort((a,b)=>f.sort==='oldest'?a.at.localeCompare(b.at):b.at.localeCompare(a.at));
}
export type DemoAction =
  | {type:'review';id:string;status:ReviewStatus}
  | {type:'correct';id:string;plate:string;reason:string}
  | {type:'link';id:string;vehicleId:string}
  | {type:'note';text:string}
  | {type:'approve'}
  | {type:'flag';text:string};
/** Pure domain transitions keep demo UI and a future API adapter on the same contract. */
export function applyAction(state:DemoState,action:DemoAction,role:Role,at=new Date().toISOString(),id=crypto.randomUUID()):DemoState {
  const actor=role==='manager'?'Jamie Dalton · Manager':'Alex Morgan · Staff';
  const s='id' in action?state.sightings.find(s=>s.id===action.id):undefined;
  if('id' in action&&!s)throw new Error('Sighting not found.');
  let text='',patch:Partial<Sighting>={},next={...state};
  if(action.type==='review'){patch={status:action.status};text=`${action.status==='confirmed'?'Confirmed':action.status==='unrelated'?'Marked unrelated':'Reopened'} sighting #${s!.id} (${s!.plate}).`;}
  if(action.type==='correct') {const plate=action.plate.trim().toUpperCase();if(!/^[A-Z0-9? -]{3,15}$/.test(plate)||!action.reason.trim())throw new Error('Enter a valid plate and a reason.');patch={plate,status:'pending'};text=`Plate corrected: ${s!.plate} → ${plate}. ${action.reason.trim()}`;}
  if(action.type==='link'){const v=vehicles.find(v=>v.id===action.vehicleId);if(!v)throw new Error('Choose an existing vehicle.');patch={vehicleId:v.id,status:'pending'};text=`Linked sighting #${s!.id} to ${v.plate}; verification required.`;}
  if(action.type==='note'||action.type==='flag'){if(!action.text.trim())throw new Error('Add an observation first.');const note={id,text:action.text.trim(),actor,at};next.notes=[...state.notes,note];text=`${action.type==='flag'?'Flagged possible condition change':'Added inspection note'}: ${note.text}`;if(action.type==='flag')next.incident='open';}
  if(action.type==='approve'){if(role!=='manager')throw new Error('Manager review is required.');next.incident='reviewed';text='Completed incident LT-001 review. No cause or responsibility assigned.';}
  if(s)next.sightings=state.sightings.map(row=>row.id===s.id?{...row,...patch}:row);
  next.log=[{id,text,actor,at,sightingId:s?.id,vehicleId:patch.vehicleId||s?.vehicleId||'range'},...state.log];return next;
}
export const STORAGE_KEY='lottrace-workspace-v2';
export function parseStoredState(raw:string|null):DemoState {
  if(!raw)return initialState();
  try{const s=JSON.parse(raw) as DemoState;
    if(s.version!==2||!Array.isArray(s.sightings)||s.sightings.length!==rawSightings.length||!Array.isArray(s.log)||!Array.isArray(s.notes)||!['open','reviewed'].includes(s.incident))return initialState();
    const seed=initialState();if(!s.sightings.every((row,i)=>row.id===seed.sightings[i].id&&typeof row.plate==='string'&&['pending','confirmed','unrelated'].includes(row.status)&&(row.vehicleId===null||vehicles.some(v=>v.id===row.vehicleId))))return initialState();
    if(!s.log.every(l=>typeof l.text==='string'&&typeof l.actor==='string'&&Number.isFinite(Date.parse(l.at)))||!s.notes.every(n=>typeof n.text==='string'&&typeof n.actor==='string'&&Number.isFinite(Date.parse(n.at))))return initialState();
    // Persist only editable fields; media and source facts come from the trusted fixture.
    return {...s,sightings:seed.sightings.map((row,i)=>({...row,plate:s.sightings[i].plate,status:s.sightings[i].status,vehicleId:s.sightings[i].vehicleId}))};
  }catch{return initialState();}
}
export const day=(at:string)=>new Date(at).toLocaleDateString('en-GB',{day:'numeric',month:'short',year:'numeric'});
export const time=(at:string)=>new Date(at).toLocaleTimeString('en-GB',{hour:'2-digit',minute:'2-digit',second:'2-digit'});
