/**
 * LogsTable Component
 * @description Paginated table for displaying usage log entries with sorting and tag pills
 */

'use client';

import { UsageLogEntry } from '@/types';
import { formatCurrency } from '@/lib/utils';

interface LogsTableProps {
  logs: UsageLogEntry[];
  total: number;
  page: number;
  pageSize: number;
  hasMore: boolean;
  sortBy: string;
  sortOrder: string;
  onSort: (field: string) => void;
  onPageChange: (page: number) => void;
  isLoading: boolean;
}

function SortIcon({ field, sortBy, sortOrder }: { field: string; sortBy: string; sortOrder: string }) {
  if (sortBy !== field) return <span className="text-slate-300 dark:text-slate-600 ml-1">&#x2195;</span>;
  return <span className="ml-1">{sortOrder === 'asc' ? '\u2191' : '\u2193'}</span>;
}

export default function LogsTable({
  logs,
  total,
  page,
  pageSize,
  hasMore,
  sortBy,
  sortOrder,
  onSort,
  onPageChange,
  isLoading,
}: LogsTableProps) {
  const totalPages = Math.ceil(total / pageSize);

  if (isLoading) {
    return (
      <div className="flex items-center justify-center py-16">
        <div className="inline-block animate-spin rounded-full h-6 w-6 border-2 border-slate-300 border-t-slate-900 dark:border-slate-600 dark:border-t-white" />
      </div>
    );
  }

  if (logs.length === 0) {
    return (
      <div className="text-center py-16 text-slate-500 dark:text-slate-400">
        <p className="text-lg font-medium">No logs found</p>
        <p className="text-sm mt-1">Try adjusting your filters or make some API calls first.</p>
      </div>
    );
  }

  return (
    <div>
      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-slate-200 dark:border-slate-700">
              <th
                className="text-left py-3 px-3 font-medium text-slate-500 dark:text-slate-400 cursor-pointer hover:text-slate-700 dark:hover:text-slate-200 select-none"
                onClick={() => onSort('created_at')}
              >
                Time <SortIcon field="created_at" sortBy={sortBy} sortOrder={sortOrder} />
              </th>
              <th className="text-left py-3 px-3 font-medium text-slate-500 dark:text-slate-400">Provider</th>
              <th className="text-left py-3 px-3 font-medium text-slate-500 dark:text-slate-400">Model</th>
              <th
                className="text-right py-3 px-3 font-medium text-slate-500 dark:text-slate-400 cursor-pointer hover:text-slate-700 dark:hover:text-slate-200 select-none"
                onClick={() => onSort('input_tokens')}
              >
                Tokens (In/Out) <SortIcon field="input_tokens" sortBy={sortBy} sortOrder={sortOrder} />
              </th>
              <th
                className="text-right py-3 px-3 font-medium text-slate-500 dark:text-slate-400 cursor-pointer hover:text-slate-700 dark:hover:text-slate-200 select-none"
                onClick={() => onSort('cost_usd')}
              >
                Cost <SortIcon field="cost_usd" sortBy={sortBy} sortOrder={sortOrder} />
              </th>
              <th
                className="text-right py-3 px-3 font-medium text-slate-500 dark:text-slate-400 cursor-pointer hover:text-slate-700 dark:hover:text-slate-200 select-none"
                onClick={() => onSort('latency_ms')}
              >
                Latency <SortIcon field="latency_ms" sortBy={sortBy} sortOrder={sortOrder} />
              </th>
              <th className="text-center py-3 px-3 font-medium text-slate-500 dark:text-slate-400">Cache</th>
              <th className="text-left py-3 px-3 font-medium text-slate-500 dark:text-slate-400">Tags</th>
            </tr>
          </thead>
          <tbody>
            {logs.map((log) => (
              <tr
                key={log.id}
                className="border-b border-slate-100 dark:border-slate-800 hover:bg-slate-50 dark:hover:bg-slate-800/50 transition-colors"
              >
                <td className="py-2.5 px-3 text-slate-600 dark:text-slate-300 whitespace-nowrap">
                  {new Date(log.created_at).toLocaleString(undefined, {
                    month: 'short',
                    day: 'numeric',
                    hour: '2-digit',
                    minute: '2-digit',
                    second: '2-digit',
                  })}
                </td>
                <td className="py-2.5 px-3">
                  <span className="px-2 py-0.5 text-xs font-medium rounded bg-blue-100 dark:bg-blue-900/30 text-blue-700 dark:text-blue-300">
                    {log.provider}
                  </span>
                </td>
                <td className="py-2.5 px-3 text-slate-900 dark:text-white font-mono text-xs">
                  {log.model}
                </td>
                <td className="py-2.5 px-3 text-right text-slate-600 dark:text-slate-300 font-mono text-xs">
                  {log.input_tokens.toLocaleString()} / {log.output_tokens.toLocaleString()}
                </td>
                <td className="py-2.5 px-3 text-right font-medium text-slate-900 dark:text-white">
                  {formatCurrency(log.cost_usd)}
                </td>
                <td className="py-2.5 px-3 text-right text-slate-500 dark:text-slate-400">
                  {log.latency_ms != null ? `${log.latency_ms.toFixed(0)}ms` : '-'}
                </td>
                <td className="py-2.5 px-3 text-center">
                  {log.cache_hit ? (
                    <span className="px-2 py-0.5 text-xs font-medium rounded bg-green-100 dark:bg-green-900/30 text-green-700 dark:text-green-300">
                      HIT
                    </span>
                  ) : (
                    <span className="text-slate-400 dark:text-slate-600 text-xs">-</span>
                  )}
                </td>
                <td className="py-2.5 px-3">
                  <div className="flex flex-wrap gap-1">
                    {log.tags.map((tag) => (
                      <span
                        key={tag}
                        className="px-1.5 py-0.5 text-xs rounded bg-indigo-100 dark:bg-indigo-900/30 text-indigo-700 dark:text-indigo-300"
                      >
                        {tag}
                      </span>
                    ))}
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {/* Pagination */}
      <div className="flex items-center justify-between mt-4 pt-4 border-t border-slate-200 dark:border-slate-700">
        <p className="text-sm text-slate-500 dark:text-slate-400">
          Showing {(page - 1) * pageSize + 1}-{Math.min(page * pageSize, total)} of {total.toLocaleString()} logs
        </p>
        <div className="flex items-center gap-2">
          <button
            onClick={() => onPageChange(page - 1)}
            disabled={page <= 1}
            className="px-3 py-1.5 text-sm rounded-lg border border-slate-200 dark:border-slate-700 text-slate-600 dark:text-slate-300 hover:bg-slate-100 dark:hover:bg-slate-800 disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
          >
            Previous
          </button>
          <span className="text-sm text-slate-500 dark:text-slate-400">
            Page {page} of {totalPages}
          </span>
          <button
            onClick={() => onPageChange(page + 1)}
            disabled={!hasMore}
            className="px-3 py-1.5 text-sm rounded-lg border border-slate-200 dark:border-slate-700 text-slate-600 dark:text-slate-300 hover:bg-slate-100 dark:hover:bg-slate-800 disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
          >
            Next
          </button>
        </div>
      </div>
    </div>
  );
}
