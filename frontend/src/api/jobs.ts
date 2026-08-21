import api from './axios';
import type { Job, PaginatedResponse } from '../types';

interface BackendJobsResponse {
  jobs: Job[];
  total: number;
  page: number;
  limit: number;
}

export const jobsApi = {
  getSearchJobs: async (params: {
    keyword?: string;
    company_name?: string;
    location?: string;
    location_type?: string;
    ats?: string;
    industry?: string;
    posted_within_hours?: number;
    page?: number;
    limit?: number;
    sort?: string;
  }): Promise<PaginatedResponse<Job>> => {
    const raw: BackendJobsResponse = await api.get('/api/jobs/search', { params });

    const total = raw.total ?? 0;
    const limit = raw.limit ?? 20;
    const totalPages = limit > 0 ? Math.ceil(total / limit) : 1;

    return {
      success: true,
      data: raw.jobs ?? [],
      meta: {
        totalItems: total,
        totalPages,
        page: raw.page ?? 1,
        limit,
      },
    };
  },
};