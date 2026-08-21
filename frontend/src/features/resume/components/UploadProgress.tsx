import { motion } from 'framer-motion';
import { XCircle, RefreshCw, FileText } from 'lucide-react';

interface UploadProgressProps {
  fileName: string;
  progress: number;
  onCancel: () => void;
  onRetry: () => void;
  isError: boolean;
}

export const UploadProgress = ({ fileName, progress, onCancel, onRetry, isError }: UploadProgressProps) => {
  return (
    <motion.div 
      initial={{ opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      className="bg-white dark:bg-gray-800 rounded-xl border border-gray-200 dark:border-gray-700 p-6 shadow-sm"
    >
      <div className="flex items-center justify-between mb-4">
        <div className="flex items-center gap-3">
          <div className="p-2 bg-indigo-50 dark:bg-indigo-900/20 rounded-lg text-indigo-600 dark:text-indigo-400">
            <FileText className="w-6 h-6" />
          </div>
          <div>
            <h4 className="text-sm font-medium text-gray-900 dark:text-gray-100 line-clamp-1">{fileName}</h4>
            <p className="text-xs text-gray-500 dark:text-gray-400 mt-0.5">
              {isError ? 'Upload failed' : progress === 100 ? 'Processing...' : 'Uploading...'}
            </p>
          </div>
        </div>
        <div>
          {isError ? (
            <button
              onClick={onRetry}
              className="text-xs flex items-center gap-1 font-medium text-indigo-600 dark:text-indigo-400 hover:text-indigo-700 bg-indigo-50 dark:bg-indigo-900/30 px-2 py-1 rounded"
            >
              <RefreshCw className="w-3 h-3" /> Retry
            </button>
          ) : (
            <button
              onClick={onCancel}
              className="text-gray-400 hover:text-gray-600 dark:hover:text-gray-200 transition-colors"
            >
              <XCircle className="w-5 h-5" />
            </button>
          )}
        </div>
      </div>

      <div className="relative h-2 w-full bg-gray-100 dark:bg-gray-700 rounded-full overflow-hidden">
        <motion.div 
          className={`absolute top-0 left-0 h-full rounded-full ${isError ? 'bg-red-500' : 'bg-indigo-600 dark:bg-indigo-500'}`}
          initial={{ width: 0 }}
          animate={{ width: `${progress}%` }}
          transition={{ duration: 0.2 }}
        />
      </div>
      <div className="mt-2 text-right">
        <span className={`text-xs font-semibold ${isError ? 'text-red-500' : 'text-indigo-600 dark:text-indigo-400'}`}>
          {progress}%
        </span>
      </div>
    </motion.div>
  );
};
