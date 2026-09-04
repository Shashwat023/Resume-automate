export interface Job {
  id: string;
  title: string;
  company_name: string;
  location: string;
  location_type: 'Remote' | 'Hybrid' | 'Onsite';
  industry?: string;
  posted_text?: string;
  posted_date?: string;
  job_type?: string;
  salary?: string;
  description?: string;
  requirements?: string[];
  postedAt?: string;
  status?: 'active' | 'closed' | 'draft';
  apply_url: string;
  company_url?: string;
  ats?: string;
}

export interface Resume {
  id: string;
  file_name: string;
  resume_url: string;
  size?: number;
  uploaded_at: string;
}

import { type ProfileFormValues } from '../features/profile/schema';

export type Profile = ProfileFormValues & {
  id?: string;
  updatedAt?: string;
  completionPercentage?: number;
};

export type JobStatus = 'waiting' | 'running' | 'completed' | 'failed' | 'retrying' | 'skipped' | 'waiting_for_user' | 'cancelled';
export type QueueStatus = 'idle' | 'running' | 'paused' | 'completed' | 'failed' | 'cancelled';

export interface QueueItem {
  id: string;
  jobId: string;
  jobTitle: string;
  company: string;
  company_url?: string;
  ats?: string;
  status: JobStatus;
  // The raw backend status string (e.g. 'paused', 'queued', 'running'),
  // kept alongside the coarser `status` (JobStatus) enum for cases that
  // need a finer distinction than the UI's badge vocabulary carries —
  // e.g. per-row pause/resume needs to tell 'paused' apart from an
  // ordinary 'queued' job, even though both map to JobStatus 'waiting'.
  rawStatus?: string;
  statusLabel?: string;
  attempts: number;
  addedAt: string;
  startedAt?: string;
  processedAt?: string;
  duration?: number; // in seconds
  error?: string;
  currentStep?: string;
}

export interface QueueLog {
  id: string;
  timestamp: string;
  message: string;
  type: 'info' | 'error' | 'success' | 'warning';
}

export interface ExecutionStats {
  averageTime: number; // seconds
  fastestTime: number; // seconds
  slowestTime: number; // seconds
  totalProcessed: number;
  successRate: number; // percentage
}

export interface QueueStateResponse {
  status: QueueStatus;
  items: QueueItem[];
  logs: QueueLog[];
  stats: ExecutionStats;
  currentJobId?: string;
  progress: {
    completed: number;
    total: number;
    percentage: number;
    eta: number; // seconds
  };
}

export interface ApiResponse<T> {
  data: T;
  message?: string;
  success: boolean;
}

export interface PaginationMeta {
  page: number;
  limit: number;
  totalItems: number;
  totalPages: number;
}

export interface PaginatedResponse<T> extends ApiResponse<T[]> {
  meta: PaginationMeta;
}
