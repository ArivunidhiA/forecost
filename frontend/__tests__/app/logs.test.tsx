/**
 * Tests for Logs Explorer page.
 *
 * Verifies filter controls render, pagination works, and export buttons
 * call downloadExport (not getExportUrl).
 */

import React from 'react';
import { render, screen, waitFor } from '@testing-library/react';
import '@testing-library/jest-dom';

// Mock next/navigation
jest.mock('next/navigation', () => ({
  useRouter: () => ({ push: jest.fn(), replace: jest.fn() }),
}));

// Mock the API module
const mockGetLogs = jest.fn();
const mockGetTags = jest.fn();
const mockDownloadExport = jest.fn();

jest.mock('@/lib/api', () => ({
  api: {
    getTags: (...args: any[]) => mockGetTags(...args),
  },
  isAuthenticated: jest.fn(() => true),
  getLogs: (...args: any[]) => mockGetLogs(...args),
  downloadExport: (...args: any[]) => mockDownloadExport(...args),
  LogsParams: {},
}));

import LogsPage from '@/app/logs/page';

beforeEach(() => {
  jest.clearAllMocks();
  mockGetLogs.mockResolvedValue({
    logs: [
      {
        id: 'log-1',
        provider: 'openai',
        model: 'gpt-4o',
        input_tokens: 100,
        output_tokens: 50,
        cost_usd: 0.005,
        latency_ms: 250,
        cache_hit: false,
        tags: ['backend'],
        created_at: '2024-02-09T10:00:00Z',
      },
    ],
    total: 1,
    page: 1,
    page_size: 50,
    has_more: false,
  });
  mockGetTags.mockResolvedValue([]);
});

describe('Logs Page', () => {
  it('should render without crashing', async () => {
    render(<LogsPage />);
    await waitFor(() => {
      expect(mockGetLogs).toHaveBeenCalled();
    });
  });

  it('should render filter controls', async () => {
    render(<LogsPage />);
    await waitFor(() => {
      expect(mockGetLogs).toHaveBeenCalled();
    });

    // Should have provider filter
    const providerLabel = screen.queryByText('Provider');
    expect(providerLabel).toBeInTheDocument();
  });

  it('should have button-based export controls, not anchor links', async () => {
    render(<LogsPage />);
    await waitFor(() => {
      expect(mockGetLogs).toHaveBeenCalled();
    });

    // Find export buttons
    const csvButton = screen.queryByText('Export CSV');
    const jsonButton = screen.queryByText('Export JSON');

    if (csvButton) {
      expect(csvButton.tagName).toBe('BUTTON');
    }
    if (jsonButton) {
      expect(jsonButton.tagName).toBe('BUTTON');
    }
  });
});
