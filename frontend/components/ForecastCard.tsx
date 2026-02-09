/**
 * ForecastCard Component
 * @description Shows predicted next month cost with trend arrow, sparkline, and confidence badge
 */

'use client';

import { useState, useEffect } from 'react';
import { ForecastData } from '@/types';
import { api } from '@/lib/api';
import { formatCurrency } from '@/lib/utils';

function TrendArrow({ trend }: { trend: string }) {
  if (trend === 'increasing') {
    return (
      <svg className="w-5 h-5 text-red-500" fill="none" viewBox="0 0 24 24" stroke="currentColor">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 7h8m0 0v8m0-8l-8 8-4-4-6 6" />
      </svg>
    );
  }
  if (trend === 'decreasing') {
    return (
      <svg className="w-5 h-5 text-green-500" fill="none" viewBox="0 0 24 24" stroke="currentColor">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 17h8m0 0V9m0 8l-8-8-4 4-6-6" />
      </svg>
    );
  }
  return (
    <svg className="w-5 h-5 text-slate-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 12h14" />
    </svg>
  );
}

function ConfidenceBadge({ confidence }: { confidence: string }) {
  const colors: Record<string, string> = {
    high: 'bg-green-100 dark:bg-green-900/30 text-green-700 dark:text-green-300',
    medium: 'bg-yellow-100 dark:bg-yellow-900/30 text-yellow-700 dark:text-yellow-300',
    low: 'bg-slate-100 dark:bg-slate-800 text-slate-500 dark:text-slate-400',
  };

  return (
    <span className={`px-2 py-0.5 text-xs font-medium rounded ${colors[confidence] || colors.low}`}>
      {confidence} confidence
    </span>
  );
}

function MiniSparkline({ data, projected }: { data: number[]; projected: number[] }) {
  if (data.length === 0 && projected.length === 0) return null;

  const all = [...data, ...projected];
  const maxVal = Math.max(...all, 0.001);
  const width = 200;
  const height = 40;
  const totalPoints = all.length;
  const stepX = width / Math.max(totalPoints - 1, 1);

  const toY = (val: number) => height - (val / maxVal) * (height - 4) - 2;

  // Historical path
  const histPoints = data.map((v, i) => `${i * stepX},${toY(v)}`).join(' ');

  // Projected path (dashed)
  const projStart = data.length > 0 ? data.length - 1 : 0;
  const projPoints = projected.map((v, i) => `${(projStart + i) * stepX},${toY(v)}`).join(' ');

  return (
    <svg width={width} height={height} className="mt-2">
      {data.length > 1 && (
        <polyline
          fill="none"
          stroke="currentColor"
          strokeWidth="1.5"
          className="text-blue-500"
          points={histPoints}
        />
      )}
      {projected.length > 1 && (
        <polyline
          fill="none"
          stroke="currentColor"
          strokeWidth="1.5"
          strokeDasharray="4 2"
          className="text-blue-300 dark:text-blue-600"
          points={projPoints}
        />
      )}
      {/* Divider line between historical and projected */}
      {data.length > 0 && projected.length > 0 && (
        <line
          x1={(data.length - 1) * stepX}
          y1={0}
          x2={(data.length - 1) * stepX}
          y2={height}
          stroke="currentColor"
          strokeWidth="0.5"
          strokeDasharray="2 2"
          className="text-slate-300 dark:text-slate-600"
        />
      )}
    </svg>
  );
}

export default function ForecastCard() {
  const [forecast, setForecast] = useState<ForecastData | null>(null);
  const [isLoading, setIsLoading] = useState(true);

  useEffect(() => {
    const fetchForecast = async () => {
      try {
        const data = await api.getForecast();
        setForecast(data);
      } catch (err) {
        console.error('Failed to fetch forecast:', err);
      } finally {
        setIsLoading(false);
      }
    };
    fetchForecast();
  }, []);

  if (isLoading) {
    return (
      <div className="bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 rounded-xl p-4">
        <div className="animate-pulse">
          <div className="h-4 bg-slate-200 dark:bg-slate-700 rounded w-32 mb-3" />
          <div className="h-8 bg-slate-200 dark:bg-slate-700 rounded w-24 mb-2" />
          <div className="h-3 bg-slate-200 dark:bg-slate-700 rounded w-40" />
        </div>
      </div>
    );
  }

  if (!forecast || forecast.predicted_next_month_usd === 0) {
    return (
      <div className="bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 rounded-xl p-4">
        <p className="text-sm text-slate-500 dark:text-slate-400">Forecast</p>
        <p className="text-sm text-slate-400 dark:text-slate-500 mt-2">
          Not enough data for a forecast yet.
        </p>
      </div>
    );
  }

  const trendColor = forecast.trend === 'increasing'
    ? 'text-red-600 dark:text-red-400'
    : forecast.trend === 'decreasing'
    ? 'text-green-600 dark:text-green-400'
    : 'text-slate-600 dark:text-slate-400';

  // Build sparkline data from projected_daily
  const projectedValues = forecast.projected_daily.map(d => d.cost_usd);
  // Use daily average as historical approximation
  const histValues = Array(7).fill(forecast.daily_average_usd);

  return (
    <div className="bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 rounded-xl p-4">
      <div className="flex items-center justify-between mb-1">
        <p className="text-sm text-slate-500 dark:text-slate-400">Next Month Forecast</p>
        <ConfidenceBadge confidence={forecast.confidence} />
      </div>
      <div className="flex items-center gap-2">
        <p className="text-2xl font-semibold text-slate-900 dark:text-white">
          {formatCurrency(forecast.predicted_next_month_usd)}
        </p>
        <TrendArrow trend={forecast.trend} />
      </div>
      <div className="flex items-center gap-2 mt-1">
        <p className="text-xs text-slate-500 dark:text-slate-400">
          Avg {formatCurrency(forecast.daily_average_usd)}/day
        </p>
        {forecast.trend_pct_change !== 0 && (
          <span className={`text-xs font-medium ${trendColor}`}>
            {forecast.trend_pct_change > 0 ? '+' : ''}{forecast.trend_pct_change.toFixed(1)}%
          </span>
        )}
      </div>
      <MiniSparkline data={histValues} projected={projectedValues.slice(0, 14)} />
    </div>
  );
}
