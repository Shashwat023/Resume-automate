import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { ReactQueryDevtools } from '@tanstack/react-query-devtools';
import { RouterProvider } from 'react-router';
import { Toaster } from 'sonner';
import { router } from './app/router';
import { isNotFound } from './api/axios';
import './index.css';

// Production ready QueryClient
const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      refetchOnWindowFocus: false,
      // A 404 is an answer, not a transient failure. `GET /api/resume/{id}`
      // returning 404 is simply "no resume uploaded yet", but blanket
      // retrying meant three requests with backoff before the upload
      // dropzone appeared — a ~9s spinner for every new user
      // (FLAGGED.md #34.3). Retry genuinely transient failures only.
      retry: (failureCount, error) =>
        !isNotFound(error) && failureCount < 2,
      staleTime: 5 * 60 * 1000, // 5 minutes
    },
    mutations: {
      retry: 1,
    }
  },
});

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <QueryClientProvider client={queryClient}>
      <RouterProvider router={router} />
      <Toaster />
      <ReactQueryDevtools initialIsOpen={false} />
    </QueryClientProvider>
  </StrictMode>,
);
