import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { jobsApi } from '../../../api/jobs';
import { queueApi } from '../../../api/queue';
import { toast } from 'sonner';
import type { SearchFilters } from '../store/searchStore';
import type { Job } from '@/types';

const TIMELINE_TO_HOURS: Record<string, number> = {
  '24h': 24,
  week: 24 * 7,
  month: 24 * 30,
};

export function buildSearchParams(params: {
  keyword?: string;
  filters: SearchFilters;
  page?: number;
  limit?: number;
}) {
  const { keyword, filters, page, limit } = params;
  // Map frontend filter names → backend parameter names
  return {
    keyword: keyword || undefined,
    company_name: filters.company || undefined,
    location: filters.location || undefined,
    location_type: filters.jobType === 'All' ? undefined : filters.jobType,
    ats: filters.ats === 'All' ? undefined : filters.ats,
    industry: filters.industry === 'All' ? undefined : filters.industry,
    posted_within_hours:
      filters.timeline === 'All' ? undefined : TIMELINE_TO_HOURS[filters.timeline],
    page,
    limit,
  };
}

/** Hard ceiling so "Auto Apply All Filtered" can never enqueue an unbounded set. */
export const MAX_FILTERED_QUEUE_JOBS = 500;

/**
 * Every job matching the current search, across ALL pages (the table only
 * holds one page, so queueing `jobs` alone silently dropped the rest).
 */
export async function fetchAllFilteredJobs(params: {
  keyword?: string;
  filters: SearchFilters;
}) {
  const pageSize = 100;
  const collected: Job[] = [];
  let page = 1;
  for (;;) {
    const response = await jobsApi.getSearchJobs(
      buildSearchParams({ ...params, page, limit: pageSize })
    );
    collected.push(...response.data);
    const done =
      page >= response.meta.totalPages ||
      response.data.length === 0 ||
      collected.length >= MAX_FILTERED_QUEUE_JOBS;
    if (done) break;
    page += 1;
  }
  return collected.slice(0, MAX_FILTERED_QUEUE_JOBS);
}

export const useSearchJobsQuery = (params: {
  keyword?: string;
  filters: SearchFilters;
  page?: number;
  limit?: number;
}) => {
  const apiParams = buildSearchParams(params);

  return useQuery({
    queryKey: ['jobs', 'search', apiParams],
    queryFn: () => jobsApi.getSearchJobs(apiParams),
    placeholderData: (previousData) => previousData,
  });
};

export const useCreateQueueMutation = () => {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (payload: { jobs: { id: string; title: string; company_name: string; apply_url: string }[] }) => {
      return queueApi.createQueue(payload);
    },
    onSuccess: (succeeded, variables) => {
      const added = succeeded.length;
      toast.success(`Added ${added} job${added === 1 ? '' : 's'} to the queue`);
      const skipped = variables.jobs.length - added;
      if (skipped > 0) {
        toast.warning(`${skipped} job${skipped === 1 ? '' : 's'} skipped (already queued, applied, or awaiting review)`);
      }
      queryClient.invalidateQueries({ queryKey: ['queue'] });
      queryClient.invalidateQueries({ queryKey: ['queue-status'] });
    },
    onError: (error: any) => {
      toast.error(error.message || 'Failed to create queue');
    },
  });
};
