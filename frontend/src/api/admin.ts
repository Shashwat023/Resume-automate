import api from './axios';

export interface SyncResult {
  company_url: string;
  success: boolean;
  jobs_inserted: number;
  jobs_updated: number;
  failed: number;
  timestamp: string;
}

/**
 * Extracted from pages/AdminPage.tsx as part of the clean-architecture
 * restructure — it was previously defined inline in the page component,
 * the one place in the app with no api/feature-file separation at all.
 * Moved verbatim, same request shape, same timeout, same response mapping.
 */
export const adminApi = {
  syncCompany: async (company_url: string): Promise<SyncResult> => {
    const data: any = await api.post('/api/admin/sync', { company_url }, {
      timeout: 15 * 60 * 1000, // 15 minutes — scraping can take a while
    });
    return {
      company_url,
      success: data?.success ?? false,
      jobs_inserted: data?.jobs_inserted ?? 0,
      jobs_updated: data?.jobs_updated ?? 0,
      failed: data?.failed ?? 0,
      timestamp: new Date().toISOString(),
    };
  },
};

/**
 * "Sync all tracked companies" (config/portals.yml) — a separate button
 * from the manual paste-a-URL flow above. Unlike syncCompany, these calls
 * return immediately: the actual multi-hour crawl runs as a background
 * job on the server (see backend/app/services/scraper/bulk_sync_service.py),
 * polled via getTrackedSyncStatus rather than awaited directly.
 */
export interface TrackedSyncStatus {
  status: 'idle' | 'running' | 'paused' | 'completed';
  total_eligible: number;
  processed: number;
  jobs_inserted: number;
  jobs_updated: number;
  companies_failed: number;
  current_company_name: string | null;
  started_at: string | null;
  updated_at: string;
}

export const trackedSyncApi = {
  start: (): Promise<TrackedSyncStatus> => api.post('/api/admin/sync-tracked/start'),
  pause: (): Promise<TrackedSyncStatus> => api.post('/api/admin/sync-tracked/pause'),
  getStatus: (): Promise<TrackedSyncStatus> => api.get('/api/admin/sync-tracked/status'),
};
