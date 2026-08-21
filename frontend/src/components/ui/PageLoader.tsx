import { Loader2 } from 'lucide-react';

export const PageLoader = () => {
  return (
    <div className="flex-1 flex flex-col items-center justify-center min-h-[60vh]">
      <Loader2 className="w-8 h-8 text-indigo-600 animate-spin mb-4" />
      <p className="text-gray-500 dark:text-gray-400 font-medium animate-pulse">Loading module...</p>
    </div>
  );
};
