import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { queueApi } from '../../../api/queue';
import { useQueueStore } from '../../../store/queueStore';
import { getStoredProfileId } from '../../profile/services/profile.queries';
import { toast } from 'sonner';

export const useQueueStatusQuery = () => {
  const setQueueState = useQueueStore((state) => state.setQueueState);
  const profileId = getStoredProfileId();

  return useQuery({
    queryKey: ['queue-status', profileId],
    queryFn: async () => {
      const response = await queueApi.getQueueStatus();
      setQueueState(response.data);
      return response.data;
    },
    refetchInterval: 4000,
  });
};

export const useCreateQueueMutation = () => {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (payload: {
      jobs: { id: string; title: string; company_name: string; apply_url: string }[];
    }) => queueApi.createQueue(payload),
    onSuccess: (results: any[]) => {
      toast.success(`${results.length} application(s) queued successfully!`);
      queryClient.invalidateQueries({ queryKey: ['queue-status'] });
    },
    onError: (error: Error) => {
      toast.error(error.message || 'Failed to queue applications');
    },
  });
};

// Backend has no pause/resume/cancel endpoints — these just refetch for now
export const usePauseQueueMutation = () => {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async () => {},
    onSuccess: () => {
      toast.info('Pause is not yet supported by the backend.');
      queryClient.invalidateQueries({ queryKey: ['queue-status'] });
    },
  });
};

export const useResumeQueueMutation = () => {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async () => {},
    onSuccess: () => {
      toast.info('Resume is not yet supported by the backend.');
      queryClient.invalidateQueries({ queryKey: ['queue-status'] });
    },
  });
};

export const useCancelQueueMutation = () => {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async () => {},
    onSuccess: () => {
      toast.info('Cancel is not yet supported by the backend.');
      queryClient.invalidateQueries({ queryKey: ['queue-status'] });
    },
  });
};

export const useRetryJobMutation = () => {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (jobId: string) => {
      const profileId = getStoredProfileId();
      if (!profileId) throw new Error('No profile');
      return queueApi.startApply(profileId, Number(jobId));
    },
    onSuccess: () => {
      toast.success('Retrying application...');
      queryClient.invalidateQueries({ queryKey: ['queue-status'] });
    },
    onError: (e: Error) => toast.error(e.message),
  });
};

export const useSkipJobMutation = () =>
  useMutation({ mutationFn: async (_jobId: string) => {} });