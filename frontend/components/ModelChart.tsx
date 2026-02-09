/**
 * ModelChart Component
 * @description Bar chart showing cost breakdown by model using recharts
 */

'use client';

import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  Cell,
} from 'recharts';
import { ModelCost } from '@/types';
import { formatCurrency, getModelColor } from '@/lib/utils';

export interface ModelChartProps {
  data: ModelCost[];
}

export default function ModelChart({ data }: ModelChartProps) {
  if (!data || data.length === 0) {
    return (
      <div className="flex items-center justify-center h-64 text-slate-400">
        No data available
      </div>
    );
  }

  // Sort by cost descending
  const sortedData = [...data].sort((a, b) => b.cost_usd - a.cost_usd);

  return (
    <div className="w-full h-80">
      <ResponsiveContainer width="100%" height="100%">
        <BarChart
          data={sortedData}
          layout="vertical"
          margin={{ top: 5, right: 30, left: 80, bottom: 5 }}
        >
          <CartesianGrid
            strokeDasharray="3 3"
            horizontal={true}
            vertical={false}
            stroke="rgba(148, 163, 184, 0.15)"
          />
          <XAxis
            type="number"
            tickFormatter={(value) => `$${value.toFixed(0)}`}
            stroke="#94a3b8"
            fontSize={12}
            axisLine={false}
            tickLine={false}
          />
          <YAxis
            type="category"
            dataKey="model"
            stroke="#94a3b8"
            fontSize={12}
            axisLine={false}
            tickLine={false}
            width={75}
          />
          <Tooltip
            content={({ active, payload }) => {
              if (active && payload && payload.length) {
                const item = payload[0].payload as ModelCost;
                return (
                  <div className="bg-slate-900 dark:bg-slate-800 text-white px-3 py-2 rounded-lg shadow-lg text-sm">
                    <p className="font-medium">{item.model}</p>
                    <p className="text-slate-300">{formatCurrency(item.cost_usd)}</p>
                    <p className="text-slate-400 text-xs">{item.call_count.toLocaleString()} calls</p>
                  </div>
                );
              }
              return null;
            }}
          />
          <Bar
            dataKey="cost_usd"
            radius={[0, 4, 4, 0]}
            maxBarSize={32}
          >
            {sortedData.map((entry, index) => (
              <Cell key={`cell-${index}`} fill={getModelColor(entry.model)} />
            ))}
          </Bar>
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}
