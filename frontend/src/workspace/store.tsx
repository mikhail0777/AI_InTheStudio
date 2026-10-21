import React,{createContext,useContext,useEffect,useState} from 'react';
import {applyAction,DemoAction,DemoState,emptyFilters,initialState,parseStoredState,Role,SearchFilters,Sighting,STORAGE_KEY,View,vehicles} from './model';
const routes:View[]=['overview','search','sightings','history','incidents','activity','recording','records','inspections'];
export function workspaceRoute(hash:string){
 const parts=hash.replace(/^#\/?/,'').split('/');
 let source=parts[0]==='sample'?'sample':'local';
 if(source==='sample')parts.shift();
 const [requested,id]=parts;
 if(requested==='recording')source='local';
 const view=source==='local'?(requested==='search'||requested==='records'||requested==='inspections'||requested==='incidents'?requested:'recording'):(routes.includes(requested as View)?requested as View:'search');
 return {source,view,id} as {source:'local'|'sample';view:View;id?:string};
}
const route=()=>workspaceRoute(location.hash);
interface Store {
 data:DemoState; role:Role;setRole:(role:Role)=>void; selected:Sighting;select:(id:string)=>void;
 view:View;source:'local'|'sample';switchSource:(source:'local'|'sample')=>void;navigate:(view:View|null,id?:string)=>void;filters:SearchFilters;setFilters:React.Dispatch<React.SetStateAction<SearchFilters>>;
 act:(action:DemoAction)=>boolean;toast:string;notify:(message:string)=>void;storageError:string;reset:()=>void;
}
const Context=createContext<Store|null>(null);
export const useWorkspace=()=>{const s=useContext(Context);if(!s)throw new Error('Missing workspace provider');return s;};
export function WorkspaceProvider({children}:{children:React.ReactNode}){
 const [data,setData]=useState(()=>{try{return parseStoredState(localStorage.getItem(STORAGE_KEY));}catch{return initialState();}});
 const [role,setRole]=useState<Role>('staff'),[view,setView]=useState<View>(route().view),[source,setSource]=useState<'local'|'sample'>(route().source),[selectedId,select]=useState('7842');
 const [filters,setFilters]=useState<SearchFilters>({...emptyFilters}),[toast,notify]=useState(''),[storageError,setStorageError]=useState('');
 useEffect(()=>{const update=()=>{const r=route();setView(r.view);setSource(r.source);if(r.source==='sample'&&r.id){if(r.view==='history'){const s=data.sightings.find(s=>s.vehicleId===r.id);if(s)select(s.id);}else if(data.sightings.some(s=>s.id===r.id))select(r.id);}};update();window.addEventListener('hashchange',update);return()=>window.removeEventListener('hashchange',update);},[data.sightings]);
 useEffect(()=>{try{localStorage.setItem(STORAGE_KEY,JSON.stringify(data));setStorageError('');}catch{setStorageError('Browser storage is unavailable. Demo changes will only last for this session.');}},[data]);
 useEffect(()=>{if(!toast)return;const timer=setTimeout(()=>notify(''),4500);return()=>clearTimeout(timer);},[toast]);
 const selected=data.sightings.find(s=>s.id===selectedId)||data.sightings[0];
 const setRoute=(fragment:string)=>{if(location.hash!==fragment)location.hash=fragment;const r=workspaceRoute(fragment);setView(r.view);setSource(r.source);window.scrollTo({top:0});};
 const navigate=(next:View|null,id?:string)=>{const mode=next==='recording'?'local':source;setRoute(`#/${mode==='sample'?'sample/':''}${next||(mode==='local'?'recording':'search')}${id?'/'+id:''}`);if(mode==='sample'&&id&&data.sightings.some(s=>s.id===id))select(id);};
 const switchSource=(next:'local'|'sample')=>setRoute(next==='sample'?'#/sample/search':'#/recording');
 const act=(action:DemoAction)=>{try{const next=applyAction(data,action,role);setData(next);notify(next.log[0].text);return true;}catch(e){notify(e instanceof Error?e.message:'Could not save this change.');return false;}};
 return <Context.Provider value={{data,role,setRole,selected,select,view,source,switchSource,navigate,filters,setFilters,act,toast,notify,storageError,reset:()=>{setData(initialState());select('7842');setFilters({...emptyFilters});notify('Sample records restored. Your recordings were not changed.');}}}>{children}</Context.Provider>;
}
