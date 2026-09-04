import { useQueueStatusQuery } from '../features/queue/services/queue.queries';
import { QueueSummary } from '../features/queue/components/QueueSummary';
import { QueueTable } from '../features/queue/components/QueueTable';
import { QueueControls } from '../features/queue/components/QueueControls';
import { CurrentJobCard } from '../features/queue/components/CurrentJobCard';
import { TimelineCard } from '../features/queue/components/TimelineCard';
import { LogViewer } from '../features/queue/components/LogViewer';
import { useQueueStore } from '../store/queueStore';

export const QueuePage = () => {
  // Mount polling query
  const { isLoading, error } = useQueueStatusQuery();
  const queueState = useQueueStore(state => state.queueState);

  if (isLoading && !queueState) {
    return (
      <div className="h-full flex items-center justify-center">
        <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-indigo-600"></div>
      </div>
    );
  }

  if (error && !queueState) {
    return (
      <div className="h-full flex flex-col items-center justify-center text-red-500">
        <p>Failed to connect to backend queue service.</p>
        <p className="text-sm text-gray-500 mt-2">Retrying automatically...</p>
      </div>
    );
  }

  // queueState.status is a coarse AGGREGATE across the whole queue and
  // does not move for a single job stuck at needs_input (2FA) or paused —
  // e.g. 3 failed + 2 needs_input jobs computes to aggregate 'idle', which
  // would hide CurrentJobCard (and its Take Control button) at exactly the
  // moment a real, specific job needs it. currentJobId is per-job and
  // already correctly includes waiting_for_user (see api/queue.ts), so it
  // catches this case; the aggregate checks stay as an additional signal,
  // not the only one.
  const hasActiveJob =
    !!queueState?.currentJobId ||
    queueState?.status === 'running' ||
    queueState?.status === 'paused';

  return (
    <div className="max-w-7xl mx-auto h-full flex flex-col space-y-6 pb-6">
      
      {/* Top Header & Controls */}
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold text-gray-900 dark:text-gray-100">Queue Management</h1>
          <p className="text-sm text-gray-500 dark:text-gray-400 mt-1">
            Monitor and control automated job applications in real-time.
          </p>
        </div>
        
        <QueueControls />
      </div>

      {/* Summary Cards */}
      <QueueSummary />

      {/* Main Content Split Layout */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6 flex-1 min-h-[600px]">
        
        {/* Left Side: Table */}
        <div className="lg:col-span-2 flex flex-col h-full overflow-hidden">
          <QueueTable />
        </div>

        {/* Right Side: Active Panel */}
        <div className="lg:col-span-1 flex flex-col space-y-6 h-full">
          {hasActiveJob && (
            <>
              <CurrentJobCard />
              <TimelineCard />
            </>
          )}
          
          <div className={`flex-1 ${!hasActiveJob ? 'h-full' : ''}`}>
            <LogViewer />
          </div>
        </div>

      </div>
    </div>
  );
};
