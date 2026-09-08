import type { AxiosProgressEvent } from 'axios';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { resumeApi } from '../../../api/resume';
import { useResumeStore } from '../../../store/resumeStore';
import { getStoredProfileId } from '@/lib/session';
import { toast } from 'sonner';

export const useGetResumeQuery = () => {
  const setActiveResume = useResumeStore((state) => state.setActiveResume);
  const profileId = getStoredProfileId();

  return useQuery({
    queryKey: ['resume', profileId],
    queryFn: async () => {
      if (!profileId) return null;
      const data = await resumeApi.getResume(profileId);
      if (data) setActiveResume(data as any);
      return data;
    },
    enabled: !!profileId,
    staleTime: 5 * 60 * 1000,
  });
};

export const useUploadResumeMutation = () => {
  const queryClient = useQueryClient();
  const setActiveResume = useResumeStore((state) => state.setActiveResume);

  return useMutation({
    mutationFn: ({
      file,
      onUploadProgress,
      signal,
    }: {
      file: File;
      onUploadProgress?: (progressEvent: AxiosProgressEvent) => void;
      signal?: AbortSignal;
    }) => {
      const profileId = getStoredProfileId();
      if (!profileId) {
        throw new Error('Please save your profile first before uploading a resume.');
      }
      return resumeApi.uploadResume(profileId, file, onUploadProgress, signal);
    },
    onSuccess: (data) => {
      setActiveResume(data as any);
      queryClient.invalidateQueries({ queryKey: ['resume'] });
      toast.success('Resume uploaded successfully!');
    },
    onError: (error: any) => {
      if (error?.message !== 'canceled') {
        toast.error(error?.message || 'Failed to upload resume');
      }
    },
  });
};

export const useDeleteResumeMutation = () => {
  const queryClient = useQueryClient();
  const clearResume = useResumeStore((state) => state.clearResume);

  return useMutation({
    mutationFn: () => {
      const profileId = getStoredProfileId();
      if (!profileId) throw new Error('No profile found');
      return resumeApi.deleteResume(profileId);
    },
    onSuccess: () => {
      clearResume();
      queryClient.invalidateQueries({ queryKey: ['resume'] });
      toast.success('Resume deleted successfully');
    },
    onError: (error: any) => {
      toast.error(error?.message || 'Failed to delete resume');
    },
  });
};