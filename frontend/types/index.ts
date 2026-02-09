/**
 * LLMLab Frontend Types
 * @description Core TypeScript interfaces aligned with the backend API schemas
 */

export interface User {
  id: string;
  github_id: number;
  email: string;
  username?: string;
  avatar_url?: string;
  created_at: string;
}

export interface APIKey {
  id: string;
  provider: string;
  proxy_key: string;
  created_at: string;
  last_used_at: string | null;
  is_active: boolean;
}

export interface APIKeyListResponse {
  keys: APIKey[];
}

export interface DailyCost {
  date: string;
  cost_usd: number;
  call_count: number;
}

export interface ModelCost {
  model: string;
  provider: string;
  total_tokens: number;
  cost_usd: number;
  call_count: number;
  avg_latency_ms?: number | null;
}

export interface Stats {
  period: string;
  total_usd: number;
  total_calls: number;
  total_tokens: number;
  avg_latency_ms: number;
  today_usd: number;
  month_usd: number;
  all_time_usd: number;
  cache_hits: number;
  cache_misses: number;
  cache_savings_usd: number;
  by_model: ModelCost[];
  by_day: DailyCost[];
}

export interface AuthResponse {
  user_id: string;
  email: string;
  username?: string;
  token: string;
  expires_in: number;
}

export interface Budget {
  id: string;
  amount_usd: number;
  period: string;
  alert_threshold: number;
  current_spend: number;
  status: string;
  created_at: string;
  updated_at: string;
}

export interface BudgetListResponse {
  budgets: Budget[];
}

export interface BudgetAlert {
  budget_id: string;
  amount_usd: number;
  current_spend: number;
  threshold: number;
  status: 'ok' | 'warning' | 'exceeded';
}

export interface RecommendationItem {
  type: string;
  title: string;
  description: string;
  potential_savings: number;
  priority: string;
  current_model?: string;
  suggested_model?: string;
}

export interface RecommendationsResponse {
  recommendations: RecommendationItem[];
  total_potential_savings: number;
  analyzed_period_days: number;
}

export interface HeatmapCell {
  day: number;
  hour: number;
  call_count: number;
  cost_usd: number;
}

export interface HeatmapResponse {
  cells: HeatmapCell[];
}

export interface ComparisonAlternative {
  provider: string;
  model: string;
  estimated_cost: number;
}

export interface ComparisonItem {
  model: string;
  provider: string;
  actual_cost: number;
  input_tokens: number;
  output_tokens: number;
  alternatives: ComparisonAlternative[];
}

export interface ComparisonResponse {
  comparisons: ComparisonItem[];
  current_total: number;
  cheapest_total: number;
}

export interface Webhook {
  id: string;
  url: string;
  event_type: string;
  is_active: boolean;
  created_at: string;
}

export interface WebhookListResponse {
  webhooks: Webhook[];
}

export interface APIError {
  detail: string;
  status_code?: number;
}

// =============================================================================
// USAGE LOGS
// =============================================================================

export interface UsageLogEntry {
  id: string;
  provider: string;
  model: string;
  input_tokens: number;
  output_tokens: number;
  cost_usd: number;
  latency_ms: number | null;
  cache_hit: boolean;
  tags: string[];
  created_at: string;
}

export interface UsageLogsResponse {
  logs: UsageLogEntry[];
  total: number;
  page: number;
  page_size: number;
  has_more: boolean;
}

// =============================================================================
// TAGS
// =============================================================================

export interface Tag {
  id: string;
  name: string;
  color: string;
  usage_count: number;
  created_at: string;
}

export interface TagListResponse {
  tags: Tag[];
}

// =============================================================================
// FORECAST
// =============================================================================

export interface ForecastData {
  predicted_next_month_usd: number;
  daily_average_usd: number;
  trend: 'increasing' | 'decreasing' | 'stable';
  trend_pct_change: number;
  confidence: 'low' | 'medium' | 'high';
  projected_daily: DailyCost[];
}

// =============================================================================
// ANOMALY
// =============================================================================

export interface AnomalyEvent {
  type: string;
  message: string;
  severity: 'info' | 'warning' | 'critical';
  current_value: number;
  expected_value: number;
  deviation_factor: number;
  detected_at: string;
}

export interface AnomalyResponse {
  anomalies: AnomalyEvent[];
  has_active_anomaly: boolean;
}
