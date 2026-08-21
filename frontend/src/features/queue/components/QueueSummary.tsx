import { useQueueStore } from '../../../store/queueStore';
import { motion } from 'framer-motion';
import { PlayCircle, CheckCircle2, Clock, Zap, AlertTriangle, AlertCircle } from 'lucide-react';
import { clsx } from 'clsx';
import type { ReactNode } from 'react';
import { type QueueStatus } from '../../../types';

const statusIcons: Record<QueueStatus, ReactNode> = {
  idle: <Clock className="w-5 h-5" />,
  running: <PlayCircle className="w-5 h-5 text-blue-500" />,
  paused: <Clock className="w-5 h-5 text-amber-500" />,
  completed: <CheckCircle2 className="w-5 h-5 text-emerald-500" />,
  failed: <AlertTriangle className="w-5 h-5 text-red-500" />,
  cancelled: <AlertCircle className="w-5 h-5 text-red-500" />
};

export const QueueSummary = () => {
  const queueState = useQueueStore((state) => state.queueState);
  
  if (!queueState) return null;

  const { status, progress, stats, items } = queueState;
  
  const waitingCount = items.filter(i => i.status === 'waiting').length;
  const runningCount = items.filter(i => i.status === 'running').length;
  const completedCount = items.filter(i => i.status === 'completed').length;
  const failedCount = items.filter(i => i.status === 'failed').length;

  return (
    <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
      {/* Status Card */}
      <div className="bg-white dark:bg-gray-800 rounded-xl p-5 border border-gray-200 dark:border-gray-700">
        <div className="flex items-center justify-between mb-4">
          <h3 className="text-sm font-medium text-gray-500 dark:text-gray-400">Queue Status</h3>
          {statusIcons[status]}
        </div>
        <p className="text-2xl font-bold text-gray-900 dark:text-gray-100 capitalize">
          {status}
        </p>
        <p className="text-sm text-gray-500 dark:text-gray-400 mt-1">
          {runningCount > 0 ? `${runningCount} job(s) running` : 'No active jobs'}
        </p>
      </div>

      {/* Jobs Breakdown Card */}
      <div className="bg-white dark:bg-gray-800 rounded-xl p-5 border border-gray-200 dark:border-gray-700">
        <div className="flex items-center justify-between mb-4">
          <h3 className="text-sm font-medium text-gray-500 dark:text-gray-400">Total Jobs</h3>
          <span className="text-2xl font-bold text-gray-900 dark:text-gray-100">{progress.total}</span>
        </div>
        <div className="grid grid-cols-3 gap-2 text-center text-xs">
          <div className="bg-gray-50 dark:bg-gray-900/50 p-2 rounded-lg">
            <div className="font-semibold text-gray-700 dark:text-gray-300">{waitingCount}</div>
            <div className="text-gray-500">Wait</div>
          </div>
          <div className="bg-emerald-50 dark:bg-emerald-900/20 p-2 rounded-lg">
            <div className="font-semibold text-emerald-700 dark:text-emerald-400">{completedCount}</div>
            <div className="text-emerald-600">Done</div>
          </div>
          <div className="bg-red-50 dark:bg-red-900/20 p-2 rounded-lg">
            <div className="font-semibold text-red-700 dark:text-red-400">{failedCount}</div>
            <div className="text-red-600">Fail</div>
          </div>
        </div>
      </div>

      {/* Progress Ring Card */}
      <div className="bg-white dark:bg-gray-800 rounded-xl p-5 border border-gray-200 dark:border-gray-700">
        <div className="flex items-center justify-between mb-4">
          <h3 className="text-sm font-medium text-gray-500 dark:text-gray-400">Overall Progress</h3>
          <span className="text-sm font-medium text-indigo-600 dark:text-indigo-400">
            ETA {Math.round(progress.eta / 60)} min
          </span>
        </div>
        
        <div className="flex items-center gap-4">
          <div className="relative w-16 h-16 shrink-0">
            <svg className="w-16 h-16 transform -rotate-90">
              <circle cx="32" cy="32" r="28" stroke="currentColor" strokeWidth="6" fill="transparent" className="text-gray-100 dark:text-gray-700" />
              <motion.circle
                cx="32" cy="32" r="28" stroke="currentColor" strokeWidth="6" fill="transparent"
                strokeDasharray="175"
                initial={{ strokeDashoffset: 175 }}
                animate={{ strokeDashoffset: 175 - (175 * progress.percentage) / 100 }}
                transition={{ duration: 1, ease: 'easeOut' }}
                className={clsx("transition-all duration-1000 ease-out", 
                  progress.percentage === 100 ? "text-emerald-500" : "text-indigo-600"
                )}
              />
            </svg>
            <div className="absolute inset-0 flex items-center justify-center text-sm font-bold text-gray-900 dark:text-white">
              {progress.percentage}%
            </div>
          </div>
          <div>
            <p className="text-sm font-medium text-gray-900 dark:text-gray-100">{progress.completed} / {progress.total} done</p>
            <p className="text-xs text-gray-500 dark:text-gray-400 mt-1">{progress.total - progress.completed} remaining</p>
          </div>
        </div>
      </div>

      {/* Speed Stats Card */}
      <div className="bg-white dark:bg-gray-800 rounded-xl p-5 border border-gray-200 dark:border-gray-700">
        <div className="flex items-center justify-between mb-4">
          <h3 className="text-sm font-medium text-gray-500 dark:text-gray-400">Execution Speed</h3>
          <Zap className="w-5 h-5 text-indigo-500" />
        </div>
        <p className="text-2xl font-bold text-gray-900 dark:text-gray-100">
          ~{Math.round(stats.averageTime)}s
          <span className="text-sm font-normal text-gray-500 ml-2">avg / job</span>
        </p>
        <div className="flex gap-4 mt-2 text-xs">
          <div className="text-gray-500">Fastest: <span className="font-medium text-gray-900 dark:text-gray-200">{stats.fastestTime}s</span></div>
          <div className="text-gray-500">Slowest: <span className="font-medium text-gray-900 dark:text-gray-200">{stats.slowestTime}s</span></div>
        </div>
      </div>
    </div>
  );
};
