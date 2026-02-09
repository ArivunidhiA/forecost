/**
 * RecommendationsPanel Component
 * @description Displays cost optimization recommendations from the backend engine
 */

'use client';

import { useState, useEffect } from 'react';
import { api } from '@/lib/api';
import { RecommendationItem, RecommendationsResponse } from '@/types';
import { formatCurrency } from '@/lib/utils';

const PRIORITY_STYLES: Record<string, string> = {
  high: 'bg-red-100 text-red-700 dark:bg-red-900/30 dark:text-red-300',
  medium: 'bg-yellow-100 text-yellow-700 dark:bg-yellow-900/30 dark:text-yellow-300',
  low: 'bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-300',
};

export default function RecommendationsPanel() {
  const [data, setData] = useState<RecommendationsResponse | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const fetchRecommendations = async () => {
      try {
        const result = await api.getRecommendations();
        setData(result);
      } catch (err) {
        console.error('Failed to fetch recommendations:', err);
        setError('Failed to load recommendations');
      } finally {
        setIsLoading(false);
      }
    };

    fetchRecommendations();
  }, []);

  if (isLoading) {
    return (
      <div className="bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 rounded-xl p-6">
        <h2 className="text-lg font-semibold text-slate-900 dark:text-white mb-4">
          Recommendations
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
          Recommendations
        </h2>
        <p className="text-sm text-red-500 dark:text-red-400">{error}</p>
      </div>
    );
  }

  const recommendations = data?.recommendations || [];
  const totalSavings = data?.total_potential_savings || 0;

  return (
    <div className="bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 rounded-xl p-6">
      <div className="flex items-center justify-between mb-4">
        <h2 className="text-lg font-semibold text-slate-900 dark:text-white">
          Recommendations
        </h2>
        {totalSavings > 0 && (
          <span className="text-sm font-medium text-green-600 dark:text-green-400">
            Save up to {formatCurrency(totalSavings)}/month
          </span>
        )}
      </div>

      {recommendations.length === 0 ? (
        <p className="text-center py-8 text-slate-500 dark:text-slate-400">
          No recommendations yet — start making API calls to get optimization tips.
        </p>
      ) : (
        <div className="space-y-3">
          {recommendations.map((rec: RecommendationItem, index: number) => (
            <div
              key={index}
              className="p-4 bg-slate-50 dark:bg-slate-800/50 rounded-lg border border-slate-100 dark:border-slate-700/50"
            >
              <div className="flex items-start justify-between mb-2">
                <div className="flex items-center gap-2">
                  <span
                    className={`px-2 py-0.5 text-xs font-medium rounded ${
                      PRIORITY_STYLES[rec.priority] || PRIORITY_STYLES.medium
                    }`}
                  >
                    {rec.priority}
                  </span>
                  <h3 className="font-medium text-slate-900 dark:text-white text-sm">
                    {rec.title}
                  </h3>
                </div>
                {rec.potential_savings > 0 && (
                  <span className="text-sm font-semibold text-green-600 dark:text-green-400 whitespace-nowrap ml-2">
                    -{formatCurrency(rec.potential_savings)}
                  </span>
                )}
              </div>
              <p className="text-sm text-slate-600 dark:text-slate-400">
                {rec.description}
              </p>
              {rec.current_model && rec.suggested_model && (
                <div className="mt-2 flex items-center gap-2 text-xs">
                  <span className="px-2 py-1 bg-slate-200 dark:bg-slate-700 rounded text-slate-700 dark:text-slate-300 font-mono">
                    {rec.current_model}
                  </span>
                  <span className="text-slate-400">→</span>
                  <span className="px-2 py-1 bg-blue-100 dark:bg-blue-900/30 rounded text-blue-700 dark:text-blue-300 font-mono">
                    {rec.suggested_model}
                  </span>
                </div>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
