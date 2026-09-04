import { 
  createColumnHelper, 
  flexRender, 
  getCoreRowModel, 
  useReactTable,
} from '@tanstack/react-table';
import { useState } from 'react';
import { PlayCircle, PauseCircle, SkipForward, ExternalLink, History } from 'lucide-react';
import { QueueStatusBadge } from './QueueStatusBadge';
import { JobTimelineModal } from './JobTimelineModal';
import { useQueueStore } from '../../../store/queueStore';
import { type QueueItem } from '../../../types';
import {
  useSkipJobMutation,
  useRetryJobMutation,
  usePauseJobMutation,
  useResumeJobMutation,
} from '../services/queue.queries';

const columnHelper = createColumnHelper<QueueItem>();

// Statuses a job can be pause/resumed from — never a terminal one.
const PAUSABLE_RAW_STATUSES = new Set(['queued', 'pending', 'running']);

export const QueueTable = () => {
  const queueState = useQueueStore((state) => state.queueState);
  const [timelineJobId, setTimelineJobId] = useState<string | null>(null);
  const skipMutation = useSkipJobMutation();
  const retryMutation = useRetryJobMutation();
  const pauseMutation = usePauseJobMutation();
  const resumeMutation = useResumeJobMutation();

  const columns = [
    columnHelper.accessor((_, index) => index + 1, {
      id: 'position',
      header: '#',
      cell: info => <span className="text-gray-500 font-medium text-sm">{info.getValue()}</span>,
    }),
    columnHelper.accessor('company', {
      header: 'Company',
      cell: info => (
        <div className="flex items-center gap-3">
          <div className="w-8 h-8 rounded-md bg-gray-100 dark:bg-gray-800 flex items-center justify-center font-bold text-gray-500 text-xs shrink-0">
            {info.getValue().charAt(0)}
          </div>
          <span className="font-medium text-gray-900 dark:text-gray-100">{info.getValue()}</span>
        </div>
      ),
    }),
    columnHelper.accessor('jobTitle', {
      header: 'Job Title',
      cell: info => <span className="text-gray-700 dark:text-gray-300 text-sm truncate max-w-[200px] block">{info.getValue()}</span>,
    }),
    columnHelper.accessor('ats', {
      header: 'ATS',
      cell: info => <span className="text-gray-500 dark:text-gray-400 text-sm uppercase">{info.getValue() || 'Unknown'}</span>,
    }),
    columnHelper.accessor('status', {
      header: 'Status',
      cell: info => (
        // title carries the finer-grained backend label (e.g. distinguishing
        // "Paused" from an ordinary "Queued", both of which render the same
        // badge) without a visual redesign — hover to see it.
        <span title={info.row.original.statusLabel}>
          <QueueStatusBadge status={info.getValue()} />
        </span>
      ),
    }),
    columnHelper.accessor('duration', {
      header: 'Duration',
      cell: info => {
        const d = info.getValue();
        return <span className="text-gray-500 text-sm">{d ? `${d}s` : '-'}</span>;
      },
    }),
    columnHelper.display({
      id: 'actions',
      header: '',
      cell: (info) => {
        const item = info.row.original;
        
        return (
          <div className="flex items-center justify-end gap-2 opacity-0 group-hover:opacity-100 transition-opacity">
            {item.rawStatus === 'paused' && (
              <button
                onClick={() => resumeMutation.mutate(item.id)}
                disabled={resumeMutation.isPending}
                className="p-1.5 text-gray-400 hover:text-indigo-600 transition-colors disabled:opacity-50"
                title="Resume"
              >
                <PlayCircle className="w-4 h-4" />
              </button>
            )}
            {item.rawStatus && PAUSABLE_RAW_STATUSES.has(item.rawStatus) && (
              <button
                onClick={() => pauseMutation.mutate(item.id)}
                disabled={pauseMutation.isPending}
                className="p-1.5 text-gray-400 hover:text-amber-600 transition-colors disabled:opacity-50"
                title="Pause — stop this application before it goes further"
              >
                <PauseCircle className="w-4 h-4" />
              </button>
            )}
            {item.status === 'failed' && (
              <button onClick={() => retryMutation.mutate(item.jobId)} className="p-1.5 text-gray-400 hover:text-indigo-600 transition-colors" title="Retry">
                <PlayCircle className="w-4 h-4" />
              </button>
            )}
            {(item.status === 'waiting' || item.status === 'failed') && (
              <button onClick={() => skipMutation.mutate(item.jobId)} className="p-1.5 text-gray-400 hover:text-amber-600 transition-colors" title="Skip">
                <SkipForward className="w-4 h-4" />
              </button>
            )}
            {item.company_url && (
              <a href={item.company_url} target="_blank" rel="noreferrer" className="p-1.5 text-gray-400 hover:text-gray-900 transition-colors" title="Open Job">
                <ExternalLink className="w-4 h-4" />
              </a>
            )}
            <button
              onClick={() => setTimelineJobId(item.id)}
              className="p-1.5 text-gray-400 hover:text-gray-900 dark:hover:text-gray-100 transition-colors"
              title="View run timeline"
            >
              <History className="w-4 h-4" />
            </button>
          </div>
        );
      },
    }),
  ];

  const table = useReactTable({
    data: queueState?.items || [],
    columns,
    getCoreRowModel: getCoreRowModel(),
  });

  return (
    <div className="bg-white dark:bg-gray-800 rounded-xl border border-gray-200 dark:border-gray-700 flex flex-col h-full overflow-hidden">
      {/* Independent scroll region for the row list — previously this
          panel had no vertical overflow handling at all, so with the
          outer h-full/overflow-hidden layout in QueuePage.tsx, any rows
          past the visible height were silently clipped and completely
          unreachable (not just visually cut off, actually inaccessible
          by any scroll). The header stays pinned via `sticky top-0` so
          column labels remain visible while scrolling through the list. */}
      <div className="overflow-auto custom-scrollbar flex-1 min-h-0">
        <table className="w-full text-left border-collapse">
          <thead className="sticky top-0 z-10">
            {table.getHeaderGroups().map((headerGroup) => (
              <tr key={headerGroup.id} className="border-b border-gray-200 dark:border-gray-700 bg-gray-50 dark:bg-gray-800">
                {headerGroup.headers.map((header) => (
                  <th key={header.id} className="px-6 py-4 text-xs font-semibold text-gray-500 dark:text-gray-400 uppercase tracking-wider">
                    {flexRender(header.column.columnDef.header, header.getContext())}
                  </th>
                ))}
              </tr>
            ))}
          </thead>
          <tbody className="divide-y divide-gray-200 dark:divide-gray-700">
            {table.getRowModel().rows.map((row) => (
              <tr key={row.id} className="group hover:bg-gray-50 dark:hover:bg-gray-700/50 transition-colors">
                {row.getVisibleCells().map((cell) => (
                  <td key={cell.id} className="px-6 py-4 whitespace-nowrap">
                    {flexRender(cell.column.columnDef.cell, cell.getContext())}
                  </td>
                ))}
              </tr>
            ))}
            {!queueState?.items?.length && (
              <tr>
                <td colSpan={columns.length} className="px-6 py-12 text-center text-gray-500 dark:text-gray-400">
                  No jobs currently in the queue.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>

      {timelineJobId && (
        <JobTimelineModal applicationId={timelineJobId} onClose={() => setTimelineJobId(null)} />
      )}
    </div>
  );
};
