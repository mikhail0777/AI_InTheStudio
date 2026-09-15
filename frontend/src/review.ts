import type { AttributeDetail, TrackResult } from './types';

export const candidateLabels: Record<TrackResult['classification'], string> = {
  strong_match: 'Likely candidate',
  possible_match: 'Possible candidate',
  insufficient_visibility: 'Limited visibility',
  unlikely_match: 'Low similarity',
};

export function reviewLabel(track: TrackResult): string {
  switch (track.human_feedback) {
    case 'confirmed': return 'Confirmed by reviewer';
    case 'rejected': return 'Rejected by reviewer';
    case 'needs_research': return 'Flagged for further review';
    default: return 'Awaiting human review';
  }
}

export function attributeLabel(detail: AttributeDetail): string {
  switch (detail.assessment) {
    case 'match': return 'Supports description';
    case 'conflict': return 'Conflicts with description';
    default: return 'Not established';
  }
}

export function isReviewCandidate(track: TrackResult): boolean {
  return track.human_feedback !== 'rejected' &&
    (track.classification === 'strong_match' || track.classification === 'possible_match' || track.human_feedback === 'confirmed' || track.human_feedback === 'needs_research');
}

export function formatTime(seconds: number): string {
  const safe = Number.isFinite(seconds) ? Math.max(0, seconds) : 0;
  return `${Math.floor(safe / 60).toString().padStart(2, '0')}:${Math.floor(safe % 60).toString().padStart(2, '0')}`;
}
