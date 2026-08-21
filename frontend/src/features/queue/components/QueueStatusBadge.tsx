import { clsx } from 'clsx';
import { type JobStatus } from '../../../types';

const statusStyles: Record<JobStatus, string> = {
  waiting: 'bg-gray-100 text-gray-700 dark:bg-gray-800 dark:text-gray-300',
  running: 'bg-blue-100 text-blue-700 dark:bg-blue-900/40 dark:text-blue-400',
  completed: 'bg-emerald-100 text-emerald-700 dark:bg-emerald-900/40 dark:text-emerald-400',
  failed: 'bg-red-100 text-red-700 dark:bg-red-900/40 dark:text-red-400',
  retrying: 'bg-amber-100 text-amber-700 dark:bg-amber-900/40 dark:text-amber-400',
  skipped: 'bg-gray-100 text-gray-500 dark:bg-gray-800 dark:text-gray-400',
  waiting_for_user: 'bg-purple-100 text-purple-700 dark:bg-purple-900/40 dark:text-purple-400',
  cancelled: 'bg-red-100 text-red-700 dark:bg-red-900/40 dark:text-red-400',
};

const statusLabels: Record<JobStatus, string> = {
  waiting: 'Waiting',
  running: 'Running',
  completed: 'Completed',
  failed: 'Failed',
  retrying: 'Retrying',
  skipped: 'Skipped',
  waiting_for_user: 'User Input Required',
  cancelled: 'Cancelled',
};

interface QueueStatusBadgeProps {
  status: JobStatus;
  className?: string;
}

export const QueueStatusBadge = ({ status, className }: QueueStatusBadgeProps) => {
  return (
    <span className={clsx(
      'inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium',
      statusStyles[status],
      className
    )}>
      {status === 'running' && (
        <span className="w-1.5 h-1.5 rounded-full bg-blue-500 mr-1.5 animate-pulse" />
      )}
      {status === 'waiting_for_user' && (
        <span className="w-1.5 h-1.5 rounded-full bg-purple-500 mr-1.5 animate-bounce" />
      )}
      {statusLabels[status]}
    </span>
  );
};
