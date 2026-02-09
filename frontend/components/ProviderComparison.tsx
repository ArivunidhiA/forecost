/**
 * ProviderComparison Component
 * @description Table comparing current costs against cheaper provider alternatives
 */

'use client';

import { useState, useEffect } from 'react';
import { api } from '@/lib/api';
import { ComparisonResponse, ComparisonItem } from '@/types';
import { formatCurrency } from '@/lib/utils';

export default function ProviderComparison() {
  const [data, setData] = useState<ComparisonResponse | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const fetchComparison = async () => {
      try {
        const result = await api.getComparison();
        setData(result);
      } catch (err) {
        console.error('Failed to fetch comparison:', err);
        setError('Failed to load comparison data');
      } finally {
        setIsLoading(false);
      }
    };

    fetchComparison();
  }, []);

  if (isLoading) {
    return (
      <div className="bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 rounded-xl p-6">
        <h2 className="text-lg font-semibold text-slate-900 dark:text-white mb-4">
          Provider Cost Comparison
        </h2>
        <div className="flex items-center justify-center py-8">
          <div className="inline-block animate-spin rounded-full h-6 w-6 border-2 border-slate-300 border-t-slate-900 dark:border-slate-600 dark:border-t-white" />
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 rounded-xl p-6">
        <h2 className="text-lg font-semibold text-slate-900 dark:text-white mb-4">
          Provider Cost Comparison
        </h2>
        <p className="text-sm text-red-500 dark:text-red-400">{error}</p>
      </div>
    );
  }

  const comparisons = data?.comparisons || [];
  const currentTotal = data?.current_total || 0;
  const cheapestTotal = data?.cheapest_total || 0;
  const potentialSavings = currentTotal - cheapestTotal;

  return (
    <div className="bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 rounded-xl p-6">
      <div className="flex items-center justify-between mb-4">
        <h2 className="text-lg font-semibold text-slate-900 dark:text-white">
          Provider Cost Comparison
        </h2>
        {potentialSavings > 0.001 && (
          <span className="text-sm font-medium text-green-600 dark:text-green-400">
            Save up to {formatCurrency(potentialSavings)}/month
          </span>
        )}
      </div>

      {/* Summary banner */}
      {potentialSavings > 0.001 && (
        <div className="mb-4 p-3 bg-green-50 dark:bg-green-900/20 border border-green-200 dark:border-green-800 rounded-lg">
          <p className="text-sm text-green-700 dark:text-green-300">
            You could save <span className="font-semibold">{formatCurrency(potentialSavings)}/month</span>{' '}
            by switching to the cheapest alternatives for each model.
          </p>
        </div>
      )}

      {comparisons.length === 0 ? (
        <p className="text-center py-8 text-slate-500 dark:text-slate-400">
          No usage data yet. Start making API calls to see cost comparisons.
        </p>
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-slate-200 dark:border-slate-700">
                <th className="text-left py-2 px-3 text-slate-500 dark:text-slate-400 font-medium">
                  Current Model
                </th>
                <th className="text-left py-2 px-3 text-slate-500 dark:text-slate-400 font-medium">
                  Provider
                </th>
                <th className="text-right py-2 px-3 text-slate-500 dark:text-slate-400 font-medium">
                  Current Cost
                </th>
                <th className="text-left py-2 px-3 text-slate-500 dark:text-slate-400 font-medium">
                  Cheapest Alt.
                </th>
                <th className="text-right py-2 px-3 text-slate-500 dark:text-slate-400 font-medium">
                  Savings
                </th>
              </tr>
            </thead>
            <tbody>
              {comparisons.map((item: ComparisonItem, idx: number) => {
                const cheapest = item.alternatives[0];
                const savings = cheapest
                  ? item.actual_cost - cheapest.estimated_cost
                  : 0;

                return (
                  <tr
                    key={idx}
                    className="border-b border-slate-100 dark:border-slate-800 hover:bg-slate-50 dark:hover:bg-slate-800/50"
                  >
                    <td className="py-3 px-3">
                      <span className="font-mono text-slate-900 dark:text-white">
                        {item.model}
                      </span>
                    </td>
                    <td className="py-3 px-3">
                      <span className="px-2 py-0.5 text-xs font-medium rounded bg-blue-100 dark:bg-blue-900/30 text-blue-700 dark:text-blue-300">
                        {item.provider}
                      </span>
                    </td>
                    <td className="py-3 px-3 text-right font-medium text-slate-900 dark:text-white">
                      {formatCurrency(item.actual_cost)}
                    </td>
                    <td className="py-3 px-3">
                      {cheapest ? (
                        <div>
                          <span className="font-mono text-slate-700 dark:text-slate-300 text-xs">
                            {cheapest.model}
                          </span>
                          <span className="text-slate-400 dark:text-slate-500 text-xs ml-1">
                            ({cheapest.provider})
                          </span>
                          <span className="block text-xs text-slate-500 dark:text-slate-400">
                            {formatCurrency(cheapest.estimated_cost)}
                          </span>
                        </div>
                      ) : (
                        <span className="text-slate-400 text-xs">—</span>
                      )}
                    </td>
                    <td className="py-3 px-3 text-right">
                      {savings > 0.0001 ? (
                        <span className="text-green-600 dark:text-green-400 font-medium">
                          -{formatCurrency(savings)}
                        </span>
                      ) : (
                        <span className="text-slate-400 text-xs">—</span>
                      )}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
