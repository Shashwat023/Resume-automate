import { useQueueStore } from '../../../store/queueStore';
import { QueueStatusBadge } from './QueueStatusBadge';
import { FileText, UserCircle, ExternalLink } from 'lucide-react';

export const CurrentJobCard = () => {
  const queueState = useQueueStore((state) => state.queueState);
  
  if (!queueState || !queueState.currentJobId) return null;

  const currentJob = queueState.items.find(i => i.id === queueState.currentJobId || i.jobId === queueState.currentJobId);

  if (!currentJob) return null;

  return (
    <div className="bg-white dark:bg-gray-800 rounded-xl p-5 border border-indigo-200 dark:border-indigo-900 shadow-sm shadow-indigo-100 dark:shadow-none">
      <div className="flex items-center justify-between mb-4">
        <h3 className="text-sm font-semibold text-indigo-600 dark:text-indigo-400 flex items-center gap-2">
          <span className="relative flex h-2.5 w-2.5">
            <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-indigo-400 opacity-75"></span>
            <span className="relative inline-flex rounded-full h-2.5 w-2.5 bg-indigo-500"></span>
          </span>
          Currently Processing
        </h3>
        <QueueStatusBadge status={currentJob.status} />
      </div>

      <div className="flex gap-4">
        <div className="w-12 h-12 rounded-lg bg-gray-100 dark:bg-gray-700 flex flex-col items-center justify-center shrink-0 border border-gray-200 dark:border-gray-600">
          <span className="text-lg font-bold text-gray-600 dark:text-gray-300">{currentJob.company.charAt(0)}</span>
        </div>
        
        <div className="min-w-0 flex-1">
          <h4 className="text-base font-bold text-gray-900 dark:text-white truncate">{currentJob.jobTitle}</h4>
          <p className="text-sm text-gray-500 dark:text-gray-400 truncate">{currentJob.company}</p>
        </div>
      </div>

      <div className="mt-5 pt-5 border-t border-gray-100 dark:border-gray-700">
        <div className="grid grid-cols-2 gap-4">
          <div>
            <p className="text-xs text-gray-500 dark:text-gray-400 mb-1">Elapsed Time</p>
            <p className="text-sm font-medium text-gray-900 dark:text-gray-100">
              {currentJob.duration ? `${currentJob.duration} seconds` : '0 seconds'}
            </p>
          </div>
          <div>
            <p className="text-xs text-gray-500 dark:text-gray-400 mb-1">Target ATS</p>
            <p className="text-sm font-medium text-gray-900 dark:text-gray-100 uppercase">
              {currentJob.ats || 'Unknown'}
            </p>
          </div>
        </div>

        <div className="mt-4 flex flex-wrap gap-2">
          <span className="inline-flex items-center gap-1.5 px-2 py-1 rounded bg-gray-50 dark:bg-gray-700/50 border border-gray-200 dark:border-gray-700 text-xs font-medium text-gray-600 dark:text-gray-300">
            <FileText className="w-3.5 h-3.5" /> Resume linked
          </span>
          <span className="inline-flex items-center gap-1.5 px-2 py-1 rounded bg-gray-50 dark:bg-gray-700/50 border border-gray-200 dark:border-gray-700 text-xs font-medium text-gray-600 dark:text-gray-300">
            <UserCircle className="w-3.5 h-3.5" /> Profile linked
          </span>
        </div>
      </div>
      
      {currentJob.company_url && (
        <a 
          href={currentJob.company_url} 
          target="_blank" 
          rel="noreferrer"
          className="mt-4 flex items-center justify-center gap-2 w-full px-3 py-2 bg-indigo-50 dark:bg-indigo-900/20 text-indigo-600 dark:text-indigo-400 hover:bg-indigo-100 dark:hover:bg-indigo-900/40 transition-colors rounded-lg text-sm font-medium"
        >
          View Target Form <ExternalLink className="w-4 h-4" />
        </a>
      )}
    </div>
  );
};
