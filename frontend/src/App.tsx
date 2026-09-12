import React, { useState, useEffect } from 'react';
import { TargetConfiguration, SessionStatus, TrackResult } from './types';
import {
  createSession,
  uploadVideo,
  uploadTelemetry,
  startAnalysis,
  getTracks,
  submitHumanFeedback
} from './api';
import { Header } from './components/Header';
import { TargetForm } from './components/TargetForm';
import { VideoPlayer } from './components/VideoPlayer';
import { TrackCard } from './components/TrackCard';
import { TrackDetailModal } from './components/TrackDetailModal';
import { AgentActivityFeed } from './components/AgentActivityFeed';
import { TelemetryMap } from './components/TelemetryMap';
import { SARReportModal } from './components/SARReportModal';
import { ListFilter, Layers } from 'lucide-react';

export const App: React.FC = () => {
  const [session, setSession] = useState<SessionStatus | null>(null);
  const [tracks, setTracks] = useState<TrackResult[]>([]);
  const [selectedTrack, setSelectedTrack] = useState<TrackResult | null>(null);
  const [videoUrl, setVideoUrl] = useState<string | null>(null);
  const [jumpTimestamp, setJumpTimestamp] = useState<number | null>(null);

  const [isProcessing, setIsProcessing] = useState(false);
  const [showReportModal, setShowReportModal] = useState(false);
  const [filterClassification, setFilterClassification] = useState<string>('all');

  // SSE Stream Listener for real-time Agent Activity Feed
  useEffect(() => {
    if (!session?.session_id || session.status === 'completed' || session.status === 'error') return;

    const eventSource = new EventSource(`/api/sessions/${session.session_id}/events`);

    eventSource.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data);
        if (data.type === 'log') {
          setSession((prev) => {
            if (!prev) return prev;
            return {
              ...prev,
              agent_logs: [...prev.agent_logs, data.log]
            };
          });
        } else if (data.type === 'status') {
          setSession((prev) => {
            if (!prev) return prev;
            return {
              ...prev,
              status: data.status,
              progress_percent: data.progress_percent,
              current_stage: data.current_stage
            };
          });

          if (data.status === 'completed') {
            setIsProcessing(false);
            refreshTracks(session.session_id);
          }
        }
      } catch (err) {
        console.error('SSE JSON error:', err);
      }
    };

    return () => {
      eventSource.close();
    };
  }, [session?.session_id, session?.status]);

  const refreshTracks = async (sessionId: string) => {
    try {
      const fetchedTracks = await getTracks(sessionId);
      setTracks(fetchedTracks);
    } catch (e) {
      console.error('Error fetching tracks:', e);
    }
  };

  const handleStartSession = async (config: TargetConfiguration, videoFile: File, srtFile?: File) => {
    setIsProcessing(true);
    setTracks([]);
    setSelectedTrack(null);

    try {
      // 1. Create Session
      const newSession = await createSession(config);
      setSession(newSession);

      // 2. Upload Video
      await uploadVideo(newSession.session_id, videoFile);
      setVideoUrl(`/uploads/${newSession.session_id}/${videoFile.name}`);

      // 3. Upload Telemetry if present
      if (srtFile) {
        await uploadTelemetry(newSession.session_id, srtFile);
      }

      // 4. Start Agentic Analysis
      await startAnalysis(newSession.session_id, config);
    } catch (err: any) {
      alert(`Error starting analysis: ${err.message}`);
      setIsProcessing(false);
    }
  };

  const handleFeedback = async (trackId: number, status: 'confirmed' | 'rejected' | 'needs_research', notes?: string) => {
    if (!session) return;
    try {
      const updatedTrack = await submitHumanFeedback(session.session_id, trackId, status, notes);
      setTracks((prev) => prev.map((t) => (t.track_id === trackId ? updatedTrack : t)));
      if (selectedTrack?.track_id === trackId) {
        setSelectedTrack(updatedTrack);
      }
    } catch (e: any) {
      alert(`Error submitting feedback: ${e.message}`);
    }
  };

  const handleNewMission = () => {
    setSession(null);
    setTracks([]);
    setSelectedTrack(null);
    setVideoUrl(null);
    setIsProcessing(false);
  };

  const filteredTracks = tracks.filter((t) => {
    if (filterClassification === 'all') return true;
    return t.classification === filterClassification;
  });

  return (
    <div style={{ display: 'flex', flexDirection: 'column', minHeight: '100vh' }}>
      <Header
        status={session}
        onNewMission={handleNewMission}
        onOpenReport={() => setShowReportModal(true)}
      />

      <main className="layout-grid" style={{ padding: '24px', maxWidth: '1440px', margin: '0 auto', width: '100%' }}>
        {/* Left Column: Target Configuration & Telemetry Map */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: '32px' }}>
          <TargetForm onStartSession={handleStartSession} isProcessing={isProcessing} />
          <TelemetryMap tracks={tracks} onSelectTrack={(t) => { setSelectedTrack(t); setJumpTimestamp(t.best_timestamp_seconds); }} />
        </div>

        {/* Center Column: Video Player & Ranked Sightings List */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: '32px' }}>
          <VideoPlayer
            videoUrl={videoUrl}
            tracks={tracks}
            status={session}
            selectedTrack={selectedTrack}
            onSelectTrack={(t) => setSelectedTrack(t)}
            jumpTimestamp={jumpTimestamp}
          />

          {/* Ranked Sightings Panel */}
          <div className="card-module" style={{ flex: 1, padding: 0, overflow: 'hidden', display: 'flex', flexDirection: 'column' }}>
            <div className="screws" />
            
            <div style={{ padding: '24px', borderBottom: '1px solid var(--shadow-dark)', background: 'rgba(255,255,255,0.2)' }}>
              <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
                  <Layers size={20} color="var(--accent-orange)" />
                  <span style={{ fontWeight: 800, fontSize: '1.25rem', letterSpacing: '-0.03em' }}>RANKED SIGHTINGS</span>
                  <span className="status-label" style={{ background: 'var(--bg-recessed)', padding: '4px 8px', borderRadius: '4px' }}>
                    {filteredTracks.length} MODULES
                  </span>
                </div>

                {/* Classification Filter */}
                <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                  <ListFilter size={16} color="var(--text-muted)" />
                  <select
                    className="input-slot"
                    value={filterClassification}
                    onChange={(e) => setFilterClassification(e.target.value)}
                    style={{ padding: '6px 12px', width: 'auto', background: 'var(--bg-recessed)' }}
                  >
                    <option value="all">ALL CANDIDATES</option>
                    <option value="strong_match">STRONG MATCHES</option>
                    <option value="possible_match">POSSIBLE MATCHES</option>
                    <option value="unlikely_match">UNLIKELY MATCHES</option>
                  </select>
                </div>
              </div>
            </div>

            <div style={{
              display: 'grid',
              gridTemplateColumns: 'repeat(auto-fill, minmax(320px, 1fr))',
              gap: '24px',
              padding: '24px',
              overflowY: 'auto',
              maxHeight: '480px',
              background: 'var(--bg-chassis)'
            }}>
              {filteredTracks.length === 0 ? (
                <div style={{ gridColumn: '1 / -1', textAlign: 'center', padding: '64px', color: 'var(--text-muted)' }}>
                  <p style={{ fontWeight: 700, fontSize: '1.25rem' }}>NO CANDIDATE SIGHTINGS</p>
                  <p className="status-label" style={{ marginTop: '8px' }}>AWAITING DATA STREAM...</p>
                </div>
              ) : (
                filteredTracks.map((t) => (
                  <TrackCard
                    key={t.track_id}
                    track={t}
                    isSelected={selectedTrack?.track_id === t.track_id}
                    onSelect={() => setSelectedTrack(t)}
                    onJumpToTime={(sec) => setJumpTimestamp(sec)}
                    onFeedback={handleFeedback}
                  />
                ))
              )}
            </div>
          </div>
        </div>

        {/* Right Column: Agent Activity Feed */}
        <div style={{ display: 'flex', flexDirection: 'column' }}>
          <AgentActivityFeed
            logs={session?.agent_logs || []}
            currentStage={session?.current_stage || 'idle'}
          />
        </div>
      </main>

      {/* Deep Evidence Inspection Modal */}
      <TrackDetailModal
        track={selectedTrack}
        onClose={() => setSelectedTrack(null)}
        onFeedback={handleFeedback}
      />

      {/* Post-Flight SAR Report Modal */}
      {showReportModal && (
        <SARReportModal
          status={session}
          tracks={tracks}
          onClose={() => setShowReportModal(false)}
        />
      )}
    </div>
  );
};
