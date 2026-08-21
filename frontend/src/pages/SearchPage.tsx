import { SearchHeader } from '../features/search/components/SearchHeader';
import { SearchBar } from '../features/search/components/SearchBar';
import { FilterPanel } from '../features/search/components/FilterPanel';
import { JobTable } from '../features/search/components/JobTable';
import { TableToolbar } from '../features/search/components/TableToolbar';
import { Pagination } from '../features/search/components/Pagination';
import { EmptyState } from '../features/search/components/EmptyState';
import { LoadingState } from '../features/search/components/LoadingState';
import { ConfirmQueueDialog } from '../features/search/components/ConfirmQueueDialog';

import { useJobSearch } from '../features/search/hooks/useJobSearch';
import { useFilters } from '../features/search/hooks/useFilters';
import { usePagination } from '../features/search/hooks/usePagination';
import { useRowSelection } from '../features/search/hooks/useRowSelection';
import { useSearchJobsQuery, useCreateQueueMutation } from '../features/search/services/search.queries';
import {
  useQueueConfirmation,
  QUICK_SELECT_OPTIONS,
} from '@/features/search/hooks/useQueueConfirmation';
import { useDebounce } from '../hooks/useDebounce';
import { Play, ListChecks } from 'lucide-react';

export const SearchPage = () => {
  const { keyword } = useJobSearch();
  const { filters, resetFilters } = useFilters();
  const { page, limit } = usePagination();
  const { rowSelection, onRowSelectionChange, clearSelection, setSelectedRowIds } = useRowSelection();

  const debouncedKeyword = useDebounce(keyword, 500);

  const { data: response, isLoading, isError, refetch } = useSearchJobsQuery({
    keyword: debouncedKeyword,
    filters,
    page,
    limit,
  });

  const { mutate: createQueue, isPending: isCreatingQueue } = useCreateQueueMutation();

  const jobs = response?.data || [];
  const meta = response?.meta || { totalItems: 0, totalPages: 0, page: 1, limit: 10 };
  const selectedCount = Object.keys(rowSelection).filter(k => rowSelection[k]).length;

  const {
    isConfirmOpen,
    setIsConfirmOpen,
    quickSelectN,
    setQuickSelectN,
    handleQuickSelect,
    handleAutoApplySelected,
    handleAutoApplyFiltered,
    handleConfirmQueue,
    queueCount,
  } = useQueueConfirmation({
    jobs,
    rowSelection,
    selectedCount,
    totalItems: meta.totalItems,
    createQueue,
    clearSelection,
    setSelectedRowIds,
  });

  return (
    <div className="flex flex-col h-full max-w-7xl mx-auto space-y-2">
      <SearchHeader />

      <SearchBar />
      <FilterPanel />

      <div className="flex-1 flex flex-col space-y-4">
        <TableToolbar
          selectedCount={selectedCount}
          onClearSelection={() => { clearSelection(); setQuickSelectN(null); }}
          isLoading={isLoading}
        />

        <div className="flex-1 min-h-[400px]">
          {isLoading && !jobs.length ? (
            <LoadingState />
          ) : isError ? (
            <div className="p-8 text-center text-red-500 border rounded-xl border-red-200 bg-red-50 dark:bg-red-900/10 dark:border-red-900/30">
              <p className="mb-4">Failed to load jobs. Please try again.</p>
              <button
                onClick={() => refetch()}
                className="px-4 py-2 bg-white dark:bg-gray-800 border border-red-300 dark:border-red-800 rounded-md text-red-600 dark:text-red-400 hover:bg-red-50 dark:hover:bg-red-900/20"
              >
                Retry
              </button>
            </div>
          ) : jobs.length === 0 ? (
            <EmptyState onReset={resetFilters} />
          ) : (
            <>
              <JobTable
                data={jobs}
                rowSelection={rowSelection}
                onRowSelectionChange={onRowSelectionChange}
              />
              <Pagination totalItems={meta.totalItems} totalPages={meta.totalPages} />
            </>
          )}
        </div>
      </div>

      {/* Auto Apply Action Bar */}
      <div className="sticky bottom-0 mt-8 py-4 bg-white/80 dark:bg-gray-950/80 backdrop-blur-md border-t border-gray-200 dark:border-gray-800 flex flex-col sm:flex-row items-center justify-end gap-3 z-20">

        {/* Quick Select Top N */}
        {jobs.length > 0 && (
          <div className="flex items-center gap-2">
            <ListChecks className="w-4 h-4 text-gray-500 dark:text-gray-400" />
            <span className="text-sm text-gray-500 dark:text-gray-400 whitespace-nowrap">
              Quick select:
            </span>
            <div className="flex gap-1">
              {QUICK_SELECT_OPTIONS.map(n => {
                const available = Math.min(n, jobs.length);
                const isActive = quickSelectN === n;
                return (
                  <button
                    key={n}
                    onClick={() => handleQuickSelect(n)}
                    disabled={jobs.length === 0}
                    title={`Select top ${available} jobs`}
                    className={`px-3 py-1.5 rounded-md text-xs font-semibold border transition-colors
                      ${isActive
                        ? 'bg-indigo-600 text-white border-indigo-600'
                        : 'bg-white dark:bg-gray-800 text-gray-700 dark:text-gray-300 border-gray-300 dark:border-gray-600 hover:border-indigo-400 hover:text-indigo-600 dark:hover:text-indigo-400'
                      }
                      disabled:opacity-40 disabled:cursor-not-allowed`}
                  >
                    Top {Math.min(n, jobs.length)}
                  </button>
                );
              })}
            </div>
          </div>
        )}

        <div className="flex items-center gap-3 ml-4">
          <button
            onClick={handleAutoApplyFiltered}
            disabled={jobs.length === 0 || isLoading}
            className="w-full sm:w-auto px-6 py-2.5 border border-indigo-200 dark:border-indigo-800 text-indigo-700 dark:text-indigo-400 bg-indigo-50 dark:bg-indigo-900/20 hover:bg-indigo-100 dark:hover:bg-indigo-900/40 rounded-lg text-sm font-semibold transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
          >
            Auto Apply All Filtered
          </button>
          <button
            onClick={handleAutoApplySelected}
            disabled={selectedCount === 0 || isLoading}
            className="w-full sm:w-auto flex items-center justify-center gap-2 px-6 py-2.5 bg-indigo-600 hover:bg-indigo-700 text-white rounded-lg text-sm font-semibold shadow-sm transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
          >
            <Play className="w-4 h-4 fill-current" />
            Auto Apply Selected ({selectedCount})
          </button>
        </div>
      </div>

      <ConfirmQueueDialog
        isOpen={isConfirmOpen}
        onClose={() => setIsConfirmOpen(false)}
        onConfirm={handleConfirmQueue}
        jobCount={queueCount}
        isPending={isCreatingQueue}
      />
    </div>
  );
};