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
