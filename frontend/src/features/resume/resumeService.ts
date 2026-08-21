/**
 * React-Query hooks for resume upload / fetch / delete.
 * All routes require a profile_id integer.
 */
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { resumeApi } from '../../api/resume';
import { toast } from 'sonner';

export const useResumeQuery = (profileId: number | null) =>
  useQuery({
    queryKey: ['resume', profileId],
    queryFn: () => {
      if (!profileId) throw new Error('No profile ID');
      return resumeApi.getResume(profileId);
    },
    enabled: !!profileId,
    staleTime: 10 * 60 * 1000,
  });

export const useUploadResumeMutation = (profileId: number | null) => {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({
      file,
      onProgress,
      signal,
    }: {
      file: File;
      onProgress?: (e: ProgressEvent) => void;
      signal?: AbortSignal;
    }) => {
      if (!profileId) throw new Error('No profile ID');
      return resumeApi.uploadResume(profileId, file, onProgress, signal);
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['resume', profileId] });
      toast.success('Resume uploaded!');
    },
    onError: (err: Error) => toast.error(err.message),
  });
};

export const useDeleteResumeMutation = (profileId: number | null) => {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: () => {
      if (!profileId) throw new Error('No profile ID');
      return resumeApi.deleteResume(profileId);
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['resume', profileId] });
      toast.success('Resume deleted.');
    },
    onError: (err: Error) => toast.error(err.message),
  });
};
