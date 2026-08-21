import { motion } from 'framer-motion';

export const LoadingState = () => {
  return (
    <div className="space-y-4">
      {/* Table Header Skeleton */}
      <div className="h-12 bg-gray-100 dark:bg-gray-800/50 rounded-t-xl w-full border border-gray-200 dark:border-gray-800" />
      
      {/* Rows Skeleton */}
      <div className="space-y-3 px-4">
        {[1, 2, 3, 4, 5].map((i) => (
          <motion.div
            key={i}
            initial={{ opacity: 0, y: 10 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: i * 0.05 }}
            className="flex items-center gap-6 h-16 w-full"
          >
            <div className="w-4 h-4 rounded bg-gray-200 dark:bg-gray-700 shrink-0 animate-pulse" />
            <div className="flex-1 space-y-2">
              <div className="h-4 bg-gray-200 dark:bg-gray-700 rounded w-1/3 animate-pulse" />
              <div className="h-3 bg-gray-100 dark:bg-gray-800 rounded w-1/4 animate-pulse" />
            </div>
            <div className="hidden md:block w-32 h-4 bg-gray-200 dark:bg-gray-700 rounded animate-pulse" />
            <div className="hidden lg:block w-24 h-4 bg-gray-200 dark:bg-gray-700 rounded animate-pulse" />
            <div className="hidden xl:block w-24 h-4 bg-gray-200 dark:bg-gray-700 rounded animate-pulse" />
            <div className="w-8 h-8 rounded-full bg-gray-200 dark:bg-gray-700 shrink-0 animate-pulse" />
          </motion.div>
        ))}
      </div>
    </div>
  );
};
