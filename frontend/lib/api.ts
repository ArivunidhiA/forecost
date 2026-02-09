/**
 * LLMLab API Client
 * @description HTTP client with JWT auth, auto-logout on 401, and error handling
 */

import {
  Stats,
  APIKey,
  APIKeyListResponse,
  User,
  AuthResponse,
  APIError,
  Budget,
  BudgetListResponse,
  RecommendationsResponse,
  HeatmapResponse,
  ComparisonResponse,
  Webhook,
  WebhookListResponse,
  UsageLogsResponse,
  Tag,
  TagListResponse,
  ForecastData,
  AnomalyResponse,
} from '@/types';

const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';

/**
 * Get the stored JWT token
 */
function getToken(): string | null {
  if (typeof window === 'undefined') return null;
  return localStorage.getItem('llmlab_token');
}

/**
 * Store JWT token
 */
export function setToken(token: string): void {
  localStorage.setItem('llmlab_token', token);
}

/**
 * Remove JWT token and redirect to login
 */
export function logout(): void {
  localStorage.removeItem('llmlab_token');
  localStorage.removeItem('llmlab_user');
  window.location.href = '/';
}

/**
 * Store user data
 */
export function setUser(user: User): void {
  localStorage.setItem('llmlab_user', JSON.stringify(user));
}

/**
 * Get stored user data
 */
export function getUser(): User | null {
  if (typeof window === 'undefined') return null;
  const data = localStorage.getItem('llmlab_user');
  return data ? JSON.parse(data) : null;
}

/**
 * Check if user is authenticated
 */
export function isAuthenticated(): boolean {
  return !!getToken();
}

/**
 * API fetch wrapper with auth and error handling
 */
async function apiFetch<T>(
  endpoint: string,
  options: RequestInit = {}
): Promise<T> {
  const token = getToken();

  const headers: HeadersInit = {
    'Content-Type': 'application/json',
    ...options.headers,
  };

  if (token) {
    (headers as Record<string, string>)['Authorization'] = `Bearer ${token}`;
  }

  const response = await fetch(`${API_BASE_URL}${endpoint}`, {
    ...options,
    headers,
  });

  // Auto-logout on 401
  if (response.status === 401) {
    logout();
    throw new Error('Session expired. Please log in again.');
  }

  if (!response.ok) {
    const error: APIError = await response.json().catch(() => ({
      detail: 'An error occurred',
    }));
    throw new Error(error.detail || `HTTP ${response.status}`);
  }

  return response.json();
}

// =============================================================================
// AUTHENTICATION
// =============================================================================

/**
 * Exchange GitHub OAuth code for JWT token
 */
export async function githubCallback(code: string): Promise<AuthResponse> {
  return apiFetch<AuthResponse>('/auth/github', {
    method: 'POST',
    body: JSON.stringify({ code }),
  });
}

/**
 * Get current user info
 */
export async function getMe(): Promise<User> {
  return apiFetch<User>('/api/v1/me');
}

// =============================================================================
// API KEYS
// =============================================================================

/**
 * Get user's API keys
 */
export async function getKeys(): Promise<APIKey[]> {
  const response = await apiFetch<APIKeyListResponse>('/api/v1/keys');
  return response.keys;
}

/**
 * Create a new API key
 */
export async function createKey(provider: string, apiKey: string): Promise<APIKey> {
  return apiFetch<APIKey>('/api/v1/keys', {
    method: 'POST',
    body: JSON.stringify({ provider, api_key: apiKey }),
  });
}

/**
 * Delete an API key
 */
export async function deleteKey(keyId: string): Promise<void> {
  await apiFetch<void>(`/api/v1/keys/${keyId}`, {
    method: 'DELETE',
  });
}

// =============================================================================
// STATS
// =============================================================================

/**
 * Get user's cost statistics
 */
export async function getStats(period: string = 'month'): Promise<Stats> {
  return apiFetch<Stats>(`/api/v1/stats?period=${period}`);
}

// =============================================================================
// BUDGETS
// =============================================================================

/**
 * Get user's budgets
 */
export async function getBudgets(): Promise<Budget[]> {
  const response = await apiFetch<BudgetListResponse>('/api/v1/budgets');
  return response.budgets;
}

/**
 * Create or update a budget
 */
export async function createBudget(
  amount_usd: number,
  alert_threshold: number = 80.0
): Promise<Budget> {
  return apiFetch<Budget>('/api/v1/budgets', {
    method: 'POST',
    body: JSON.stringify({ amount_usd, alert_threshold }),
  });
}

/**
 * Delete a budget
 */
export async function deleteBudget(budgetId: string): Promise<void> {
  await apiFetch<void>(`/api/v1/budgets/${budgetId}`, {
    method: 'DELETE',
  });
}

// =============================================================================
// RECOMMENDATIONS
// =============================================================================

/**
 * Get cost optimization recommendations
 */
export async function getRecommendations(): Promise<RecommendationsResponse> {
  return apiFetch<RecommendationsResponse>('/api/v1/recommendations');
}

// =============================================================================
// HEATMAP
// =============================================================================

/**
 * Get usage heatmap data (day x hour)
 */
export async function getHeatmap(): Promise<HeatmapResponse> {
  return apiFetch<HeatmapResponse>('/api/v1/stats/heatmap');
}

// =============================================================================
// PROVIDER COMPARISON
// =============================================================================

/**
 * Get provider cost comparison data
 */
export async function getComparison(): Promise<ComparisonResponse> {
  return apiFetch<ComparisonResponse>('/api/v1/stats/comparison');
}

// =============================================================================
// WEBHOOKS
// =============================================================================

/**
 * Get user's webhooks
 */
export async function getWebhooks(): Promise<Webhook[]> {
  const response = await apiFetch<WebhookListResponse>('/api/v1/webhooks');
  return response.webhooks;
}

/**
 * Create a new webhook
 */
export async function createWebhook(
  url: string,
  event_type: string
): Promise<Webhook> {
  return apiFetch<Webhook>('/api/v1/webhooks', {
    method: 'POST',
    body: JSON.stringify({ url, event_type }),
  });
}

/**
 * Delete a webhook
 */
export async function deleteWebhook(webhookId: string): Promise<void> {
  await apiFetch<void>(`/api/v1/webhooks/${webhookId}`, {
    method: 'DELETE',
  });
}

// =============================================================================
// USAGE LOGS
// =============================================================================

export interface LogsParams {
  page?: number;
  page_size?: number;
  provider?: string;
  model?: string;
  tag?: string;
  cache_hit?: boolean;
  date_from?: string;
  date_to?: string;
  sort_by?: string;
  sort_order?: string;
}

export async function getLogs(params: LogsParams = {}): Promise<UsageLogsResponse> {
  const searchParams = new URLSearchParams();
  Object.entries(params).forEach(([key, value]) => {
    if (value !== undefined && value !== null && value !== '') {
      searchParams.set(key, String(value));
    }
  });
  const qs = searchParams.toString();
  return apiFetch<UsageLogsResponse>(`/api/v1/logs${qs ? `?${qs}` : ''}`);
}

// =============================================================================
// TAGS
// =============================================================================

export async function getTags(): Promise<Tag[]> {
  const response = await apiFetch<TagListResponse>('/api/v1/tags');
  return response.tags;
}

export async function createTag(name: string, color: string = '#6366f1'): Promise<Tag> {
  return apiFetch<Tag>('/api/v1/tags', {
    method: 'POST',
    body: JSON.stringify({ name, color }),
  });
}

export async function deleteTag(tagId: string): Promise<void> {
  await apiFetch<void>(`/api/v1/tags/${tagId}`, { method: 'DELETE' });
}

export async function attachTags(logId: string, tagIds: string[]): Promise<void> {
  await apiFetch<void>(`/api/v1/logs/${logId}/tags`, {
    method: 'POST',
    body: JSON.stringify({ tag_ids: tagIds }),
  });
}

// =============================================================================
// FORECAST
// =============================================================================

export async function getForecast(): Promise<ForecastData> {
  return apiFetch<ForecastData>('/api/v1/stats/forecast');
}

// =============================================================================
// ANOMALIES
// =============================================================================

export async function getAnomalies(): Promise<AnomalyResponse> {
  return apiFetch<AnomalyResponse>('/api/v1/stats/anomalies');
}

// =============================================================================
// DATA EXPORT
// =============================================================================

/**
 * Download export file via fetch with proper Authorization header.
 * Uses Blob download to avoid exposing JWT tokens in URLs.
 */
export async function downloadExport(format: 'csv' | 'json', params: LogsParams = {}): Promise<void> {
  const searchParams = new URLSearchParams();
  Object.entries(params).forEach(([key, value]) => {
    if (value !== undefined && value !== null && value !== '') {
      searchParams.set(key, String(value));
    }
  });
  const qs = searchParams.toString();
  const token = getToken();

  const headers: Record<string, string> = {};
  if (token) {
    headers['Authorization'] = `Bearer ${token}`;
  }

  const response = await fetch(
    `${API_BASE_URL}/api/v1/export/${format}${qs ? `?${qs}` : ''}`,
    { headers }
  );

  if (response.status === 401) {
    logout();
    throw new Error('Session expired. Please log in again.');
  }

  if (!response.ok) {
    throw new Error(`Export failed: HTTP ${response.status}`);
  }

  const blob = await response.blob();
  const url = window.URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;

  // Extract filename from Content-Disposition header or use default
  const disposition = response.headers.get('Content-Disposition');
  const filenameMatch = disposition?.match(/filename=(.+)/);
  a.download = filenameMatch ? filenameMatch[1] : `llmlab_export.${format}`;

  document.body.appendChild(a);
  a.click();
  window.URL.revokeObjectURL(url);
  document.body.removeChild(a);
}

// =============================================================================
// EXPORT
// =============================================================================

export const api = {
  githubCallback,
  getMe,
  getStats,
  getKeys,
  createKey,
  deleteKey,
  getBudgets,
  createBudget,
  deleteBudget,
  getRecommendations,
  getHeatmap,
  getComparison,
  getWebhooks,
  createWebhook,
  deleteWebhook,
  getLogs,
  getTags,
  createTag,
  deleteTag,
  attachTags,
  getForecast,
  getAnomalies,
  downloadExport,
};

export default api;
