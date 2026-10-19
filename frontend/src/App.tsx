import React, { useEffect, useRef, useState } from 'react';
import { SearchResult, SessionStatus, TargetConfiguration, VehicleSighting } from './types';
import { cancelAnalysis, createSession, deleteSession, getResults, getSessionStatus, getVehicleSightings, pauseAnalysis, resumeAnalysis, startAnalysis, submitResultFeedback, uploadVideo } from './api';
import { Header } from './components/Header';
import { TargetForm } from './components/TargetForm';
import { VideoPlayer } from './components/VideoPlayer';
import { AgentActivityFeed } from './components/AgentActivityFeed';
import { SARReportModal } from './components/SARReportModal';
import { ResultCard } from './components/ResultCard';
import { VehicleHistoryPanel } from './components/VehicleHistoryPanel';

const activeStatuses = ['queued', 'analyzing', 'paused'];
const messageOf = (error: unknown) => error instanceof Error ? error.message : 'Unexpected error. Please try again.';

export const App: React.FC = () => {
  const [view, setView] = useState<'search' | 'history'>('search');
  const [session, setSession] = useState<SessionStatus | null>(null);
  const [monitoredSessionId, setMonitoredSessionId] = useState<string | null>(null);
  const [results, setResults] = useState<SearchResult[]>([]);
  const [selectedResult, setSelectedResult] = useState<SearchResult | null>(null);
  const [videoUrl, setVideoUrl] = useState<string | null>(null);
  const [jumpTimestamp, setJumpTimestamp] = useState<{ seconds: number; key: number } | null>(null);
  const [isUploading, setIsUploading] = useState(false);
  const [uploadStage, setUploadStage] = useState('');
  const [controlPending, setControlPending] = useState(false);
  const [showReportModal, setShowReportModal] = useState(false);
  const [error, setError] = useState('');
  const [connectionError, setConnectionError] = useState('');
  const [classificationFilter, setClassificationFilter] = useState('matches');
  const [startTime, setStartTime] = useState('');
  const [endTime, setEndTime] = useState('');
  const [history, setHistory] = useState<VehicleSighting[]>([]);
  const activeConfig = useRef<TargetConfiguration | null>(null);
  const generation = useRef(0);
  const isProcessing = isUploading || !!(session && activeStatuses.includes(session.status));

  useEffect(() => {
    if (!monitoredSessionId) return;
    let disposed = false;
    let timer: ReturnType<typeof setTimeout>;
    const poll = async () => {
      try {
        const latest = await getSessionStatus(monitoredSessionId);
        if (disposed) return;
        const finished = ['completed', 'error', 'cancelled'].includes(latest.status);
        if (finished) {
          const investigationResults = await getResults(monitoredSessionId);
          if (disposed) return;
          setResults(investigationResults);
          const plate = activeConfig.current?.plate_number;
          if (plate) setHistory(await getVehicleSightings({ plate }));
        }
        setSession(latest);
        setConnectionError('');
        if (finished) return;
      } catch (failure) {
        if (disposed) return;
        setConnectionError(`Connection interrupted; retrying. ${messageOf(failure)}`);
      }
      timer = setTimeout(poll, 1500);
    };
    void poll();
    return () => { disposed = true; clearTimeout(timer); };
  }, [monitoredSessionId]);

  const handleStartSession = async (config: TargetConfiguration, videoFile: File) => {
    if (isProcessing) return;
    setView('search');
    generation.current += 1;
    setIsUploading(true); setError(''); setConnectionError(''); setMonitoredSessionId(null);
    setResults([]); setSelectedResult(null); setVideoUrl(null); setJumpTimestamp(null);
    setHistory([]); activeConfig.current = config;
    setClassificationFilter('matches'); setStartTime(''); setEndTime(''); setShowReportModal(false);
    try {
      setUploadStage('Creating investigation');
      const created = await createSession(config);
      setSession(created);
      setUploadStage('Uploading recording');
      const uploaded = await uploadVideo(created.session_id, videoFile);
      if (uploaded.video_url) setVideoUrl(uploaded.video_url);
      setUploadStage('Starting vehicle search');
      await startAnalysis(created.session_id, config);
      setSession(await getSessionStatus(created.session_id));
      setMonitoredSessionId(created.session_id);
    } catch (failure) {
      setError(`Unable to start investigation. ${messageOf(failure)}`);
    } finally { setIsUploading(false); setUploadStage(''); }
  };

  const handleResultFeedback = async (resultId: string, status: 'confirmed' | 'rejected' | 'needs_research') => {
    if (!session) return;
    const requestGeneration = generation.current;
    try {
      const updated = await submitResultFeedback(session.session_id, resultId, status);
      if (requestGeneration !== generation.current) return;
      setResults(previous => previous.map(result => result.result_id === resultId ? updated : result));
      setError('');
    } catch (failure) {
      if (requestGeneration === generation.current) setError(`Review could not be saved. ${messageOf(failure)}`);
    }
  };
  const handleHistorySearch = async (filters: Record<string, string | number | boolean | undefined>) => {
    try { setHistory(await getVehicleSightings(filters)); setError(''); }
    catch (failure) { setError(`Vehicle history could not be searched. ${messageOf(failure)}`); }
  };

  const handleControl = async (action: 'pause' | 'resume' | 'cancel') => {
    if (!session || controlPending) return;
    setControlPending(true);
    try {
      const perform = { pause: pauseAnalysis, resume: resumeAnalysis, cancel: cancelAnalysis }[action];
      await perform(session.session_id);
      setSession(await getSessionStatus(session.session_id));
      setError('');
    } catch (failure) { setError(`Unable to ${action} investigation. ${messageOf(failure)}`); }
    finally { setControlPending(false); }
  };

  const handleNewMission = () => {
    if (isProcessing) return;
    setView('search');
    generation.current += 1;
    setMonitoredSessionId(null); setSession(null); setResults([]); setSelectedResult(null);
    setVideoUrl(null); setJumpTimestamp(null); setError(''); setConnectionError(''); setShowReportModal(false);
    setHistory([]); activeConfig.current = null;
    setClassificationFilter('matches'); setStartTime(''); setEndTime('');
  };
  const handleDeleteCase = async () => {
    if (!session || isProcessing) return;
    if (!window.confirm('Permanently delete this investigation, uploaded recording, and saved evidence?')) return;
    try {
      await deleteSession(session.session_id);
      handleNewMission();
    } catch (failure) { setError(`Unable to delete investigation. ${messageOf(failure)}`); }
  };
  const jumpTo = (seconds: number) => setJumpTimestamp({ seconds, key: Date.now() });
  const startSeconds = startTime === '' ? 0 : Number(startTime);
  const endSeconds = endTime === '' ? Number.POSITIVE_INFINITY : Number(endTime);
  const matchingResults = results.filter(result => result.human_feedback !== 'rejected'
    && (classificationFilter === 'all' || (classificationFilter === 'matches'
      ? ['strong_match', 'possible_match'].includes(result.classification)
      : result.classification === classificationFilter))
    && result.end_seconds >= startSeconds && result.start_seconds <= endSeconds);
  const supportedCount = results.filter(result => result.classification === 'strong_match').length;
  const emptyDetail = isProcessing ? 'Sightings will appear after the recording has been scanned.'
    : session?.status === 'completed' ? 'No supported sighting was found at the selected scan depth. Try Thorough mode or verify that the plate or vehicle is clearly visible.'
    : session?.status === 'error' ? 'Processing stopped. Review the error and start a new investigation.'
    : session?.status === 'cancelled' ? 'Investigation cancelled. Existing evidence was retained.'
    : 'Add a security recording and the vehicle information you know.';
  const reviewCount = results.filter(result => result.classification === 'possible_match').length;

  return <div className="app-shell">
    <Header status={session} onNewMission={handleNewMission} onOpenReport={() => setShowReportModal(true)} isProcessing={isProcessing} isUploading={isUploading} controlPending={controlPending} onControl={handleControl} onDeleteCase={handleDeleteCase} />
    <nav className="workspace-nav" aria-label="Workspace"><div><button aria-current={view === 'search' ? 'page' : undefined} onClick={() => setView('search')}>Investigation</button><button aria-current={view === 'history' ? 'page' : undefined} onClick={() => setView('history')}>Vehicle history</button></div><span><i /> Local workspace</span></nav>
    {(error || connectionError || session?.error_message) && <div className="app-notice error-message" role="alert">{error || connectionError || session?.error_message}</div>}
    {isUploading && <div className="app-notice" role="status">{uploadStage}…</div>}
    {view === 'history' && <main className="history-workspace"><div className="page-intro"><span className="eyebrow">Your evidence library</span><h2>Every sighting.<br />One place to look.</h2><p>Search vehicle observations across your processed recordings.</p></div><VehicleHistoryPanel sightings={history} plate={activeConfig.current?.plate_number} onSearch={handleHistorySearch} /></main>}
    <main className={`workspace-layout ${session ? 'has-investigation' : 'start-workspace'} ${view === 'history' ? 'view-hidden' : ''}`}>
      {!session && <section className="start-intro"><span className="intro-label"><span /> FROM FOOTAGE TO ANSWERS</span><h2>Find the moment.<br /><span>Follow the vehicle.</span></h2><p>A plate. A colour. A detail you remember.<br />Turn your security footage into evidence you can review.</p><div className="intro-process"><div><b>01</b><span>Add a recording</span></div><div><b>02</b><span>Describe the vehicle</span></div><div><b>03</b><span>Review the sightings</span></div></div><div className="local-note">Your footage stays on this computer.</div></section>}
      <aside className="case-sidebar"><TargetForm onStartSession={handleStartSession} isProcessing={isProcessing} /></aside>
      <div className={`evidence-workspace ${!session ? 'view-hidden' : ''}`}>
        <section className="workspace-heading">
          <div><span className="eyebrow">Investigation workspace</span><h2>Review vehicle evidence</h2><p>{session ? 'Inspect detections against the original recording before confirming a sighting.' : 'Upload footage and describe the vehicle you need to find.'}</p></div>
          <div className="workspace-stats" aria-label="Evidence summary"><div><strong>{results.length}</strong><span>Sightings</span></div><div><strong>{supportedCount}</strong><span>Supported</span></div><div><strong>{reviewCount}</strong><span>Review</span></div></div>
        </section>
        <VideoPlayer videoUrl={videoUrl} status={session} selectedResult={selectedResult} jumpTimestamp={jumpTimestamp?.seconds} jumpKey={jumpTimestamp?.key} />
        <section className="surface sightings-panel">
          <div className="row-between sightings-heading"><div><span className="eyebrow">Evidence timeline</span><h2>Vehicle sightings</h2><p className="muted">{supportedCount} supported · {reviewCount} needs review · {results.length} total</p></div>
            <div className="result-filters" aria-label="Result filters">
              <label className="filter-label">Evidence<select className="input-slot" value={classificationFilter} onChange={event => setClassificationFilter(event.target.value)}><option value="matches">Supported + possible</option><option value="strong_match">Supported sighting</option><option value="possible_match">Review-only</option><option value="all">All</option></select></label>
              <label className="filter-label">From (s)<input className="input-slot" type="number" min="0" value={startTime} onChange={event => setStartTime(event.target.value)} /></label>
              <label className="filter-label">To (s)<input className="input-slot" type="number" min="0" value={endTime} onChange={event => setEndTime(event.target.value)} /></label>
            </div>
          </div>
          <div className="sightings-grid">{matchingResults.length ? matchingResults.map(result => <ResultCard key={result.result_id} result={result} onJumpToTime={jumpTo} onSelectResult={setSelectedResult} onFeedback={handleResultFeedback} />)
            : <div className="empty-state"><strong>{isProcessing ? 'Scanning recording' : 'No vehicle sightings'}</strong><p>{emptyDetail}</p></div>}</div>
        </section>
        <AgentActivityFeed logs={session?.agent_logs || []} currentStage={uploadStage || session?.current_stage || ''} />
      </div>
    </main>
    {showReportModal && <SARReportModal status={session} results={results} onClose={() => setShowReportModal(false)} />}
  </div>;
};
