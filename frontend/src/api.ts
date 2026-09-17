import { TargetConfiguration, SessionStatus, TrackResult, GPSPoint, SearchResult } from './types';

const API_BASE = '/api';

export async function createSession(target_config?: TargetConfiguration): Promise<SessionStatus> {
  const res = await fetch(`${API_BASE}/sessions`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(target_config || {})
  });
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

export async function uploadVideo(sessionId: string, file: File): Promise<any> {
  const formData = new FormData();
  formData.append('file', file);
  const res = await fetch(`${API_BASE}/sessions/${sessionId}/video`, {
    method: 'POST',
    body: formData
  });
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

export async function getTelemetry(sessionId: string): Promise<GPSPoint[]> {
  const res = await fetch(`${API_BASE}/sessions/${sessionId}/telemetry`);
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

export async function cancelAnalysis(sessionId: string): Promise<any> {
  const res = await fetch(`${API_BASE}/sessions/${sessionId}/cancel`, { method: 'POST' });
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

export async function uploadTelemetry(sessionId: string, file: File): Promise<any> {
  const formData = new FormData();
  formData.append('file', file);
  const res = await fetch(`${API_BASE}/sessions/${sessionId}/telemetry`, {
    method: 'POST',
    body: formData
  });
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

export async function getTracks(sessionId: string): Promise<TrackResult[]> {
  const res = await fetch(`${API_BASE}/sessions/${sessionId}/tracks`);
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

export async function getResults(sessionId: string): Promise<SearchResult[]> {
  const res = await fetch(`${API_BASE}/sessions/${sessionId}/results`);
  if (!res.ok) throw new Error(await res.text());
  return res.json();
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

export async function submitHumanFeedback(
  sessionId: string,
  trackId: number,
  status: 'confirmed' | 'rejected' | 'needs_research',
  notes?: string
): Promise<TrackResult> {
  const res = await fetch(`${API_BASE}/sessions/${sessionId}/tracks/${trackId}/feedback`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ status, notes })
  });
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}
