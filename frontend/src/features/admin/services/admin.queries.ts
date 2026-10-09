import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import api from '@/api/axios';
import { trackedSyncApi } from '@/api/admin';
import { toast } from 'sonner';

/**
 * Extracted from pages/AdminPage.tsx as part of the clean-architecture
 * restructure. Same query key, same staleTime, same response mapping.
 */
export const useAdminStatsQuery = () => {
  return useQuery({
    queryKey: ['admin-stats'],
    queryFn: async () => {
      const data: any = await api.get('/api/jobs/search', { params: { page: 1, limit: 1 } });
      return { total_jobs: data?.total ?? 0 };
    },
    staleTime: 30_000,
  });
};

/**
 * "Sync all tracked companies" progress — polled on a plain interval
 * rather than tied to the queue page's own configurable polling
 * (store/settingsStore.ts): a single company sync takes minutes, so a
 * fixed 5s cadence is both frequent enough to feel live and nowhere near
 * expensive enough to need its own user-facing setting.
 */
export const useTrackedSyncStatusQuery = () => {
  return useQuery({
    queryKey: ['tracked-sync-status'],
    queryFn: () => trackedSyncApi.getStatus(),
    refetchInterval: 5000,
  });
};

export const useStartTrackedSyncMutation = () => {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: () => trackedSyncApi.start(),
    onSuccess: (data) => {
      queryClient.setQueryData(['tracked-sync-status'], data);
      toast.success('Started syncing tracked companies.');
    },
    onError: (error: Error) => {
      toast.error(error.message || 'Failed to start the tracked-company sync');
    },
  });
};

export const usePauseTrackedSyncMutation = () => {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: () => trackedSyncApi.pause(),
    onSuccess: (data) => {
      queryClient.setQueryData(['tracked-sync-status'], data);
      toast.success('Pausing — it will stop after finishing the current company.');
    },
    onError: (error: Error) => {
      toast.error(error.message || 'Failed to pause the tracked-company sync');
    },
  });
};
