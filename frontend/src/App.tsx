import React, { useEffect, useRef, useState } from 'react';
import { GPSPoint, TargetConfiguration, SessionStatus, TrackResult } from './types';
import { createSession, uploadVideo, uploadTelemetry, startAnalysis, getSessionStatus, getTelemetry, getTracks, submitHumanFeedback, pauseAnalysis, resumeAnalysis, cancelAnalysis } from './api';
import { Header } from './components/Header';
import { TargetForm } from './components/TargetForm';
import { VideoPlayer } from './components/VideoPlayer';
import { TrackCard } from './components/TrackCard';
import { TrackDetailModal } from './components/TrackDetailModal';
import { AgentActivityFeed } from './components/AgentActivityFeed';
import { TelemetryMap } from './components/TelemetryMap';
import { SARReportModal } from './components/SARReportModal';
import { isReviewCandidate } from './review';

const activeStatuses = ['queued', 'analyzing', 'paused'];
const messageOf = (error: unknown) => error instanceof Error ? error.message : 'Unexpected error. Please try again.';

export const App: React.FC = () => {
  const [session, setSession] = useState<SessionStatus | null>(null);
  const [monitoredSessionId, setMonitoredSessionId] = useState<string | null>(null);
  const [tracks, setTracks] = useState<TrackResult[]>([]);
  const [telemetry, setTelemetry] = useState<GPSPoint[]>([]);
  const [selectedTrack, setSelectedTrack] = useState<TrackResult | null>(null);
  const [videoUrl, setVideoUrl] = useState<string | null>(null);
  const [jumpTimestamp, setJumpTimestamp] = useState<{ seconds: number; key: number } | null>(null);
  const [isUploading, setIsUploading] = useState(false);
  const [uploadStage, setUploadStage] = useState('');
  const [controlPending, setControlPending] = useState(false);
  const [showReportModal, setShowReportModal] = useState(false);
  const [error, setError] = useState('');
  const [connectionError, setConnectionError] = useState('');
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
          const [results, points] = await Promise.all([getTracks(monitoredSessionId), getTelemetry(monitoredSessionId)]);
          if (disposed) return;
          setTracks(results);
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
    setTracks([]); setTelemetry([]); setSelectedTrack(null); setVideoUrl(null); setJumpTimestamp(null);
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
    setMonitoredSessionId(null); setSession(null); setTracks([]); setTelemetry([]); setSelectedTrack(null);
    setVideoUrl(null); setJumpTimestamp(null); setError(''); setConnectionError(''); setShowReportModal(false);
  };
  const jumpTo = (seconds: number) => setJumpTimestamp({ seconds, key: Date.now() });
  const matchingTracks = tracks.filter(isReviewCandidate);
  const emptyDetail = isProcessing ? 'Candidates will appear when processing finishes.'
    : session?.status === 'completed' ? 'No person had enough visible evidence to match the description.'
    : session?.status === 'error' ? 'Processing stopped. Review the error above and retry with a new analysis.'
    : session?.status === 'cancelled' ? 'Analysis was cancelled. Start a new analysis to process the recording.'
    : 'Describe who you are looking for and attach a recording.';

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
        <VideoPlayer videoUrl={videoUrl} tracks={matchingTracks} status={session} selectedTrack={selectedTrack} onSelectTrack={setSelectedTrack} jumpTimestamp={jumpTimestamp?.seconds} jumpKey={jumpTimestamp?.key} />
        <section className="card-module sightings-panel">
          <div className="row-between sightings-heading"><div><h2>Matching people</h2><p className="muted">{matchingTracks.length} results supported by visible evidence</p></div></div>
          <div className="sightings-grid">{matchingTracks.length ? matchingTracks.map(track => <TrackCard key={track.track_id} track={track} isSelected={selectedTrack?.track_id === track.track_id} onSelect={() => setSelectedTrack(track)} onJumpToTime={jumpTo} onFeedback={handleFeedback} />)
            : <div className="empty-state"><strong>{isProcessing ? 'Processing recording' : 'No candidate sightings'}</strong><p>{emptyDetail}</p></div>}</div>
        </section>
      </div>
      <div className="activity-column"><AgentActivityFeed logs={session?.agent_logs || []} currentStage={uploadStage || session?.current_stage || 'idle'} /></div>
    </main>
    <TrackDetailModal track={selectedTrack} onClose={() => setSelectedTrack(null)} onFeedback={handleFeedback} />
    {showReportModal && <SARReportModal status={session} tracks={tracks} onClose={() => setShowReportModal(false)} />}
  </div>;
};
