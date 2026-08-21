import api from './axios';
import { getStoredProfileId } from '../features/profile/services/profile.queries';
import type { QueueStateResponse, QueueItem, JobStatus, QueueStatus } from '../types';

// Shape returned by GET /api/apply/history/{profile_id}
interface BackendApplyHistoryItem {
  application_id: string;
  company_name: string | null;
  job_title: string | null;
  status: string; // 'pending' | 'running' | 'completed' | 'failed' etc.
  started_at: string | null;
  finished_at: string | null;
}

function mapBackendStatusToJobStatus(status: string): JobStatus {
  switch (status) {
    case 'queued':
    case 'pending':
    case 'checking_url':
    case 'rescraped_retry_queued':
      return 'waiting';
    case 'link_expired_rescraping':
    case 'running':
      return 'running';
    case 'needs_input':
      return 'waiting_for_user';
    case 'completed':
    case 'success':
      return 'completed';
    case 'failed':
    case 'error':
    case 'link_expired_rescraped_still_unavailable':
      return 'failed';
    case 'cancelled':
      return 'cancelled';
    default:
      return 'waiting';
  }
}

// Human-readable label for the new intermediate statuses, used in the Queue UI
export function describeBackendStatus(status: string): string {
  switch (status) {
    case 'checking_url':
      return 'Checking job link...';
    case 'link_expired_rescraping':
      return 'Link expired — re-scraping company...';
    case 'rescraped_retry_queued':
      return 'Link refreshed — retrying application';
    case 'link_expired_rescraped_still_unavailable':
      return 'Listing no longer available (re-scraped, still down)';
    case 'queued':
      return 'Queued';
    case 'running':
      return 'Applying...';
    case 'needs_input':
      return 'Waiting for you — open live view';
    case 'completed':
      return 'Completed';
    case 'failed':
      return 'Failed';
    default:
      return status;
  }
}

function mapHistoryToQueueState(history: BackendApplyHistoryItem[]): QueueStateResponse {
  const items: QueueItem[] = history.map((h) => {
    const status = mapBackendStatusToJobStatus(h.status);
    const durationSec =
      h.started_at && h.finished_at
        ? Math.max(0, Math.round((new Date(h.finished_at).getTime() - new Date(h.started_at).getTime()) / 1000))
        : undefined;

    return {
      id: h.application_id,
      jobId: h.application_id,
      jobTitle: h.job_title ?? 'Unknown role',
      company: h.company_name ?? 'Unknown company',
      status,
      statusLabel: describeBackendStatus(h.status),
      attempts: 1,
      addedAt: h.started_at ?? new Date().toISOString(),
      startedAt: h.started_at ?? undefined,
      processedAt: h.finished_at ?? undefined,
      duration: durationSec,
    };
  });

  const total = items.length;
  const completed = items.filter((i) => i.status === 'completed' || i.status === 'failed').length;
  const running = items.find((i) => i.status === 'running');
  const hasRunning = !!running;
  const hasWaiting = items.some((i) => i.status === 'waiting');

  let overallStatus: QueueStatus = 'idle';
  if (hasRunning) overallStatus = 'running';
  else if (hasWaiting) overallStatus = 'paused';
  else if (total > 0 && completed === total) overallStatus = 'completed';

  const completedDurations = items
    .filter((i) => typeof i.duration === 'number')
    .map((i) => i.duration as number);

  const avg = completedDurations.length
    ? Math.round(completedDurations.reduce((a, b) => a + b, 0) / completedDurations.length)
    : 0;
  const fastest = completedDurations.length ? Math.min(...completedDurations) : 0;
  const slowest = completedDurations.length ? Math.max(...completedDurations) : 0;
  const successCount = items.filter((i) => i.status === 'completed').length;
  const successRate = total > 0 ? Math.round((successCount / total) * 100) : 0;

  return {
    status: overallStatus,
    items,
    logs: [], // backend has no log stream endpoint yet
    stats: {
      averageTime: avg,
      fastestTime: fastest,
      slowestTime: slowest,
      totalProcessed: total,
      successRate,
    },
    currentJobId: running?.id,
    progress: {
      completed,
      total,
      percentage: total > 0 ? Math.round((completed / total) * 100) : 0,
      eta: 0,
    },
  };
}

export const queueApi = {
  startApply: (profileId: number, jobId: number) =>
    api.post('/api/apply/start', { profile_id: profileId, job_id: jobId }),

  getApplyStatus: (applicationId: string) =>
    api.get(`/api/apply/status/${applicationId}`),

  getDetails: (applicationId: string) =>
    api.get(`/api/apply/details/${applicationId}`),

  createQueue: async (payload: {
    jobs: { id: string; title: string; company_name: string; apply_url: string }[];
  }) => {
    const profileId = getStoredProfileId();
    if (!profileId) throw new Error('Please save your profile first.');

    const results = await Promise.allSettled(
      payload.jobs.map((job) =>
        api.post('/api/apply/start', {
          profile_id: profileId,
          job_id: Number(job.id),
        })
      )
    );

    const succeeded = results
      .filter((r) => r.status === 'fulfilled')
      .map((r) => (r as PromiseFulfilledResult<any>).value);

    const failed = results.filter((r) => r.status === 'rejected').length;
    if (failed > 0) console.warn(`${failed} job(s) failed to queue`);

    return succeeded;
  },

  // Returns the FULL QueueStateResponse shape the UI expects
  getQueueStatus: async (): Promise<{ data: QueueStateResponse }> => {
    const profileId = getStoredProfileId();
    if (!profileId) {
      return {
        data: {
          status: 'idle',
          items: [],
          logs: [],
          stats: { averageTime: 0, fastestTime: 0, slowestTime: 0, totalProcessed: 0, successRate: 0 },
          progress: { completed: 0, total: 0, percentage: 0, eta: 0 },
        },
      };
    }
    const history: BackendApplyHistoryItem[] = await api.get(`/api/apply/history/${profileId}`);
    return { data: mapHistoryToQueueState(history ?? []) };
  },
};