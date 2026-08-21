import { useQuery } from '@tanstack/react-query';
import api from '@/api/axios';

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
