import { SearchX } from 'lucide-react';
import { motion } from 'framer-motion';

export const EmptyState = ({ onReset }: { onReset: () => void }) => {
  return (
    <motion.div 
      initial={{ opacity: 0, scale: 0.95 }}
      animate={{ opacity: 1, scale: 1 }}
      className="flex flex-col items-center justify-center py-24 text-center px-4"
    >
      <div className="w-24 h-24 bg-gray-100 dark:bg-gray-800 rounded-full flex items-center justify-center mb-6">
        <SearchX className="w-12 h-12 text-gray-400 dark:text-gray-500" />
      </div>
      <h3 className="text-xl font-semibold text-gray-900 dark:text-gray-100 mb-2">
        No jobs found
      </h3>
      <p className="text-gray-500 dark:text-gray-400 max-w-sm mb-6">
        We couldn't find any jobs matching your current filters. Try adjusting your search or clearing filters.
      </p>
      <button
        onClick={onReset}
        className="px-6 py-2.5 bg-white dark:bg-gray-800 border border-gray-300 dark:border-gray-700 text-gray-700 dark:text-gray-200 rounded-lg text-sm font-medium hover:bg-gray-50 dark:hover:bg-gray-700 transition-colors shadow-sm"
      >
        Clear all filters
      </button>
    </motion.div>
  );
};
