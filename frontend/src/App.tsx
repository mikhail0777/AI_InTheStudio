import React, { useEffect, useRef, useState } from 'react';
import { GPSPoint, TargetConfiguration, SessionStatus, TrackResult, SearchResult } from './types';
import { createSession, uploadVideo, uploadTelemetry, startAnalysis, getSessionStatus, getTelemetry, getTracks, getResults, submitHumanFeedback, submitResultFeedback, pauseAnalysis, resumeAnalysis, cancelAnalysis } from './api';
import { Header } from './components/Header';
import { TargetForm } from './components/TargetForm';
import { VideoPlayer } from './components/VideoPlayer';
import { TrackCard } from './components/TrackCard';
import { TrackDetailModal } from './components/TrackDetailModal';
import { AgentActivityFeed } from './components/AgentActivityFeed';
import { TelemetryMap } from './components/TelemetryMap';
import { SARReportModal } from './components/SARReportModal';
import { isReviewCandidate } from './review';
import { ResultCard } from './components/ResultCard';

const activeStatuses = ['queued', 'analyzing', 'paused'];
const messageOf = (error: unknown) => error instanceof Error ? error.message : 'Unexpected error. Please try again.';

export const App: React.FC = () => {
  const [session, setSession] = useState<SessionStatus | null>(null);
  const [monitoredSessionId, setMonitoredSessionId] = useState<string | null>(null);
  const [tracks, setTracks] = useState<TrackResult[]>([]);
  const [results, setResults] = useState<SearchResult[]>([]);
  const [telemetry, setTelemetry] = useState<GPSPoint[]>([]);
  const [selectedTrack, setSelectedTrack] = useState<TrackResult | null>(null);
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
  const [entityFilter, setEntityFilter] = useState('all');
  const [minimumScore, setMinimumScore] = useState(0);
  const [startTime, setStartTime] = useState('');
  const [endTime, setEndTime] = useState('');
  const generation = useRef(0);
  const isProcessing = isUploading || !!(session && activeStatuses.includes(session.status));

  // One status source also recovers from dropped connections; avoid duplicate SSE logs.
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
          const [legacyTracks, genericResults, points] = await Promise.all([getTracks(monitoredSessionId), getResults(monitoredSessionId), getTelemetry(monitoredSessionId)]);
          if (disposed) return;
          setTracks(legacyTracks);
          setResults(genericResults);
          setTelemetry(points);
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

  const handleStartSession = async (config: TargetConfiguration, videoFile: File, srtFile?: File) => {
    if (isProcessing) return;
    generation.current += 1;
    setIsUploading(true); setError(''); setConnectionError(''); setMonitoredSessionId(null);
    setTracks([]); setResults([]); setTelemetry([]); setSelectedTrack(null); setSelectedResult(null); setVideoUrl(null); setJumpTimestamp(null);
    setClassificationFilter('matches'); setEntityFilter('all'); setMinimumScore(0); setStartTime(''); setEndTime('');
    setShowReportModal(false);
    try {
      setUploadStage('Creating session');
      const created = await createSession(config);
      setSession(created);
      setUploadStage('Uploading recording');
      const uploaded = await uploadVideo(created.session_id, videoFile);
      if (uploaded.video_url) setVideoUrl(uploaded.video_url);
      if (srtFile) {
        setUploadStage('Reading drone telemetry');
        await uploadTelemetry(created.session_id, srtFile);
        setTelemetry(await getTelemetry(created.session_id));
      }
      setUploadStage('Starting analysis');
      await startAnalysis(created.session_id, config);
      setSession(await getSessionStatus(created.session_id));
      setMonitoredSessionId(created.session_id);
    } catch (failure) {
      setError(`Unable to start analysis. ${messageOf(failure)}`);
    } finally { setIsUploading(false); setUploadStage(''); }
  };

  const handleFeedback = async (trackId: number, status: 'confirmed' | 'rejected' | 'needs_research', notes?: string) => {
    if (!session) return;
    const requestGeneration = generation.current;
    try {
      const updated = await submitHumanFeedback(session.session_id, trackId, status, notes);
      if (requestGeneration !== generation.current) return;
      setTracks(previous => previous.map(track => track.track_id === trackId ? updated : track));
      setSelectedTrack(previous => previous?.track_id === trackId ? updated : previous);
      setError('');
    } catch (failure) { if (requestGeneration === generation.current) setError(`Review could not be saved. ${messageOf(failure)}`); }
  };

  const handleResultFeedback = async (resultId: string, status: 'confirmed' | 'rejected' | 'needs_research', notes?: string) => {
    if (!session) return;
    const requestGeneration = generation.current;
    try {
      const updated = await submitResultFeedback(session.session_id, resultId, status, notes);
      if (requestGeneration !== generation.current) return;
      setResults(previous => previous.map(result => result.result_id === resultId ? updated : result));
      setError('');
    } catch (failure) { if (requestGeneration === generation.current) setError(`Review could not be saved. ${messageOf(failure)}`); }
  };

  const handleControl = async (action: 'pause' | 'resume' | 'cancel') => {
    if (!session || controlPending) return;
    setControlPending(true);
    try {
      const perform = { pause: pauseAnalysis, resume: resumeAnalysis, cancel: cancelAnalysis }[action];
      await perform(session.session_id);
      setSession(await getSessionStatus(session.session_id));
      setError('');
    } catch (failure) { setError(`Unable to ${action} analysis. ${messageOf(failure)}`); }
    finally { setControlPending(false); }
  };

  const handleNewMission = () => {
    if (isProcessing) return;
    generation.current += 1;
    setMonitoredSessionId(null); setSession(null); setTracks([]); setResults([]); setTelemetry([]); setSelectedTrack(null); setSelectedResult(null);
    setVideoUrl(null); setJumpTimestamp(null); setError(''); setConnectionError(''); setShowReportModal(false);
    setClassificationFilter('matches'); setEntityFilter('all'); setMinimumScore(0); setStartTime(''); setEndTime('');
  };
  const jumpTo = (seconds: number) => setJumpTimestamp({ seconds, key: Date.now() });
  const matchingTracks = tracks.filter(isReviewCandidate);
  const entityOptions = Array.from(new Set(results.flatMap(result => result.entities.map(entity => entity.label)))).sort();
  const startSeconds = startTime === '' ? 0 : Number(startTime);
  const endSeconds = endTime === '' ? Number.POSITIVE_INFINITY : Number(endTime);
  const matchingResults = results.filter(result => result.human_feedback !== 'rejected'
    && (classificationFilter === 'all' || (classificationFilter === 'matches'
      ? ['strong_match', 'possible_match'].includes(result.classification)
      : result.classification === classificationFilter))
    && (entityFilter === 'all' || result.entities.some(entity => entity.label === entityFilter))
    && result.overall_score >= minimumScore
    && result.end_seconds >= startSeconds && result.start_seconds <= endSeconds);
  const hasGenericSearch = !!session?.search_query;
  const emptyDetail = isProcessing ? 'Candidates will appear when processing finishes.'
    : session?.status === 'completed' ? 'No matching event was found in the analyzed frames. This does not establish that it is absent from the full video.'
    : session?.status === 'error' ? 'Processing stopped. Review the error above and retry with a new analysis.'
    : session?.status === 'cancelled' ? 'Analysis was cancelled. Start a new analysis to process the recording.'
    : 'Describe what you would like to find and attach a recording.';

  return <div className="app-shell">
    <Header status={session} onNewMission={handleNewMission} onOpenReport={() => setShowReportModal(true)} isProcessing={isProcessing} isUploading={isUploading} controlPending={controlPending} onControl={handleControl} />
    {(error || connectionError || session?.error_message) && <div className="app-notice error-message" role="alert">{error || connectionError || session?.error_message}</div>}
    {isUploading && <div className="app-notice" role="status">{uploadStage}…</div>}
    <main className="layout-grid">
      <div className="layout-column">
        <TargetForm onStartSession={handleStartSession} isProcessing={isProcessing} />
        <TelemetryMap points={telemetry} tracks={matchingTracks} onSelectTrack={track => { setSelectedTrack(track); jumpTo(track.best_timestamp_seconds); }} />
      </div>
      <div className="layout-column">
        <VideoPlayer videoUrl={videoUrl} tracks={matchingTracks} status={session} selectedTrack={selectedTrack} selectedResult={selectedResult} onSelectTrack={setSelectedTrack} jumpTimestamp={jumpTimestamp?.seconds} jumpKey={jumpTimestamp?.key} />
        <section className="card-module sightings-panel">
          <div className="row-between sightings-heading"><div><h2>{hasGenericSearch ? 'Ranked search results' : 'Matching people'}</h2><p className="muted">{hasGenericSearch ? `${matchingResults.length} of ${results.length} localized candidates` : `${matchingTracks.length} results supported by required visible evidence`}</p></div>
            {hasGenericSearch && <div className="result-filters" aria-label="Result filters">
              <label className="filter-label">Classification<select className="input-slot" value={classificationFilter} onChange={event => setClassificationFilter(event.target.value)}><option value="matches">Matches</option><option value="all">All candidates</option><option value="strong_match">Strong</option><option value="possible_match">Possible</option><option value="unlikely_match">Unlikely</option><option value="insufficient_visibility">Insufficient</option></select></label>
              <label className="filter-label">Entity<select className="input-slot" value={entityFilter} onChange={event => setEntityFilter(event.target.value)}><option value="all">All</option>{entityOptions.map(entity => <option key={entity} value={entity}>{entity}</option>)}</select></label>
              <label className="filter-label">Minimum score<input className="input-slot" type="number" min="0" max="1" step="0.05" value={minimumScore} onChange={event => setMinimumScore(Math.min(1, Math.max(0, Number(event.target.value))))} /></label>
              <label className="filter-label">From (s)<input className="input-slot" type="number" min="0" value={startTime} onChange={event => setStartTime(event.target.value)} /></label>
              <label className="filter-label">To (s)<input className="input-slot" type="number" min="0" value={endTime} onChange={event => setEndTime(event.target.value)} /></label>
            </div>}
          </div>
          <div className="sightings-grid">{hasGenericSearch && matchingResults.length ? matchingResults.map(result => <ResultCard key={result.result_id} result={result} onJumpToTime={jumpTo} onSelectResult={setSelectedResult} onFeedback={handleResultFeedback} />)
            : !hasGenericSearch && matchingTracks.length ? matchingTracks.map(track => <TrackCard key={track.track_id} track={track} isSelected={selectedTrack?.track_id === track.track_id} onSelect={() => setSelectedTrack(track)} onJumpToTime={jumpTo} onFeedback={handleFeedback} />)
            : <div className="empty-state"><strong>{isProcessing ? 'Processing recording' : 'No matching events'}</strong><p>{emptyDetail}</p></div>}</div>
        </section>
      </div>
      <div className="activity-column"><AgentActivityFeed logs={session?.agent_logs || []} currentStage={uploadStage || session?.current_stage || 'idle'} /></div>
    </main>
    <TrackDetailModal track={selectedTrack} onClose={() => setSelectedTrack(null)} onFeedback={handleFeedback} />
    {showReportModal && <SARReportModal status={session} tracks={tracks} results={results} onClose={() => setShowReportModal(false)} />}
  </div>;
};
