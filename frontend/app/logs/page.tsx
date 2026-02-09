/**
 * Logs Explorer Page
 * @description Searchable, filterable, paginated view of all usage logs
 */

'use client';

import { useState, useEffect, useCallback } from 'react';
import { useRouter } from 'next/navigation';
import Navigation from '@/components/Navigation';
import LogsTable from '@/components/LogsTable';
import { api, isAuthenticated, getLogs, downloadExport, LogsParams } from '@/lib/api';
import { UsageLogEntry } from '@/types';

export default function LogsPage() {
  const router = useRouter();
  const [logs, setLogs] = useState<UsageLogEntry[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [pageSize] = useState(50);
  const [hasMore, setHasMore] = useState(false);
  const [isLoading, setIsLoading] = useState(true);

  // Filters
  const [provider, setProvider] = useState('');
  const [model, setModel] = useState('');
  const [tagFilter, setTagFilter] = useState('');
  const [cacheFilter, setCacheFilter] = useState<string>('');
  const [dateFrom, setDateFrom] = useState('');
  const [dateTo, setDateTo] = useState('');
  const [sortBy, setSortBy] = useState('created_at');
  const [sortOrder, setSortOrder] = useState('desc');

  const fetchLogs = useCallback(async () => {
    setIsLoading(true);
    try {
      const params: LogsParams = {
        page,
        page_size: pageSize,
        sort_by: sortBy,
        sort_order: sortOrder,
      };
      if (provider) params.provider = provider;
      if (model) params.model = model;
      if (tagFilter) params.tag = tagFilter;
      if (cacheFilter === 'true') params.cache_hit = true;
      if (cacheFilter === 'false') params.cache_hit = false;
      if (dateFrom) params.date_from = dateFrom;
      if (dateTo) params.date_to = dateTo;

      const data = await getLogs(params);
      setLogs(data.logs);
      setTotal(data.total);
      setHasMore(data.has_more);
    } catch (err) {
      console.error('Failed to fetch logs:', err);
    } finally {
      setIsLoading(false);
    }
  }, [page, pageSize, provider, model, tagFilter, cacheFilter, dateFrom, dateTo, sortBy, sortOrder]);

  useEffect(() => {
    if (!isAuthenticated()) {
      router.push('/');
      return;
    }
    fetchLogs();
  }, [router, fetchLogs]);

  const handleSort = (field: string) => {
    if (sortBy === field) {
      setSortOrder(sortOrder === 'asc' ? 'desc' : 'asc');
    } else {
      setSortBy(field);
      setSortOrder('desc');
    }
    setPage(1);
  };

  const handlePageChange = (newPage: number) => {
    setPage(newPage);
  };

  const handleClearFilters = () => {
    setProvider('');
    setModel('');
    setTagFilter('');
    setCacheFilter('');
    setDateFrom('');
    setDateTo('');
    setPage(1);
  };

  const hasFilters = provider || model || tagFilter || cacheFilter || dateFrom || dateTo;

  const filterParams: LogsParams = {};
  if (provider) filterParams.provider = provider;
  if (model) filterParams.model = model;
  if (tagFilter) filterParams.tag = tagFilter;
  if (dateFrom) filterParams.date_from = dateFrom;
  if (dateTo) filterParams.date_to = dateTo;

  return (
    <div className="min-h-screen bg-slate-50 dark:bg-slate-950">
      <Navigation showUserMenu={true} />

      <main className="max-w-7xl mx-auto px-4 sm:px-6 py-8">
        {/* Header */}
        <div className="flex items-center justify-between mb-6">
          <div>
            <h1 className="text-2xl font-bold text-slate-900 dark:text-white">Usage Logs</h1>
            <p className="text-sm text-slate-500 dark:text-slate-400 mt-1">
              {total.toLocaleString()} total log entries
            </p>
          </div>
          <div className="flex items-center gap-2">
            <button
              onClick={() => downloadExport('csv', filterParams)}
              className="px-3 py-1.5 text-sm rounded-lg border border-slate-200 dark:border-slate-700 text-slate-600 dark:text-slate-300 hover:bg-slate-100 dark:hover:bg-slate-800 transition-colors"
            >
              Export CSV
            </button>
            <button
              onClick={() => downloadExport('json', filterParams)}
              className="px-3 py-1.5 text-sm rounded-lg border border-slate-200 dark:border-slate-700 text-slate-600 dark:text-slate-300 hover:bg-slate-100 dark:hover:bg-slate-800 transition-colors"
            >
              Export JSON
            </button>
          </div>
        </div>

        {/* Filter Bar */}
        <div className="bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 rounded-xl p-4 mb-6">
          <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-3">
            <div>
              <label className="block text-xs font-medium text-slate-500 dark:text-slate-400 mb-1">Provider</label>
              <select
                value={provider}
                onChange={(e) => { setProvider(e.target.value); setPage(1); }}
                className="w-full px-2 py-1.5 text-sm bg-white dark:bg-slate-800 border border-slate-200 dark:border-slate-700 rounded-lg text-slate-900 dark:text-slate-100 focus:outline-none focus:ring-2 focus:ring-blue-500"
              >
                <option value="">All</option>
                <option value="openai">OpenAI</option>
                <option value="anthropic">Anthropic</option>
                <option value="google">Google</option>
              </select>
            </div>
            <div>
              <label className="block text-xs font-medium text-slate-500 dark:text-slate-400 mb-1">Model</label>
              <input
                type="text"
                value={model}
                onChange={(e) => { setModel(e.target.value); setPage(1); }}
                placeholder="e.g. gpt-4o"
                className="w-full px-2 py-1.5 text-sm bg-white dark:bg-slate-800 border border-slate-200 dark:border-slate-700 rounded-lg text-slate-900 dark:text-slate-100 focus:outline-none focus:ring-2 focus:ring-blue-500"
              />
            </div>
            <div>
              <label className="block text-xs font-medium text-slate-500 dark:text-slate-400 mb-1">Tag</label>
              <input
                type="text"
                value={tagFilter}
                onChange={(e) => { setTagFilter(e.target.value); setPage(1); }}
                placeholder="e.g. backend"
                className="w-full px-2 py-1.5 text-sm bg-white dark:bg-slate-800 border border-slate-200 dark:border-slate-700 rounded-lg text-slate-900 dark:text-slate-100 focus:outline-none focus:ring-2 focus:ring-blue-500"
              />
            </div>
            <div>
              <label className="block text-xs font-medium text-slate-500 dark:text-slate-400 mb-1">Cache</label>
              <select
                value={cacheFilter}
                onChange={(e) => { setCacheFilter(e.target.value); setPage(1); }}
                className="w-full px-2 py-1.5 text-sm bg-white dark:bg-slate-800 border border-slate-200 dark:border-slate-700 rounded-lg text-slate-900 dark:text-slate-100 focus:outline-none focus:ring-2 focus:ring-blue-500"
              >
                <option value="">All</option>
                <option value="true">Hits only</option>
                <option value="false">Misses only</option>
              </select>
            </div>
            <div>
              <label className="block text-xs font-medium text-slate-500 dark:text-slate-400 mb-1">From</label>
              <input
                type="date"
                value={dateFrom}
                onChange={(e) => { setDateFrom(e.target.value); setPage(1); }}
                className="w-full px-2 py-1.5 text-sm bg-white dark:bg-slate-800 border border-slate-200 dark:border-slate-700 rounded-lg text-slate-900 dark:text-slate-100 focus:outline-none focus:ring-2 focus:ring-blue-500"
              />
            </div>
            <div>
              <label className="block text-xs font-medium text-slate-500 dark:text-slate-400 mb-1">To</label>
              <input
                type="date"
                value={dateTo}
                onChange={(e) => { setDateTo(e.target.value); setPage(1); }}
                className="w-full px-2 py-1.5 text-sm bg-white dark:bg-slate-800 border border-slate-200 dark:border-slate-700 rounded-lg text-slate-900 dark:text-slate-100 focus:outline-none focus:ring-2 focus:ring-blue-500"
              />
            </div>
          </div>
          {hasFilters && (
            <div className="mt-3 flex justify-end">
              <button
                onClick={handleClearFilters}
                className="text-xs text-blue-600 dark:text-blue-400 hover:underline"
              >
                Clear all filters
              </button>
            </div>
          )}
        </div>

        {/* Logs Table */}
        <div className="bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 rounded-xl p-4">
          <LogsTable
            logs={logs}
            total={total}
            page={page}
            pageSize={pageSize}
            hasMore={hasMore}
            sortBy={sortBy}
            sortOrder={sortOrder}
            onSort={handleSort}
            onPageChange={handlePageChange}
            isLoading={isLoading}
          />
        </div>
      </main>
    </div>
  );
}
