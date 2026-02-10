/**
 * Tests for the API client (frontend/lib/api.ts)
 *
 * Verifies auth header injection, 401 auto-logout, downloadExport uses
 * fetch+blob (not URL tokens), and query string construction.
 */

// Mock next/navigation before importing anything
jest.mock('next/navigation', () => ({
  useRouter: () => ({ push: jest.fn(), replace: jest.fn() }),
}));

import {
  isAuthenticated,
  getUser,
  downloadExport,
  getLogs,
} from '@/lib/api';

// ---------------------------------------------------------------------------
// Setup
// ---------------------------------------------------------------------------

const mockFetch = jest.fn();
global.fetch = mockFetch;

// Mock URL.createObjectURL and revokeObjectURL
global.URL.createObjectURL = jest.fn(() => 'blob:mock-url');
global.URL.revokeObjectURL = jest.fn();

beforeEach(() => {
  jest.clearAllMocks();
  (localStorage.getItem as jest.Mock).mockReset();
  (localStorage.setItem as jest.Mock).mockReset();
  (localStorage.removeItem as jest.Mock).mockReset();
});

// ---------------------------------------------------------------------------
// Auth header tests
// ---------------------------------------------------------------------------

describe('API client auth headers', () => {
  it('should add Authorization header when token exists', async () => {
    (localStorage.getItem as jest.Mock).mockReturnValue('test-jwt-token');

    mockFetch.mockResolvedValueOnce({
      ok: true,
      status: 200,
      json: async () => ({ logs: [], total: 0, page: 1, page_size: 50, has_more: false }),
    });

    await getLogs({});

    expect(mockFetch).toHaveBeenCalledTimes(1);
    const [, options] = mockFetch.mock.calls[0];
    expect(options.headers['Authorization']).toBe('Bearer test-jwt-token');
  });

  it('should not have Authorization header when no token', async () => {
    (localStorage.getItem as jest.Mock).mockReturnValue(null);

    mockFetch.mockResolvedValueOnce({
      ok: true,
      status: 200,
      json: async () => ({ logs: [], total: 0, page: 1, page_size: 50, has_more: false }),
    });

    await getLogs({});

    const [, options] = mockFetch.mock.calls[0];
    expect(options.headers['Authorization']).toBeUndefined();
  });
});

// ---------------------------------------------------------------------------
// 401 auto-logout
// ---------------------------------------------------------------------------

describe('Auto-logout on 401', () => {
  it('should clear localStorage on 401 response', async () => {
    (localStorage.getItem as jest.Mock).mockReturnValue('expired-token');

    // Mock window.location
    const originalLocation = window.location;
    Object.defineProperty(window, 'location', {
      writable: true,
      value: { href: '' },
    });

    mockFetch.mockResolvedValueOnce({
      ok: false,
      status: 401,
      json: async () => ({ detail: 'Unauthorized' }),
    });

    await expect(getLogs({})).rejects.toThrow('Session expired');

    expect(localStorage.removeItem).toHaveBeenCalledWith('llmlab_token');
    expect(localStorage.removeItem).toHaveBeenCalledWith('llmlab_user');

    // Restore
    Object.defineProperty(window, 'location', {
      writable: true,
      value: originalLocation,
    });
  });
});

// ---------------------------------------------------------------------------
// downloadExport uses fetch + blob (not URL tokens)
// ---------------------------------------------------------------------------

describe('downloadExport', () => {
  it('should use fetch with Authorization header, not URL token', async () => {
    (localStorage.getItem as jest.Mock).mockReturnValue('my-jwt-token');

    const mockBlob = new Blob(['csv,data'], { type: 'text/csv' });

    mockFetch.mockResolvedValueOnce({
      ok: true,
      status: 200,
      blob: async () => mockBlob,
      headers: new Headers({
        'Content-Disposition': 'attachment; filename=export.csv',
      }),
    });

    // Mock DOM methods for download
    const mockLink = { href: '', download: '', click: jest.fn() };
    jest.spyOn(document, 'createElement').mockReturnValue(mockLink as any);
    jest.spyOn(document.body, 'appendChild').mockImplementation(() => mockLink as any);
    jest.spyOn(document.body, 'removeChild').mockImplementation(() => mockLink as any);

    await downloadExport('csv', { provider: 'openai' });

    // Verify fetch was called with Authorization header
    expect(mockFetch).toHaveBeenCalledTimes(1);
    const [url, options] = mockFetch.mock.calls[0];
    expect(url).toContain('/api/v1/export/csv');
    expect(url).toContain('provider=openai');
    // Token should be in header, NOT in URL
    expect(url).not.toContain('token=');
    expect(options.headers['Authorization']).toBe('Bearer my-jwt-token');

    // Verify blob download triggered
    expect(mockLink.click).toHaveBeenCalled();
  });
});

// ---------------------------------------------------------------------------
// getLogs query string construction
// ---------------------------------------------------------------------------

describe('getLogs query string', () => {
  it('should build correct query string from params', async () => {
    (localStorage.getItem as jest.Mock).mockReturnValue('token');

    mockFetch.mockResolvedValueOnce({
      ok: true,
      status: 200,
      json: async () => ({ logs: [], total: 0, page: 1, page_size: 50, has_more: false }),
    });

    await getLogs({ provider: 'openai', page: 2, sort_by: 'cost_usd' });

    const [url] = mockFetch.mock.calls[0];
    expect(url).toContain('provider=openai');
    expect(url).toContain('page=2');
    expect(url).toContain('sort_by=cost_usd');
  });

  it('should omit undefined/empty params', async () => {
    (localStorage.getItem as jest.Mock).mockReturnValue('token');

    mockFetch.mockResolvedValueOnce({
      ok: true,
      status: 200,
      json: async () => ({ logs: [], total: 0, page: 1, page_size: 50, has_more: false }),
    });

    await getLogs({ provider: '', model: undefined });

    const [url] = mockFetch.mock.calls[0];
    expect(url).not.toContain('provider=');
    expect(url).not.toContain('model=');
  });
});
