import { useState } from 'react';
import type { Job } from '@/types';
import type { useCreateQueueMutation } from '../services/search.queries';

export const QUICK_SELECT_OPTIONS = [10, 50, 100] as const;

interface UseQueueConfirmationArgs {
  jobs: Job[];
  rowSelection: Record<string, boolean>;
  selectedCount: number;
  totalItems: number;
  createQueue: ReturnType<typeof useCreateQueueMutation>['mutate'];
  clearSelection: () => void;
  setSelectedRowIds: (selection: Record<string, boolean>) => void;
}

/**
 * Extracted from pages/SearchPage.tsx as part of the clean-architecture
 * restructure — quick-select and queue-confirmation logic, copied verbatim.
 */
export function useQueueConfirmation({
  jobs,
  rowSelection,
  selectedCount,
  totalItems,
  createQueue,
  clearSelection,
  setSelectedRowIds,
}: UseQueueConfirmationArgs) {
  const [isConfirmOpen, setIsConfirmOpen] = useState(false);
  const [queueMode, setQueueMode] = useState<'selected' | 'filtered'>('selected');
  const [quickSelectN, setQuickSelectN] = useState<number | null>(null);

  // Selects the top N jobs from the current results into rowSelection
  const handleQuickSelect = (n: number) => {
    setQuickSelectN(n);
    const topN = jobs.slice(0, n);
    const newSelection: Record<string, boolean> = {};
    topN.forEach(job => { newSelection[String(job.id)] = true; });
    setSelectedRowIds(newSelection);
    // Scroll to top of table so user sees the selected rows
    window.scrollTo({ top: 0, behavior: 'smooth' });
  };

  const handleAutoApplySelected = () => {
    setQueueMode('selected');
    setIsConfirmOpen(true);
  };

  const handleAutoApplyFiltered = () => {
    setQueueMode('filtered');
    setIsConfirmOpen(true);
  };

  const handleConfirmQueue = () => {
    let jobsToQueue: typeof jobs = [];

    if (queueMode === 'selected') {
      jobsToQueue = jobs.filter(job => rowSelection[job.id]);
    } else {
      jobsToQueue = jobs;
    }

    createQueue(
      { jobs: jobsToQueue.map(j => ({ id: j.id, title: j.title, company_name: j.company_name, apply_url: j.apply_url })) },
      {
        onSuccess: () => {
          setIsConfirmOpen(false);
          setQuickSelectN(null);
          clearSelection();
        }
      }
    );
  };

  const queueCount = queueMode === 'selected' ? selectedCount : totalItems;

  return {
    isConfirmOpen,
    setIsConfirmOpen,
    quickSelectN,
    setQuickSelectN,
    handleQuickSelect,
    handleAutoApplySelected,
    handleAutoApplyFiltered,
    handleConfirmQueue,
    queueCount,
  };
}
