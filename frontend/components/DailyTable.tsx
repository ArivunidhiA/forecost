/**
 * DailyTable Component
 * @description Table displaying daily costs for the last 30 days
 */

import { DailyCost } from '@/types';
import { formatCurrency, formatDateFull } from '@/lib/utils';

export interface DailyTableProps {
  data: DailyCost[];
}

export default function DailyTable({ data }: DailyTableProps) {
  if (!data || data.length === 0) {
    return (
      <div className="flex items-center justify-center h-32 text-slate-400">
        No data available
      </div>
    );
  }

  // Sort by date descending (most recent first)
  const sortedData = [...data].sort((a, b) => 
    new Date(b.date).getTime() - new Date(a.date).getTime()
  );

  return (
    <div className="overflow-x-auto">
      <table className="w-full">
        <thead>
          <tr className="border-b border-slate-200 dark:border-slate-700">
            <th className="text-left py-3 px-4 text-sm font-medium text-slate-500 dark:text-slate-400">
              Date
            </th>
            <th className="text-right py-3 px-4 text-sm font-medium text-slate-500 dark:text-slate-400">
              Requests
            </th>
            <th className="text-right py-3 px-4 text-sm font-medium text-slate-500 dark:text-slate-400">
              Cost
            </th>
          </tr>
        </thead>
        <tbody>
          {sortedData.map((row, index) => (
            <tr
              key={row.date}
              className={`border-b border-slate-100 dark:border-slate-800 transition-colors hover:bg-slate-50 dark:hover:bg-slate-800/50 ${
                index === 0 ? 'bg-blue-50/50 dark:bg-blue-900/10' : ''
              }`}
            >
              <td className="py-3 px-4 text-sm text-slate-700 dark:text-slate-300">
                {formatDateFull(row.date)}
                {index === 0 && (
                  <span className="ml-2 text-xs text-blue-600 dark:text-blue-400 font-medium">
                    Today
                  </span>
                )}
              </td>
              <td className="py-3 px-4 text-sm text-slate-600 dark:text-slate-400 text-right tabular-nums">
                {row.call_count.toLocaleString()}
              </td>
              <td className="py-3 px-4 text-sm font-medium text-slate-900 dark:text-white text-right tabular-nums">
                {formatCurrency(row.cost_usd)}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
