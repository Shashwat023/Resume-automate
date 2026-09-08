import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { queueApi } from '../../../api/queue';
import { useQueueStore } from '../../../store/queueStore';
import { getStoredProfileId } from '@/lib/session';
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

// Day 4 Part H: per-row pause/resume, targeting an EXPLICIT application id
// rather than only the queue's current job — this is what QueueTable's
// per-row buttons use, so a mistakenly-queued job can be stopped before it
// ever starts, not just while it's the one actively running.
export const usePauseJobMutation = () => {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (applicationId: string) => queueApi.pauseApply(applicationId),
    onSuccess: () => {
      toast.success('Paused. Press play to continue.');
      queryClient.invalidateQueries({ queryKey: ['queue-status'] });
    },
    onError: (error: Error) => {
      toast.error(error.message || 'Failed to pause');
    },
  });
};

export const useResumeJobMutation = () => {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (applicationId: string) => queueApi.resumeApply(applicationId),
    onSuccess: () => {
      toast.success('Resumed.');
      queryClient.invalidateQueries({ queryKey: ['queue-status'] });
    },
    onError: (error: Error) => {
      toast.error(error.message || 'Failed to resume');
    },
  });
};

export const useCancelJobMutation = () => {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (applicationId: string) => queueApi.cancelApply(applicationId),
    onSuccess: () => {
      toast.success('Cancelled.');
      queryClient.invalidateQueries({ queryKey: ['queue-status'] });
    },
    onError: (error: Error) => {
      toast.error(error.message || 'Failed to cancel');
    },
  });
};

// Targets the queue's currently-running/waiting-for-user application only
// (QueueControls' global bar) — kept alongside the per-row mutations above,
// which target an explicit application id instead.
export const usePauseQueueMutation = () => {
  const queryClient = useQueryClient();
  const queueState = useQueueStore((state) => state.queueState);

  return useMutation({
    mutationFn: async () => {
      const applicationId = queueState?.currentJobId;
      if (!applicationId) throw new Error('No running application to pause');
      return queueApi.pauseApply(applicationId);
    },
    onSuccess: () => {
      toast.success('Paused. Resume when you\'re ready to continue.');
      queryClient.invalidateQueries({ queryKey: ['queue-status'] });
    },
    onError: (error: Error) => {
      toast.error(error.message || 'Failed to pause');
    },
  });
};

export const useResumeQueueMutation = () => {
  const queryClient = useQueryClient();
  const queueState = useQueueStore((state) => state.queueState);

  return useMutation({
    mutationFn: async () => {
      const applicationId = queueState?.currentJobId;
      if (!applicationId) throw new Error('No paused application to resume');
      return queueApi.resumeApply(applicationId);
    },
    onSuccess: () => {
      toast.success('Resumed.');
      queryClient.invalidateQueries({ queryKey: ['queue-status'] });
    },
    onError: (error: Error) => {
      toast.error(error.message || 'Failed to resume');
    },
  });
};

export const useCancelQueueMutation = () => {
  const queryClient = useQueryClient();
  const queueState = useQueueStore((state) => state.queueState);

  return useMutation({
    mutationFn: async () => {
      const applicationId = queueState?.currentJobId;
      if (!applicationId) throw new Error('No running application to cancel');
      return queueApi.cancelApply(applicationId);
    },
    onSuccess: () => {
      toast.success('Cancelled.');
      queryClient.invalidateQueries({ queryKey: ['queue-status'] });
    },
    onError: (error: Error) => {
      toast.error(error.message || 'Failed to cancel');
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