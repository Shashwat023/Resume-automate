import {
  useReactTable,
  getCoreRowModel,
  flexRender,
  type ColumnDef,
} from '@tanstack/react-table';
import type { Job } from '../../../types';
import { ExternalLink, Building2, MapPin, MonitorPlay, Briefcase, Server } from 'lucide-react';

interface JobTableProps {
  data: Job[];
  rowSelection: Record<string, boolean>;
  onRowSelectionChange: (updater: any) => void;
}

export const JobTable = ({ data, rowSelection, onRowSelectionChange }: JobTableProps) => {
  const columns: ColumnDef<Job>[] = [
    {
      id: 'select',
      header: ({ table }) => (
        <div className="px-1">
          <input
            type="checkbox"
            className="w-4 h-4 rounded border-gray-300 text-indigo-600 focus:ring-indigo-600"
            checked={table.getIsAllRowsSelected()}
            ref={(input) => {
              if (input) {
                input.indeterminate = table.getIsSomeRowsSelected();
              }
            }}
            onChange={table.getToggleAllRowsSelectedHandler()}
          />
        </div>
      ),
      cell: ({ row }) => (
        <div className="px-1">
          <input
            type="checkbox"
            className="w-4 h-4 rounded border-gray-300 text-indigo-600 focus:ring-indigo-600"
            checked={row.getIsSelected()}
            disabled={!row.getCanSelect()}
            onChange={row.getToggleSelectedHandler()}
          />
        </div>
      ),
      enableSorting: false,
      enableHiding: false,
    },
    {
      accessorKey: 'title',
      header: 'Job Title',
      cell: ({ row }) => (
        <div className="font-medium text-gray-900 dark:text-gray-100 max-w-[200px] truncate" title={row.original.title}>
          {row.original.title}
        </div>
      ),
    },
    {
      accessorKey: 'company_name',
      header: 'Company',
      cell: ({ row }) => (
        <div className="flex items-center gap-2">
          <Building2 className="w-4 h-4 text-gray-400" />
          <span className="text-gray-700 dark:text-gray-300 truncate max-w-[150px]" title={row.original.company_name}>
            {row.original.company_name}
          </span>
        </div>
      ),
    },
    {
      accessorKey: 'location',
      header: 'Location',
      cell: ({ row }) => (
        <div className="flex items-center gap-2 text-sm text-gray-600 dark:text-gray-400">
          <MapPin className="w-4 h-4" />
          <span className="truncate max-w-[150px]">{row.original.location}</span>
        </div>
      ),
    },
    {
      accessorKey: 'location_type',
      header: 'Job Type',
      cell: ({ row }) => (
        <span className="inline-flex items-center px-2 py-1 rounded-md text-xs font-medium bg-gray-100 dark:bg-gray-800 text-gray-700 dark:text-gray-300">
          {row.original.location_type}
        </span>
      ),
    },
    {
      accessorKey: 'ats',
      header: 'ATS',
      cell: ({ row }) => (
        <span className="text-sm text-gray-500 dark:text-gray-400">
          {row.original.ats || 'Unknown'}
        </span>
      ),
    },
    {
      id: 'links',
      header: 'Links',
      cell: ({ row }) => (
        <div className="flex items-center gap-3">
          {row.original.company_url && (
            <a
              href={row.original.company_url}
              target="_blank"
              rel="noopener noreferrer"
              className="text-gray-400 hover:text-indigo-600 dark:hover:text-indigo-400 transition-colors"
              title="Company Website"
            >
              <Briefcase className="w-4 h-4" />
            </a>
          )}
          <a
            href={row.original.apply_url}
            target="_blank"
            rel="noopener noreferrer"
            className="text-gray-400 hover:text-indigo-600 dark:hover:text-indigo-400 transition-colors"
            title="Apply Link"
          >
            <ExternalLink className="w-4 h-4" />
          </a>
        </div>
      ),
    },
  ];

  const table = useReactTable({
    data,
    columns,
    state: {
      rowSelection,
    },
    enableRowSelection: true,
    onRowSelectionChange,
    getCoreRowModel: getCoreRowModel(),
    getRowId: (row) => row.id,
  });

  return (
    <div className="w-full">
      {/* Mobile view (Cards) */}
      <div className="block lg:hidden space-y-4">
        {table.getRowModel().rows.map((row) => (
          <div
            key={row.id}
            className={`bg-white dark:bg-gray-800 border rounded-xl p-4 transition-colors ${
              row.getIsSelected() 
                ? 'border-indigo-500 ring-1 ring-indigo-500 dark:border-indigo-400 dark:ring-indigo-400' 
                : 'border-gray-200 dark:border-gray-700'
            }`}
          >
            <div className="flex items-start justify-between gap-4 mb-3">
              <div className="flex items-start gap-3">
                <div className="pt-1">
                  <input
                    type="checkbox"
                    className="w-5 h-5 rounded border-gray-300 text-indigo-600 focus:ring-indigo-600"
                    checked={row.getIsSelected()}
                    disabled={!row.getCanSelect()}
                    onChange={row.getToggleSelectedHandler()}
                  />
                </div>
                <div>
                  <h4 className="font-semibold text-gray-900 dark:text-gray-100 line-clamp-2">
                    {row.original.title}
                  </h4>
                  <div className="flex items-center gap-1.5 text-sm text-gray-500 dark:text-gray-400 mt-1">
                    <Building2 className="w-4 h-4 shrink-0" />
                    <span className="truncate">{row.original.company_name}</span>
                  </div>
                </div>
              </div>
            </div>
            
            <div className="flex flex-wrap gap-2 mt-4 pt-4 border-t border-gray-100 dark:border-gray-700/50">
              <div className="flex items-center gap-1.5 text-xs text-gray-600 dark:text-gray-400 bg-gray-50 dark:bg-gray-900 px-2 py-1 rounded">
                <MapPin className="w-3.5 h-3.5" />
                {row.original.location}
              </div>
              <div className="flex items-center gap-1.5 text-xs text-gray-600 dark:text-gray-400 bg-gray-50 dark:bg-gray-900 px-2 py-1 rounded">
                <MonitorPlay className="w-3.5 h-3.5" />
                {row.original.location_type}
              </div>
              <div className="flex items-center gap-1.5 text-xs text-gray-600 dark:text-gray-400 bg-gray-50 dark:bg-gray-900 px-2 py-1 rounded">
                <Server className="w-3.5 h-3.5" />
                {row.original.ats || 'Unknown'}
              </div>
            </div>

            <div className="flex items-center justify-end gap-4 mt-4 pt-4 border-t border-gray-100 dark:border-gray-700/50">
              {row.original.company_url && (
                <a href={row.original.company_url} target="_blank" rel="noopener noreferrer" className="text-sm text-gray-500 hover:text-indigo-600 dark:hover:text-indigo-400 font-medium">
                  Website
                </a>
              )}
              <a href={row.original.apply_url} target="_blank" rel="noopener noreferrer" className="text-sm flex items-center gap-1 text-indigo-600 dark:text-indigo-400 hover:text-indigo-700 font-medium">
                Apply <ExternalLink className="w-3.5 h-3.5" />
              </a>
            </div>
          </div>
        ))}
      </div>

      {/* Desktop view (Table) */}
      <div className="hidden lg:block bg-white dark:bg-gray-800 rounded-xl border border-gray-200 dark:border-gray-700 overflow-hidden">
        <div className="overflow-x-auto">
          <table className="w-full text-left border-collapse text-sm">
            <thead className="bg-gray-50 dark:bg-gray-900/50 sticky top-0 z-10 border-b border-gray-200 dark:border-gray-700">
              {table.getHeaderGroups().map((headerGroup) => (
                <tr key={headerGroup.id}>
                  {headerGroup.headers.map((header) => (
                    <th
                      key={header.id}
                      className="py-3 px-4 font-semibold text-gray-700 dark:text-gray-300 whitespace-nowrap first:pl-6 last:pr-6"
                    >
                      {header.isPlaceholder
                        ? null
                        : flexRender(
                            header.column.columnDef.header,
                            header.getContext()
                          )}
                    </th>
                  ))}
                </tr>
              ))}
            </thead>
            <tbody className="divide-y divide-gray-100 dark:divide-gray-800/60">
              {table.getRowModel().rows.map((row) => (
                <tr 
                  key={row.id} 
                  className={`hover:bg-gray-50 dark:hover:bg-gray-800/50 transition-colors ${
                    row.getIsSelected() ? 'bg-indigo-50/50 dark:bg-indigo-900/10' : ''
                  }`}
                >
                  {row.getVisibleCells().map((cell) => (
                    <td key={cell.id} className="py-3 px-4 whitespace-nowrap first:pl-6 last:pr-6">
                      {flexRender(
                        cell.column.columnDef.cell,
                        cell.getContext()
                      )}
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
};
