import { RefreshCw, Download, X } from 'lucide-react';
import { useQueryClient } from '@tanstack/react-query';

interface TableToolbarProps {
  selectedCount: number;
  onClearSelection: () => void;
  isLoading?: boolean;
}

export const TableToolbar = ({ selectedCount, onClearSelection, isLoading }: TableToolbarProps) => {
  const queryClient = useQueryClient();

  const handleRefresh = () => {
    queryClient.invalidateQueries({ queryKey: ['jobs', 'search'] });
  };

  const handleExport = () => {
    // Placeholder for CSV export
    alert('Export CSV functionality will be implemented here.');
  };

  return (
    <div className="flex flex-col sm:flex-row items-center justify-between py-4 gap-4">
      <div className="flex items-center gap-4">
        {selectedCount > 0 ? (
          <div className="flex items-center gap-3">
            <span className="text-sm font-medium text-indigo-600 dark:text-indigo-400 bg-indigo-50 dark:bg-indigo-900/30 px-3 py-1 rounded-full">
              {selectedCount} selected
            </span>
            <button
              onClick={onClearSelection}
              className="text-sm text-gray-500 hover:text-gray-700 dark:text-gray-400 dark:hover:text-gray-200 flex items-center gap-1 transition-colors"
            >
              <X className="w-4 h-4" /> Clear
            </button>
          </div>
        ) : (
          <span className="text-sm text-gray-500 dark:text-gray-400">
            Select jobs to auto apply
          </span>
        )}
      </div>

      <div className="flex items-center gap-2 w-full sm:w-auto">
        <button
          onClick={handleRefresh}
          disabled={isLoading}
          className="flex-1 sm:flex-none flex items-center justify-center gap-2 px-3 py-1.5 border border-gray-300 dark:border-gray-700 rounded-md text-sm font-medium text-gray-700 dark:text-gray-200 bg-white dark:bg-gray-800 hover:bg-gray-50 dark:hover:bg-gray-700 transition-colors disabled:opacity-50"
        >
          <RefreshCw className={`w-4 h-4 ${isLoading ? 'animate-spin' : ''}`} />
          <span className="hidden sm:inline">Refresh</span>
        </button>
        <button
          onClick={handleExport}
          className="flex-1 sm:flex-none flex items-center justify-center gap-2 px-3 py-1.5 border border-gray-300 dark:border-gray-700 rounded-md text-sm font-medium text-gray-700 dark:text-gray-200 bg-white dark:bg-gray-800 hover:bg-gray-50 dark:hover:bg-gray-700 transition-colors"
        >
          <Download className="w-4 h-4" />
          <span className="hidden sm:inline">Export</span>
        </button>
      </div>
    </div>
  );
};
