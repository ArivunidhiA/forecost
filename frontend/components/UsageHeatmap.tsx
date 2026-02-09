/**
 * UsageHeatmap Component
 * @description 7x24 grid showing API call density by day-of-week and hour-of-day
 */

'use client';

import { useState, useEffect } from 'react';
import { api } from '@/lib/api';
import { HeatmapCell } from '@/types';

const DAY_LABELS = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'];
const HOUR_LABELS = Array.from({ length: 24 }, (_, i) => i);

function getHeatColor(value: number, max: number): string {
  if (value === 0 || max === 0) return 'bg-slate-100 dark:bg-slate-800';
  const intensity = value / max;
  if (intensity < 0.2) return 'bg-blue-100 dark:bg-blue-900/30';
  if (intensity < 0.4) return 'bg-blue-200 dark:bg-blue-800/40';
  if (intensity < 0.6) return 'bg-blue-300 dark:bg-blue-700/50';
  if (intensity < 0.8) return 'bg-blue-400 dark:bg-blue-600/60';
  return 'bg-blue-500 dark:bg-blue-500/70';
}

export default function UsageHeatmap() {
  const [cells, setCells] = useState<HeatmapCell[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [tooltip, setTooltip] = useState<{
    x: number;
    y: number;
    day: number;
    hour: number;
    calls: number;
    cost: number;
  } | null>(null);

  useEffect(() => {
    const fetchHeatmap = async () => {
      try {
        const data = await api.getHeatmap();
        setCells(data.cells);
      } catch (err) {
        console.error('Failed to fetch heatmap:', err);
      } finally {
        setIsLoading(false);
      }
    };

    fetchHeatmap();
  }, []);

  // Build lookup map
  const cellMap = new Map<string, HeatmapCell>();
  cells.forEach((c) => cellMap.set(`${c.day}-${c.hour}`, c));

  const maxCalls = Math.max(...cells.map((c) => c.call_count), 1);

  if (isLoading) {
    return (
      <div className="bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 rounded-xl p-6">
        <h2 className="text-lg font-semibold text-slate-900 dark:text-white mb-4">
          Usage Heatmap
        </h2>
        <div className="flex items-center justify-center py-8">
          <div className="inline-block animate-spin rounded-full h-6 w-6 border-2 border-slate-300 border-t-slate-900 dark:border-slate-600 dark:border-t-white" />
        </div>
      </div>
    );
  }

  return (
    <div className="bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 rounded-xl p-6 relative">
      <h2 className="text-lg font-semibold text-slate-900 dark:text-white mb-4">
        Usage Heatmap
      </h2>
      <p className="text-xs text-slate-500 dark:text-slate-400 mb-4">
        API call density over the last 30 days (day × hour)
      </p>

      <div className="overflow-x-auto">
        <div className="inline-block min-w-full">
          {/* Hour labels */}
          <div className="flex ml-10 mb-1">
            {HOUR_LABELS.map((h) => (
              <div
                key={h}
                className="text-[10px] text-slate-400 dark:text-slate-500 text-center"
                style={{ width: '24px', minWidth: '24px' }}
              >
                {h % 3 === 0 ? h : ''}
              </div>
            ))}
          </div>

          {/* Grid rows */}
          {DAY_LABELS.map((dayLabel, dayIdx) => (
            <div key={dayIdx} className="flex items-center mb-[2px]">
              <span className="text-xs text-slate-500 dark:text-slate-400 w-10 text-right pr-2 shrink-0">
                {dayLabel}
              </span>
              {HOUR_LABELS.map((hour) => {
                const cell = cellMap.get(`${dayIdx}-${hour}`);
                const calls = cell?.call_count || 0;
                const cost = cell?.cost_usd || 0;

                return (
                  <div
                    key={hour}
                    className={`rounded-sm cursor-pointer transition-all hover:ring-1 hover:ring-slate-400 ${getHeatColor(
                      calls,
                      maxCalls
                    )}`}
                    style={{
                      width: '22px',
                      height: '22px',
                      minWidth: '22px',
                      margin: '1px',
                    }}
                    onMouseEnter={(e) => {
                      const rect = e.currentTarget.getBoundingClientRect();
                      setTooltip({
                        x: rect.left + rect.width / 2,
                        y: rect.top - 8,
                        day: dayIdx,
                        hour,
                        calls,
                        cost,
                      });
                    }}
                    onMouseLeave={() => setTooltip(null)}
                  />
                );
              })}
            </div>
          ))}
        </div>
      </div>

      {/* Legend */}
      <div className="flex items-center gap-2 mt-4 text-xs text-slate-500 dark:text-slate-400">
        <span>Less</span>
        <div className="w-4 h-4 rounded-sm bg-slate-100 dark:bg-slate-800" />
        <div className="w-4 h-4 rounded-sm bg-blue-100 dark:bg-blue-900/30" />
        <div className="w-4 h-4 rounded-sm bg-blue-200 dark:bg-blue-800/40" />
        <div className="w-4 h-4 rounded-sm bg-blue-300 dark:bg-blue-700/50" />
        <div className="w-4 h-4 rounded-sm bg-blue-400 dark:bg-blue-600/60" />
        <div className="w-4 h-4 rounded-sm bg-blue-500 dark:bg-blue-500/70" />
        <span>More</span>
      </div>

      {/* Tooltip */}
      {tooltip && (
        <div
          className="fixed z-50 px-3 py-2 bg-slate-900 dark:bg-slate-700 text-white text-xs rounded-lg shadow-lg pointer-events-none"
          style={{
            left: tooltip.x,
            top: tooltip.y,
            transform: 'translate(-50%, -100%)',
          }}
        >
          <p className="font-medium">
            {DAY_LABELS[tooltip.day]} {tooltip.hour}:00
          </p>
          <p>
            {tooltip.calls} call{tooltip.calls !== 1 ? 's' : ''} · $
            {tooltip.cost.toFixed(4)}
          </p>
        </div>
      )}
    </div>
  );
}
