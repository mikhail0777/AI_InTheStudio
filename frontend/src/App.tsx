import React, { useState, useEffect } from 'react';
import { TargetConfiguration, SessionStatus, TrackResult } from './types';
import {
  createSession,
  uploadVideo,
  uploadTelemetry,
  startAnalysis,
  getSessionStatus,
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
import { ListFilter, AlertTriangle, Layers } from 'lucide-react';

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
      const vRes = await uploadVideo(newSession.session_id, videoFile);
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
    <div className="app-container">
      <Header
        status={session}
        onNewMission={handleNewMission}
        onOpenReport={() => setShowReportModal(true)}
      />

      <main className="main-content">
        {/* Left Column: Target Configuration & Telemetry Map */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: '1rem' }}>
          <TargetForm onStartSession={handleStartSession} isProcessing={isProcessing} />
          <TelemetryMap tracks={tracks} onSelectTrack={(t) => { setSelectedTrack(t); setJumpTimestamp(t.best_timestamp_seconds); }} />
        </div>

        {/* Center Column: Video Player & Ranked Sightings List */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: '1rem' }}>
          <VideoPlayer
            videoUrl={videoUrl}
            tracks={tracks}
            status={session}
            selectedTrack={selectedTrack}
            onSelectTrack={(t) => setSelectedTrack(t)}
            jumpTimestamp={jumpTimestamp}
          />

          {/* Ranked Sightings List Panel */}
          <div className="panel" style={{ flex: 1 }}>
            <div className="panel-header">
              <span className="panel-title">
                <Layers size={18} /> Ranked Candidate Sightings ({filteredTracks.length})
              </span>

              {/* Classification filter */}
              <div style={{ display: 'flex', alignItems: 'center', gap: '0.4rem' }}>
                <ListFilter size={14} color="var(--text-muted)" />
                <select
                  className="select"
                  value={filterClassification}
                  onChange={(e) => setFilterClassification(e.target.value)}
                  style={{ padding: '0.2rem 0.5rem', fontSize: '0.75rem' }}
                >
                  <option value="all">All Classifications</option>
                  <option value="strong_match">Strong Matches</option>
                  <option value="possible_match">Possible Matches</option>
                  <option value="unlikely_match">Unlikely Matches</option>
                </select>
              </div>
            </div>

            <div style={{
              display: 'grid',
              gridTemplateColumns: 'repeat(auto-fill, minmax(320px, 1fr))',
              gap: '0.8rem',
              overflowY: 'auto',
              maxHeight: '400px',
              paddingRight: '0.3rem'
            }}>
              {filteredTracks.length === 0 ? (
                <div style={{ gridColumn: '1 / -1', textAlign: 'center', padding: '2rem', color: 'var(--text-muted)' }}>
                  No candidate sightings matched current filter.
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

      {/* Track Details Modal */}
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
