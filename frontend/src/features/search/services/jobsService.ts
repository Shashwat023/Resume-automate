// /**
//  * React-Query hooks for job search — GET /api/jobs/search
//  */
// import { useQuery } from '@tanstack/react-query';
// import { jobsApi, type JobSearchParams } from '../../../api/jobs';

// export const useJobSearchQuery = (params: JobSearchParams, enabled = true) =>
//   useQuery({
//     queryKey: ['jobs', params],
//     queryFn: () => jobsApi.searchJobs(params),
//     enabled,
//     staleTime: 2 * 60 * 1000,
//     placeholderData: (prev) => prev, // keep previous page data during page transition
//   });
