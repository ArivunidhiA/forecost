/**
 * Dashboard Page
 * @description Main dashboard with cost summary, model chart, daily table,
 *              recommendations, heatmap, provider comparison, cache stats, and alert banner
 */

'use client';

import { useState, useEffect, useCallback } from 'react';
import { useRouter } from 'next/navigation';
import Navigation from '@/components/Navigation';
import CostCard from '@/components/CostCard';
import ModelChart from '@/components/ModelChart';
import DailyTable from '@/components/DailyTable';
import RecommendationsPanel from '@/components/RecommendationsPanel';
import UsageHeatmap from '@/components/UsageHeatmap';
import ProviderComparison from '@/components/ProviderComparison';
import ForecastCard from '@/components/ForecastCard';
import { api, isAuthenticated, getUser, downloadExport } from '@/lib/api';
import { Stats, User, Budget, AnomalyResponse } from '@/types';
import { formatCurrency } from '@/lib/utils';

export default function DashboardPage() {
  const router = useRouter();
  const [user, setUser] = useState<User | null>(null);
  const [stats, setStats] = useState<Stats | null>(null);
  const [budgets, setBudgets] = useState<Budget[]>([]);
  const [anomalyData, setAnomalyData] = useState<AnomalyResponse | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [lastUpdated, setLastUpdated] = useState<Date | null>(null);
  const [showExportMenu, setShowExportMenu] = useState(false);

  /**
   * Fetch stats and budgets from API
   */
  const fetchStats = useCallback(async () => {
    try {
      const [data, budgetList, anomalies] = await Promise.all([
        api.getStats('month'),
        api.getBudgets().catch(() => [] as Budget[]),
        api.getAnomalies().catch(() => null as AnomalyResponse | null),
      ]);
      setStats(data);
      setBudgets(budgetList);
      setAnomalyData(anomalies);
      setLastUpdated(new Date());
      setError(null);
    } catch (err) {
      console.error('Failed to fetch stats:', err);
      setError('Failed to load statistics. Please try again.');
    }
  }, []);

  /**
   * Initial load and auth check
   */
  useEffect(() => {
    const init = async () => {
      // Check authentication
      if (!isAuthenticated()) {
        router.push('/');
        return;
      }

      // Load user from storage
      const storedUser = getUser();
      if (storedUser) {
        setUser(storedUser);
      }

      // Fetch initial stats
      await fetchStats();
      setIsLoading(false);
    };

    init();
  }, [router, fetchStats]);

  /**
   * Poll for updates every 30 seconds
   */
  useEffect(() => {
    if (isLoading) return;

    const interval = setInterval(fetchStats, 30000);
    return () => clearInterval(interval);
  }, [isLoading, fetchStats]);

  // Loading state
  if (isLoading) {
    return (
      <div className="min-h-screen bg-slate-50 dark:bg-slate-950">
        <Navigation showUserMenu={true} />
        <div className="flex items-center justify-center h-[calc(100vh-64px)]">
          <div className="text-center">
            <div className="inline-block animate-spin rounded-full h-8 w-8 border-2 border-slate-300 border-t-slate-900 dark:border-slate-600 dark:border-t-white" />
            <p className="mt-4 text-slate-500 dark:text-slate-400">Loading dashboard...</p>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-slate-50 dark:bg-slate-950">
      <Navigation showUserMenu={true} />

      <main className="max-w-6xl mx-auto px-4 sm:px-6 py-8">
        {/* Header */}
        <div className="mb-8">
          <div className="flex items-center justify-between">
            <div>
              <h1 className="text-2xl font-bold text-slate-900 dark:text-white">
                Dashboard
              </h1>
              <p className="text-sm text-slate-500 dark:text-slate-400 mt-1">
                {user?.username ? `Welcome back, ${user.username}` : 'Your LLM cost overview'}
              </p>
            </div>
            <div className="flex items-center gap-3">
              {lastUpdated && (
                <p className="text-xs text-slate-400 dark:text-slate-500">
                  Updated {lastUpdated.toLocaleTimeString()}
                </p>
              )}
              <div className="relative">
                <button
                  onClick={() => setShowExportMenu(!showExportMenu)}
                  className="px-3 py-1.5 text-sm rounded-lg border border-slate-200 dark:border-slate-700 text-slate-600 dark:text-slate-300 hover:bg-slate-100 dark:hover:bg-slate-800 transition-colors"
                >
                  Export
                </button>
                {showExportMenu && (
                  <div className="absolute right-0 mt-1 w-36 bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-700 rounded-lg shadow-lg py-1 z-10">
                    <button
                      className="block w-full text-left px-4 py-2 text-sm text-slate-700 dark:text-slate-300 hover:bg-slate-100 dark:hover:bg-slate-800"
                      onClick={() => { downloadExport('csv'); setShowExportMenu(false); }}
                    >
                      Download CSV
                    </button>
                    <button
                      className="block w-full text-left px-4 py-2 text-sm text-slate-700 dark:text-slate-300 hover:bg-slate-100 dark:hover:bg-slate-800"
                      onClick={() => { downloadExport('json'); setShowExportMenu(false); }}
                    >
                      Download JSON
                    </button>
                  </div>
                )}
              </div>
            </div>
          </div>
        </div>

        {/* Budget Alert Banner */}
        {budgets.some((b) => b.status === 'exceeded') && (
          <div className="mb-6 p-4 bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800 rounded-xl flex items-center gap-3">
            <span className="text-red-500 text-lg">!</span>
            <div>
              <p className="text-sm font-medium text-red-700 dark:text-red-300">
                Budget Exceeded
              </p>
              <p className="text-xs text-red-600 dark:text-red-400">
                Your spending has exceeded your monthly budget. Review your usage in Settings.
              </p>
            </div>
          </div>
        )}
        {!budgets.some((b) => b.status === 'exceeded') &&
          budgets.some((b) => b.status === 'warning') && (
            <div className="mb-6 p-4 bg-yellow-50 dark:bg-yellow-900/20 border border-yellow-200 dark:border-yellow-800 rounded-xl flex items-center gap-3">
              <span className="text-yellow-500 text-lg">!</span>
              <div>
                <p className="text-sm font-medium text-yellow-700 dark:text-yellow-300">
                  Budget Warning
                </p>
                <p className="text-xs text-yellow-600 dark:text-yellow-400">
                  You&apos;re approaching your monthly budget limit. Monitor your usage carefully.
                </p>
              </div>
            </div>
          )}

        {/* Anomaly Alert Banner */}
        {anomalyData?.has_active_anomaly && anomalyData.anomalies.length > 0 && (
          <div className="mb-6 p-4 bg-orange-50 dark:bg-orange-900/20 border border-orange-200 dark:border-orange-800 rounded-xl">
            <div className="flex items-center gap-3 mb-2">
              <span className="text-orange-500 text-lg">!</span>
              <p className="text-sm font-medium text-orange-700 dark:text-orange-300">
                Anomaly Detected
              </p>
            </div>
            <div className="space-y-1 ml-7">
              {anomalyData.anomalies.map((a, i) => (
                <p key={i} className="text-xs text-orange-600 dark:text-orange-400">
                  {a.message}
                </p>
              ))}
            </div>
          </div>
        )}

        {/* Error banner */}
        {error && (
          <div className="mb-6 p-4 bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800 rounded-xl text-red-700 dark:text-red-400 text-sm">
            {error}
          </div>
        )}

        {/* Cost Summary Cards */}
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-5 gap-4 mb-8">
          <CostCard
            title="Today"
            amount={stats?.today_usd || 0}
            subtitle="Current day spend"
          />
          <CostCard
            title="This Month"
            amount={stats?.month_usd || 0}
            subtitle="Month to date"
          />
          <CostCard
            title="All Time"
            amount={stats?.all_time_usd || 0}
            subtitle="Total spend"
          />
          <div className="bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 rounded-xl p-4">
            <p className="text-sm text-slate-500 dark:text-slate-400">Cache Savings</p>
            <p className="text-2xl font-semibold text-green-600 dark:text-green-400 mt-1">
              {formatCurrency(stats?.cache_savings_usd || 0)}
            </p>
            <div className="flex items-center gap-2 mt-1">
              <p className="text-xs text-slate-500 dark:text-slate-400">
                {stats?.cache_hits || 0} hits / {(stats?.cache_hits || 0) + (stats?.cache_misses || 0)} total
              </p>
              {((stats?.cache_hits || 0) + (stats?.cache_misses || 0)) > 0 && (
                <span className="text-xs font-medium text-green-600 dark:text-green-400">
                  {(((stats?.cache_hits || 0) / ((stats?.cache_hits || 0) + (stats?.cache_misses || 0))) * 100).toFixed(1)}% hit rate
                </span>
              )}
            </div>
          </div>
          <ForecastCard />
        </div>

        {/* Latency indicator */}
        {stats && stats.avg_latency_ms > 0 && (
          <div className="mb-6 flex items-center gap-4 text-sm text-slate-500 dark:text-slate-400">
            <span>
              Avg. Latency: <span className="font-medium text-slate-700 dark:text-slate-300">{stats.avg_latency_ms.toFixed(0)}ms</span>
            </span>
            <span>
              Total Calls: <span className="font-medium text-slate-700 dark:text-slate-300">{stats.total_calls.toLocaleString()}</span>
            </span>
            <span>
              Total Tokens: <span className="font-medium text-slate-700 dark:text-slate-300">{stats.total_tokens.toLocaleString()}</span>
            </span>
          </div>
        )}

        {/* Charts Grid */}
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6 mb-8">
          {/* Model Chart */}
          <div className="bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 rounded-xl p-6">
            <h2 className="text-lg font-semibold text-slate-900 dark:text-white mb-4">
              Cost by Model
            </h2>
            <ModelChart data={stats?.by_model || []} />
          </div>

          {/* Daily Costs Table */}
          <div className="bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 rounded-xl p-6">
            <h2 className="text-lg font-semibold text-slate-900 dark:text-white mb-4">
              Daily Costs
            </h2>
            <div className="max-h-80 overflow-y-auto">
              <DailyTable data={stats?.by_day || []} />
            </div>
          </div>
        </div>

        {/* Usage Heatmap */}
        <div className="mb-8">
          <UsageHeatmap />
        </div>

        {/* Recommendations */}
        <div className="mb-8">
          <RecommendationsPanel />
        </div>

        {/* Provider Cost Comparison */}
        <div className="mb-8">
          <ProviderComparison />
        </div>

        {/* Model breakdown details */}
        <div className="bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 rounded-xl p-6">
          <h2 className="text-lg font-semibold text-slate-900 dark:text-white mb-4">
            Model Breakdown
          </h2>
          {stats?.by_model && stats.by_model.length > 0 ? (
            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
              {stats.by_model.map((model) => {
                const pct = stats.total_usd > 0
                  ? ((model.cost_usd / stats.total_usd) * 100).toFixed(1)
                  : '0.0';
                return (
                  <div
                    key={model.model}
                    className="p-4 bg-slate-50 dark:bg-slate-800/50 rounded-lg"
                  >
                    <div className="flex items-center justify-between mb-2">
                      <span className="font-medium text-slate-900 dark:text-white text-sm">
                        {model.model}
                      </span>
                      <span className="text-xs text-slate-500 dark:text-slate-400">
                        {pct}%
                      </span>
                    </div>
                    <p className="text-2xl font-semibold text-slate-900 dark:text-white">
                      {formatCurrency(model.cost_usd)}
                    </p>
                    <div className="flex items-center justify-between mt-1">
                      <p className="text-xs text-slate-500 dark:text-slate-400">
                        {model.call_count.toLocaleString()} calls &middot; {model.provider}
                      </p>
                      {model.avg_latency_ms != null && (
                        <p className="text-xs text-slate-400 dark:text-slate-500">
                          ~{model.avg_latency_ms.toFixed(0)}ms
                        </p>
                      )}
                    </div>
                  </div>
                );
              })}
            </div>
          ) : (
            <p className="text-center py-8 text-slate-500 dark:text-slate-400">
              No usage data yet. Start making API calls through your proxy keys.
            </p>
          )}
        </div>
      </main>
    </div>
  );
}
