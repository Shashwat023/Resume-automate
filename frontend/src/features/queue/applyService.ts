/**
 * React-Query hooks for the auto-apply feature.
 * Replaces the mock queueApi with real backend calls.
 */
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { applyApi } from '../../api/apply';
import { toast } from 'sonner';

/** Kick off an application — POST /api/apply/start */
export const useStartApplyMutation = () => {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: applyApi.startApply,
    onSuccess: (data) => {
      toast.success(`Application started (ID: ${data.application_id})`);
      queryClient.invalidateQueries({ queryKey: ['apply-history'] });
    },
    onError: (err: Error) => toast.error(err.message),
  });
};

/** Poll status of one application — GET /api/apply/status/{id} */
export const useApplyStatusQuery = (applicationId: string | null) =>
  useQuery({
    queryKey: ['apply-status', applicationId],
    queryFn: () => {
      if (!applicationId) throw new Error('No application ID');
      return applyApi.getStatus(applicationId);
    },
    enabled: !!applicationId,
    refetchInterval: (query) => {
      const status = query.state.data?.status;
      // Keep polling while still in-flight
      if (status === 'pending' || status === 'running') return 4000;
      return false;
    },
  });

/** Application history for a profile — GET /api/apply/history/{profile_id} */
export const useApplyHistoryQuery = (profileId: number | null) =>
  useQuery({
    queryKey: ['apply-history', profileId],
    queryFn: () => {
      if (!profileId) throw new Error('No profile ID');
      return applyApi.getHistory(profileId);
    },
    enabled: !!profileId,
    staleTime: 30_000,
  });

/** Full details for one application — GET /api/apply/details/{id} */
export const useApplyDetailsQuery = (applicationId: string | null) =>
  useQuery({
    queryKey: ['apply-details', applicationId],
    queryFn: () => {
      if (!applicationId) throw new Error('No application ID');
      return applyApi.getDetails(applicationId);
    },
    enabled: !!applicationId,
  });
