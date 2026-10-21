import React, {Suspense, useState} from 'react';
import {ArrowLeftRight,ArrowRight, Camera, Car, Check, ChevronRight, HelpCircle, History, LayoutDashboard, LogOut, Menu, Search, ShieldCheck, Upload, Video, X} from 'lucide-react';
import {logoutAuth,type AuthUser} from './api';
import {WorkspaceProvider, useWorkspace} from './workspace/store';
import type {View} from './workspace/model';
import {Brand, Modal, PageHeading} from './workspace/ui';
import {SearchPage} from './workspace/SearchPage';
import {OperationalSightingsPage} from './workspace/OperationalSightingsPage';
import {ReviewPage} from './workspace/ReviewPage';
import {OverviewPage} from './workspace/OverviewPage';
import {HistoryPage} from './workspace/HistoryPage';
import {IncidentPage} from './workspace/IncidentPage';
import {ActivityPage} from './workspace/ActivityPage';
import {AuthGate} from './workspace/AuthGate';
import {VehicleRecordsPage} from './workspace/VehicleRecordsPage';
import {InspectionsPage} from './workspace/InspectionsPage';
import {OperationalIncidentsPage} from './workspace/OperationalIncidentsPage';
import {VehicleEventsPage} from './workspace/VehicleEventsPage';
import './recording.css';

const RecordingApp = React.lazy(() => import('./RecordingApp').then(m => ({default: m.RecordingApp})));
const sampleNav = [
  {id: 'overview', label: 'Overview', icon: LayoutDashboard},
  {id: 'search', label: 'Vehicle search', icon: Search},
  {id: 'sightings', label: 'Sightings', icon: Video},
  {id: 'history', label: 'Vehicle history', icon: History},
  {id: 'incidents', label: 'Incidents', icon: ShieldCheck},
] as const;
const localNav = [
  {id: 'recording', label: 'Analyse recording', icon: Upload},
  {id: 'events', label: 'Arrival / departure', icon: ArrowLeftRight},
  {id: 'search', label: 'Saved sightings', icon: Search},
  {id: 'records', label: 'Vehicle records', icon: Car},
  {id: 'inspections', label: 'Condition inspections', icon: Camera},
  {id: 'incidents', label: 'Incidents', icon: ShieldCheck},
] as const;

function Workspace({user}:{user:AuthUser}) {
  const {view, source, switchSource, navigate, selected, role, setRole, toast, notify, storageError} = useWorkspace();
  const [menu, setMenu] = useState(false);
  const [help, setHelp] = useState(false);
  const sample = source === 'sample';
  const nav = sample ? sampleNav : localNav;
  const go = (page: View, id?: string) => { setMenu(false); navigate(page, id); };

  return <div className="workspace operational">
    <a className="skip-link" href="#main-content" onClick={e => { e.preventDefault(); document.getElementById('main-content')?.focus(); }}>Skip to content</a>
    {menu && <button aria-label="Close navigation" className="sidebar-scrim" onClick={() => setMenu(false)}/>}
    <aside className={`sidebar ${menu ? 'sidebar-open' : ''}`}>
      <Brand onClick={() => go(sample ? 'search' : 'recording')}/>
      <label className="source-switch">Workspace
        <select aria-label="Workspace data source" value={source} onChange={e => { switchSource(e.target.value as 'local' | 'sample'); setMenu(false); }}>
          <option value="local">Your recordings</option>
          <option value="sample">Sample records</option>
        </select>
      </label>
      <nav aria-label="Main navigation">
        {nav.map(n => <button key={n.id} className={view === n.id ? 'active' : ''} aria-current={view === n.id ? 'page' : undefined}
          onClick={() => go(n.id, n.id === 'history' ? selected.vehicleId || 'range' : n.id === 'sightings' ? selected.id : undefined)}>
          <n.icon size={20}/>{n.label}
        </button>)}
      </nav>
      <div className="sidebar-bottom">
        {sample && <button className={view === 'activity' ? 'active' : ''} onClick={() => go('activity')}><History size={19}/> Activity log</button>}
        <button onClick={() => setHelp(true)}><HelpCircle size={19}/> Help</button>
        <div className="workspace-storage">{sample ? 'Sample changes stay in this browser' : 'Local recording workspace'}</div>
      </div>
    </aside>
    <div className="workspace-body">
      <header className="topbar">
        <div className="topbar-left">
          <button className="icon-button menu-toggle" aria-label="Open navigation" onClick={() => setMenu(true)}><Menu size={23}/></button>
          <span className="breadcrumb">{sample ? 'Sample records' : 'Your recordings'} <ChevronRight size={14}/><strong>{nav.find(n => n.id === view)?.label || 'Activity log'}</strong></span>
        </div>
        {sample ? <label className="sample-role">Sample role
          <select aria-label="Sample role" value={role} onChange={e => setRole(e.target.value as typeof role)}>
            <option value="staff">Staff</option><option value="manager">Manager</option>
          </select>
        </label> : <div className="account-summary"><span><strong>{user.display_name}</strong><small>{user.role}</small></span><button className="icon-button" aria-label="Sign out" onClick={async()=>{await logoutAuth();location.reload();}}><LogOut size={18}/></button></div>}
      </header>
      <main id="main-content" tabIndex={-1} className={`workspace-content view-${view}`}>
        {sample && <div className="demo-banner"><span>Sample records and generated images — not results from your recordings.</span><button onClick={() => switchSource('local')}>Return to your recordings <ArrowRight size={15}/></button></div>}
        {sample && storageError && <div className="notice notice-warning" role="alert">{storageError}</div>}
        {sample && view === 'overview' && <OverviewPage/>}
        {sample && view === 'search' && <SearchPage/>}
        {sample && view === 'sightings' && <ReviewPage/>}
        {sample && view === 'history' && <HistoryPage/>}
        {sample && view === 'incidents' && <IncidentPage/>}
        {sample && view === 'activity' && <ActivityPage/>}
        {!sample && view === 'search' && <OperationalSightingsPage/>}
        {!sample && view === 'events' && <VehicleEventsPage/>}
        {!sample && view === 'records' && <VehicleRecordsPage canManage={user.role==='manager'||user.role==='administrator'}/>}
        {!sample && view === 'inspections' && <InspectionsPage/>}
        {!sample && view === 'incidents' && <OperationalIncidentsPage canManage={user.role==='manager'||user.role==='administrator'}/>}
        <div hidden={view !== 'recording' || sample}>
          {view === 'recording' && <PageHeading title="Analyse a recording" description="Upload footage, search for a vehicle, and review the source frames."/>}
          <Suspense fallback={<div className="empty" role="status">Loading recording tools…</div>}>
            <div className="recording-app"><RecordingApp/></div>
          </Suspense>
        </div>
      </main>
    </div>
    {sample && toast && <div className="toast" role="status"><Check size={19}/><span>{toast}</span><button aria-label="Dismiss notification" onClick={() => notify('')}><X size={17}/></button></div>}
    {help && <Modal title="Using LotTrace" onClose={() => setHelp(false)}>
      <p><strong>Analyse recording</strong> searches your footage using the configured LotTrace backend. Check the source frames before confirming a result.</p>
      <p><strong>Saved sightings</strong> searches observations stored by that backend. An empty list means no records match; a connection error means the backend could not be reached.</p>
      <p><strong>Sample records</strong> is a separate, fictional dataset for trying review and incident workflows. It does not measure detection accuracy or include your footage.</p>
      <button className="button button-primary full" onClick={() => { setHelp(false); switchSource('local'); }}>Open your recordings <ArrowRight size={17}/></button>
    </Modal>}
  </div>;
}

export function App() { return <AuthGate>{user=><WorkspaceProvider><Workspace user={user}/></WorkspaceProvider>}</AuthGate>; }
