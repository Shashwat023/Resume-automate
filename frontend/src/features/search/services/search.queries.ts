import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { jobsApi } from '../../../api/jobs';
import { queueApi } from '../../../api/queue';
import { toast } from 'sonner';
import type { SearchFilters } from '../store/searchStore';

const TIMELINE_TO_HOURS: Record<string, number> = {
  '24h': 24,
  week: 24 * 7,
  month: 24 * 30,
};

export const useSearchJobsQuery = (params: {
  keyword?: string;
  filters: SearchFilters;
  page?: number;
  limit?: number;
}) => {
  const { keyword, filters, page, limit } = params;

  // Map frontend filter names → backend parameter names
  const apiParams = {
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
    onSuccess: () => {
      toast.success('Successfully added to queue');
      queryClient.invalidateQueries({ queryKey: ['queue'] });
    },
    onError: (error: any) => {
      toast.error(error.message || 'Failed to create queue');
    },
  });
};