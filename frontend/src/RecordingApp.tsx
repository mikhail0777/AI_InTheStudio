import React, { useEffect, useRef, useState } from 'react';
import { SearchResult, SessionStatus, TargetConfiguration } from './types';
import { cancelAnalysis, createSession, deleteSession, getResults, getSessionStatus, pauseAnalysis, resumeAnalysis, startAnalysis, submitResultFeedback, uploadVideo } from './api';
import { Header } from './components/Header';
import { TargetForm } from './components/TargetForm';
import { VideoPlayer } from './components/VideoPlayer';
import { AgentActivityFeed } from './components/AgentActivityFeed';
import { SARReportModal } from './components/SARReportModal';
import { ResultCard } from './components/ResultCard';
import { FileVideo } from 'lucide-react';

const activeStatuses = ['queued', 'analyzing', 'paused'];
const messageOf = (error: unknown) => error instanceof Error ? error.message : 'Unexpected error. Please try again.';

export const RecordingApp: React.FC = () => {
  const [previewFile, setPreviewFile] = useState<File | null>(null);
  const [previewUrl, setPreviewUrl] = useState('');
  const [previewError, setPreviewError] = useState('');
  useEffect(() => {
    setPreviewError('');
    if (!previewFile) { setPreviewUrl(''); return; }
    const url = URL.createObjectURL(previewFile);
    setPreviewUrl(url);
    return () => URL.revokeObjectURL(url);
  }, [previewFile]);
  const [session, setSession] = useState<SessionStatus | null>(null);
  const [monitoredSessionId, setMonitoredSessionId] = useState<string | null>(null);
  const [results, setResults] = useState<SearchResult[]>([]);
  const [selectedResult, setSelectedResult] = useState<SearchResult | null>(null);
  const [videoUrl, setVideoUrl] = useState<string | null>(null);
  const [jumpTimestamp, setJumpTimestamp] = useState<{ seconds: number; key: number } | null>(null);
  const [isUploading, setIsUploading] = useState(false);
  const [uploadProgress, setUploadProgress] = useState(0);
  const [uploadStage, setUploadStage] = useState('');
  const [controlPending, setControlPending] = useState(false);
  const [showReportModal, setShowReportModal] = useState(false);
  const [error, setError] = useState('');
  const [connectionError, setConnectionError] = useState('');
  const [classificationFilter, setClassificationFilter] = useState('matches');
  const [startTime, setStartTime] = useState('');
  const [endTime, setEndTime] = useState('');
  const generation = useRef(0);
  const uploadController = useRef<AbortController | null>(null);
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
        }
        if (latest.playback_url) setVideoUrl(latest.playback_url);
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
    generation.current += 1;
    setIsUploading(true); setError(''); setConnectionError(''); setMonitoredSessionId(null);
    setResults([]); setSelectedResult(null); setVideoUrl(null); setJumpTimestamp(null);
    setClassificationFilter('matches'); setStartTime(''); setEndTime(''); setShowReportModal(false);
    try {
      setUploadStage('Creating investigation');
      const created = await createSession(config);
      setSession(created);
      setUploadStage('Uploading recording');
      const controller = new AbortController(); uploadController.current = controller;
      const uploaded = await uploadVideo(created.session_id, videoFile, setUploadProgress, controller.signal);
      if (uploaded.video_url) setVideoUrl(uploaded.video_url);
      setUploadStage('Starting vehicle search');
      await startAnalysis(created.session_id, config);
      setSession(await getSessionStatus(created.session_id));
      setMonitoredSessionId(created.session_id);
    } catch (failure) {
      setError(failure instanceof DOMException && failure.name === 'AbortError' ? 'Recording upload cancelled. You can retry when ready.' : `Unable to start investigation. ${messageOf(failure)}`);
    } finally { uploadController.current = null; setIsUploading(false); setUploadStage(''); setUploadProgress(0); }
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
    generation.current += 1;
    setMonitoredSessionId(null); setSession(null); setResults([]); setSelectedResult(null);
    setVideoUrl(null); setJumpTimestamp(null); setError(''); setConnectionError(''); setShowReportModal(false);
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
    {session && <Header status={isUploading ? {...session, progress_percent: uploadProgress} : session} onNewMission={handleNewMission} onOpenReport={() => setShowReportModal(true)} isProcessing={isProcessing} isUploading={isUploading} controlPending={controlPending} onControl={handleControl} onDeleteCase={handleDeleteCase} onCancelUpload={() => uploadController.current?.abort()} />}
    {(error || connectionError || session?.error_message || session?.proxy_error) && <div className="app-notice error-message" role="alert">{error || connectionError || session?.error_message || session?.proxy_error}</div>}
    {isUploading && <div className="app-notice" role="status">{uploadStage}…</div>}
    <div className={`workspace-layout ${session ? 'has-investigation' : 'start-workspace'}`}>
      <aside className="case-sidebar"><TargetForm onStartSession={handleStartSession} isProcessing={isProcessing} onPreviewFile={setPreviewFile} /></aside>
      {!session && <section className="landing-preview" aria-label="Recording preview">
        <div className="preview-toolbar"><strong>Recording preview</strong><span>{previewFile ? 'Selected recording' : 'No file selected'}</span></div>
        <div className={`preview-image ${previewUrl ? 'has-video' : 'no-video'}`}>
          {previewUrl ? <video key={previewUrl} src={previewUrl} controls playsInline preload="metadata" aria-label="Preview selected recording"
            onLoadedMetadata={() => setPreviewError('')}
            onError={() => setPreviewError('This file uses a video codec that this browser cannot play. LotTrace may still be able to analyse it after upload.')}/> :
            <div className="recording-placeholder"><FileVideo size={36}/><strong>No recording selected</strong><p>Choose a recording in the search form to preview it here.</p></div>}
        </div>
        {previewError && <div className="preview-error" role="alert">{previewError}</div>}
        <p>{previewFile ? previewFile.name : 'Results will appear here once a recording has been analysed.'}</p>
      </section>}
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
    </div>
    {showReportModal && <SARReportModal status={session} results={results} onClose={() => setShowReportModal(false)} />}
  </div>;
};
