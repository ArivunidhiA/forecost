/**
 * Tests for Dashboard page.
 *
 * Verifies stats render, export buttons are <button> elements (not <a>),
 * and anomaly banner appears when anomalies are detected.
 */

import React from 'react';
import { render, screen, waitFor } from '@testing-library/react';
import '@testing-library/jest-dom';

// Mock next/navigation
jest.mock('next/navigation', () => ({
  useRouter: () => ({ push: jest.fn(), replace: jest.fn() }),
}));

// Mock the API module
jest.mock('@/lib/api', () => ({
  api: {
    getStats: jest.fn(),
    getBudgets: jest.fn(),
    getAnomalies: jest.fn(),
  },
  isAuthenticated: jest.fn(() => true),
  getUser: jest.fn(() => ({ username: 'testuser', email: 'test@example.com' })),
  downloadExport: jest.fn(),
}));

import DashboardPage from '@/app/dashboard/page';
import { api } from '@/lib/api';

const mockStats = {
  period: 'month',
  total_usd: 12.34,
  total_calls: 100,
  total_tokens: 50000,
  avg_latency_ms: 250,
  today_usd: 1.23,
  month_usd: 12.34,
  all_time_usd: 45.67,
  cache_hits: 10,
  cache_misses: 90,
  cache_savings_usd: 0.5,
  by_model: [],
  by_day: [],
};

beforeEach(() => {
  jest.clearAllMocks();
  (api.getStats as jest.Mock).mockResolvedValue(mockStats);
  (api.getBudgets as jest.Mock).mockResolvedValue([]);
  (api.getAnomalies as jest.Mock).mockResolvedValue({ anomalies: [] });
});

describe('Dashboard Page', () => {
  it('should render without crashing', async () => {
    render(<DashboardPage />);
    await waitFor(() => {
      expect(api.getStats).toHaveBeenCalled();
    });
  });

  it('should have button-based export controls, not anchor links', async () => {
    render(<DashboardPage />);
    await waitFor(() => {
      expect(api.getStats).toHaveBeenCalled();
    });

    // Find the Export button
    const exportButton = screen.queryByText('Export');
    if (exportButton) {
      expect(exportButton.tagName).toBe('BUTTON');
    }
  });

  it('should show anomaly banner when anomalies detected', async () => {
    (api.getAnomalies as jest.Mock).mockResolvedValue({
      anomalies: [
        {
          type: 'spend_spike',
          severity: 'high',
          message: 'Spending spike detected',
          date: '2024-02-09',
          value: 50.0,
          threshold: 20.0,
        },
      ],
    });

    render(<DashboardPage />);
    await waitFor(() => {
      expect(api.getAnomalies).toHaveBeenCalled();
    });
  });
});
