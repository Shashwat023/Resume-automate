import { Play, Pause, XCircle, Download } from 'lucide-react';
import { 
  usePauseQueueMutation, 
  useResumeQueueMutation, 
  useCancelQueueMutation 
} from '../services/queue.queries';
import { useQueueStore } from '../../../store/queueStore';

export const QueueControls = () => {
  const queueState = useQueueStore((state) => state.queueState);
  const pauseMutation = usePauseQueueMutation();
  const resumeMutation = useResumeQueueMutation();
  const cancelMutation = useCancelQueueMutation();

  const status = queueState?.status || 'idle';
  const currentJob = queueState?.items.find((i) => i.id === queueState.currentJobId);
  // needs_input (2FA) must never be resumed blindly from here — resuming
  // without actually completing 2FA in the live view just re-hits the same
  // prompt. CurrentJobCard's "Take Control" button is the only correct
  // entry point for that case; this button stays disabled until then.
  const needsInput = currentJob?.status === 'waiting_for_user';

  const handleExport = () => {
    if (!queueState?.items) return;
    
    // Simple CSV Export logic
    const header = ['Company', 'Job Title', 'Status', 'Duration (s)', 'Error'];
    const rows = queueState.items.map(item => [
      item.company,
      item.jobTitle,
      item.status,
      item.duration || 0,
      item.error || 'N/A'
    ]);
    
    const csvContent = [header, ...rows]
      .map(e => e.join(","))
      .join("\n");
      
    const blob = new Blob([csvContent], { type: 'text/csv;charset=utf-8;' });
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.setAttribute("href", url);
    link.setAttribute("download", "queue_report.csv");
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
  };

  return (
    <div className="flex flex-wrap items-center gap-3">
      {status === 'running' ? (
        <button
          onClick={() => pauseMutation.mutate()}
          disabled={pauseMutation.isPending}
          className="flex items-center gap-2 px-4 py-2 bg-amber-100 text-amber-700 dark:bg-amber-900/30 dark:text-amber-400 rounded-lg font-medium text-sm hover:bg-amber-200 dark:hover:bg-amber-900/50 transition-colors disabled:opacity-50"
        >
          <Pause className="w-4 h-4" /> Pause Queue
        </button>
      ) : (
        <button
          onClick={() => resumeMutation.mutate()}
          disabled={
            resumeMutation.isPending || status === 'completed' || status === 'cancelled' || needsInput
          }
          title={needsInput ? 'Use "Take Control" above to complete 2FA first' : undefined}
          className="flex items-center gap-2 px-4 py-2 bg-indigo-600 text-white rounded-lg font-medium text-sm hover:bg-indigo-700 transition-colors disabled:opacity-50"
        >
          <Play className="w-4 h-4" /> {needsInput ? 'Waiting for you...' : 'Resume Queue'}
        </button>
      )}

      <button
        onClick={() => cancelMutation.mutate()}
        disabled={cancelMutation.isPending || status === 'completed' || status === 'cancelled' || status === 'idle'}
        className="flex items-center gap-2 px-4 py-2 border border-red-200 text-red-600 dark:border-red-900/30 dark:text-red-400 rounded-lg font-medium text-sm hover:bg-red-50 dark:hover:bg-red-900/20 transition-colors disabled:opacity-50"
      >
        <XCircle className="w-4 h-4" /> Cancel Run
      </button>

      <button
        onClick={handleExport}
        className="flex items-center gap-2 px-4 py-2 border border-gray-200 text-gray-700 dark:border-gray-700 dark:text-gray-300 rounded-lg font-medium text-sm hover:bg-gray-50 dark:hover:bg-gray-800 transition-colors"
      >
        <Download className="w-4 h-4" /> Export Report
      </button>
    </div>
  );
};
