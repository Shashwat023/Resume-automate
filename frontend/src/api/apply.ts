import api from './axios';

// ── Types matching backend apply schemas ──────────────────────────────
export interface ApplyStartRequest {
  profile_id: number;
  job_id: number;
}

export interface ApplyStartResponse {
  application_id: string;
  status: string;
}

export interface ApplyStatusResponse {
  application_id: string;
  status: string;
  job_title: string | null;
  company: string | null;
  started_at: string | null;
  finished_at: string | null;
  error: string | null;
}

export interface ApplyHistoryItem {
  application_id: string;
  company_name: string | null;
  job_title: string | null;
  status: string;
  started_at: string | null;
  finished_at: string | null;
}

export interface ApplyDetailsResponse {
  application_id: string;
  profile: Record<string, unknown>;
  job: Record<string, unknown>;
  status: string;
  error: string | null;
  started_at: string | null;
  finished_at: string | null;
}

export const applyApi = {
  /**
   * Start an auto-apply task — POST /api/apply/start
   */
  startApply: (payload: ApplyStartRequest) =>
    api.post<never, ApplyStartResponse>('/api/apply/start', payload),

  /**
   * Poll application status — GET /api/apply/status/{application_id}
   */
  getStatus: (applicationId: string) =>
    api.get<never, ApplyStatusResponse>(`/api/apply/status/${applicationId}`),

  /**
   * Get application history for a profile — GET /api/apply/history/{profile_id}
   */
  getHistory: (profileId: number) =>
    api.get<never, ApplyHistoryItem[]>(`/api/apply/history/${profileId}`),

  /**
   * Get full details for one application — GET /api/apply/details/{application_id}
   */
  getDetails: (applicationId: string) =>
    api.get<never, ApplyDetailsResponse>(`/api/apply/details/${applicationId}`),
};
