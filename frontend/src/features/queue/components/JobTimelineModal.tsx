import { useEffect, useState } from 'react';
import { X, History } from 'lucide-react';
import { clsx } from 'clsx';
import { queueApi, type BackendApplyDetails } from '../../../api/queue';

interface JobTimelineModalProps {
  applicationId: string;
  onClose: () => void;
}

/**
 * Day 5: the run_events timeline visible for ANY job, not just the one
 * currently live over the logs WebSocket — LogViewer only has data while
 * a job is queueState.currentJobId, so a completed/failed job's history
 * was otherwise unreachable after the fact. Fetches once (GET
 * /api/apply/details/{id}) — no WS needed, this data doesn't change.
 */
export const JobTimelineModal = ({ applicationId, onClose }: JobTimelineModalProps) => {
  const [details, setDetails] = useState<BackendApplyDetails | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    queueApi
      .getDetails(applicationId)
      .then((data) => {
        if (!cancelled) setDetails(data);
      })
      .catch((err: Error) => {
        if (!cancelled) setError(err.message);
      });
    return () => {
      cancelled = true;
    };
  }, [applicationId]);

  return (
    <div className="fixed inset-0 z-50 bg-black/70 flex items-center justify-center p-4">
      <div className="bg-white dark:bg-gray-900 rounded-xl shadow-2xl w-full max-w-2xl flex flex-col max-h-[85vh]">
        <div className="flex items-center justify-between px-4 py-3 border-b border-gray-200 dark:border-gray-700 shrink-0">
          <div className="flex items-center gap-2">
            <History className="w-4 h-4 text-gray-400" />
            <h3 className="text-sm font-semibold text-gray-900 dark:text-white">
              Run Timeline {details ? `— ${details.job.title ?? ''} @ ${details.job.company_name ?? ''}` : ''}
            </h3>
          </div>
          <button
            onClick={onClose}
            className="text-gray-400 hover:text-gray-600 dark:hover:text-gray-200"
            aria-label="Close timeline"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        <div className="flex-1 overflow-y-auto p-4 font-mono text-xs sm:text-sm">
          {error && <p className="text-red-500">{error}</p>}
          {!details && !error && <p className="text-gray-400">Loading...</p>}
          {details && details.events.length === 0 && (
            <p className="text-gray-400 italic">No events recorded for this application yet.</p>
          )}
          {details?.events.map((event) => (
            <div key={event.id} className="mb-1.5 flex gap-3 break-words">
              <span className="text-gray-400 shrink-0 select-none">
                {event.created_at.split('T')[1]?.substring(0, 8) ?? event.created_at}
              </span>
              {event.tier && (
                <span className="text-gray-400 shrink-0 select-none">[{event.tier}]</span>
              )}
              <span
                className={clsx(
                  'flex-1',
                  event.level === 'error'
                    ? 'text-red-500'
                    : event.level === 'warn'
                      ? 'text-amber-500'
                      : 'text-gray-700 dark:text-gray-300'
                )}
              >
                {event.message}
              </span>
            </div>
          ))}
        </div>

        {details?.error && (
          <div className="px-4 py-3 border-t border-gray-200 dark:border-gray-700 text-xs text-red-500 shrink-0">
            Error: {details.error}
          </div>
        )}
      </div>
    </div>
  );
};
