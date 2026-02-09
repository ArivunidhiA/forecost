"""
Pydantic schemas for request/response validation.

All API inputs and outputs are validated through these schemas.
"""

from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, Field


# =============================================================================
# AUTHENTICATION
# =============================================================================


class GitHubAuthRequest(BaseModel):
    """Request to exchange GitHub OAuth code for token."""

    code: str = Field(..., description="GitHub OAuth authorization code")


class AuthResponse(BaseModel):
    """Response after successful authentication."""

    user_id: str = Field(..., description="User's unique identifier")
    email: str = Field(..., description="User's email address")
    username: Optional[str] = Field(None, description="GitHub username")
    token: str = Field(..., description="JWT access token")
    expires_in: int = Field(..., description="Token expiry in seconds")


class UserResponse(BaseModel):
    """User profile information."""

    id: str
    github_id: int
    email: str
    username: Optional[str]
    avatar_url: Optional[str]
    created_at: datetime

    class Config:
        from_attributes = True


# =============================================================================
# API KEYS
# =============================================================================


class ApiKeyCreate(BaseModel):
    """Request to store a new API key."""

    provider: str = Field(
        ...,
        description="Provider name",
        pattern="^(openai|anthropic|google)$",
    )
    api_key: str = Field(
        ...,
        min_length=10,
        description="Your real API key for the provider",
    )


class ApiKeyResponse(BaseModel):
    """Response after creating/retrieving API key."""

    id: str = Field(..., description="Key identifier")
    provider: str = Field(..., description="Provider name")
    proxy_key: str = Field(..., description="Proxy key to use in your apps")
    created_at: datetime = Field(..., description="Creation timestamp")
    last_used_at: Optional[datetime] = Field(None, description="Last usage timestamp")
    is_active: bool = Field(..., description="Whether key is active")

    class Config:
        from_attributes = True


class ApiKeyListResponse(BaseModel):
    """List of user's API keys."""

    keys: List[ApiKeyResponse]


# =============================================================================
# PROXY
# =============================================================================


class ProxyResponse(BaseModel):
    """Generic proxy response wrapper."""

    success: bool
    data: Optional[dict] = None
    error: Optional[str] = None


# =============================================================================
# STATS
# =============================================================================


class ModelCost(BaseModel):
    """Cost breakdown for a single model."""

    model: str = Field(..., description="Model name")
    provider: str = Field(..., description="Provider name")
    total_tokens: int = Field(..., description="Total tokens used")
    cost_usd: float = Field(..., description="Total cost in USD")
    call_count: int = Field(..., description="Number of API calls")
    avg_latency_ms: Optional[float] = Field(None, description="Average latency in ms")


class DailyCost(BaseModel):
    """Cost for a single day."""

    date: str = Field(..., description="Date in YYYY-MM-DD format")
    cost_usd: float = Field(..., description="Total cost for the day")
    call_count: int = Field(..., description="Number of API calls")


class StatsResponse(BaseModel):
    """User's cost statistics."""

    period: str = Field(..., description="Time period (today, week, month, all)")
    total_usd: float = Field(..., description="Total cost in USD")
    total_calls: int = Field(..., description="Total number of API calls")
    total_tokens: int = Field(..., description="Total tokens used")
    avg_latency_ms: float = Field(0.0, description="Average latency in ms")
    today_usd: float = Field(0.0, description="Today's cost in USD")
    month_usd: float = Field(0.0, description="This month's cost in USD")
    all_time_usd: float = Field(0.0, description="All-time cost in USD")
    cache_hits: int = Field(0, description="Total cache hits")
    cache_misses: int = Field(0, description="Total cache misses")
    cache_savings_usd: float = Field(0.0, description="Total money saved by caching")
    by_model: List[ModelCost] = Field(..., description="Cost breakdown by model")
    by_day: List[DailyCost] = Field(..., description="Cost breakdown by day")


# =============================================================================
# BUDGETS
# =============================================================================


class BudgetCreate(BaseModel):
    """Request to create or update a budget."""

    amount_usd: float = Field(..., gt=0, description="Monthly budget amount in USD")
    period: str = Field(default="monthly", description="Budget period")
    alert_threshold: float = Field(default=80.0, ge=0, le=100, description="Alert threshold percentage")


class BudgetResponse(BaseModel):
    """Budget information."""

    id: str = Field(..., description="Budget identifier")
    amount_usd: float = Field(..., description="Monthly budget amount in USD")
    period: str = Field(..., description="Budget period")
    alert_threshold: float = Field(..., description="Alert threshold percentage")
    current_spend: float = Field(0.0, description="Current spend in this period")
    status: str = Field("ok", description="Budget status: ok, warning, exceeded")
    created_at: datetime = Field(..., description="Creation timestamp")
    updated_at: datetime = Field(..., description="Last update timestamp")

    class Config:
        from_attributes = True


class BudgetListResponse(BaseModel):
    """List of user's budgets."""

    budgets: List[BudgetResponse]


# =============================================================================
# RECOMMENDATIONS
# =============================================================================


class RecommendationItem(BaseModel):
    """A single cost optimization recommendation."""

    type: str = Field(..., description="Recommendation type")
    title: str = Field(..., description="Short title")
    description: str = Field(..., description="Detailed description")
    potential_savings: float = Field(0.0, description="Estimated monthly savings in USD")
    priority: str = Field("medium", description="Priority: low, medium, high")
    current_model: Optional[str] = Field(None, description="Current model (for model-switch recs)")
    suggested_model: Optional[str] = Field(None, description="Suggested model (for model-switch recs)")


class RecommendationsResponse(BaseModel):
    """Cost optimization recommendations."""

    recommendations: List[RecommendationItem] = Field(default_factory=list)
    total_potential_savings: float = Field(0.0, description="Total estimated monthly savings")
    analyzed_period_days: int = Field(30, description="Number of days analyzed")


# =============================================================================
# HEATMAP
# =============================================================================


class HeatmapCell(BaseModel):
    """A single cell in the usage heatmap."""

    day: int = Field(..., ge=0, le=6, description="Day of week (0=Monday, 6=Sunday)")
    hour: int = Field(..., ge=0, le=23, description="Hour of day (0-23)")
    call_count: int = Field(0, description="Number of API calls")
    cost_usd: float = Field(0.0, description="Total cost in USD")


class HeatmapResponse(BaseModel):
    """Usage heatmap data."""

    cells: List[HeatmapCell] = Field(default_factory=list)


# =============================================================================
# PROVIDER COMPARISON
# =============================================================================


class ComparisonAlternative(BaseModel):
    """An alternative provider/model option."""

    provider: str = Field(..., description="Provider name")
    model: str = Field(..., description="Model name")
    estimated_cost: float = Field(..., description="Estimated cost for same usage")


class ComparisonItem(BaseModel):
    """Comparison for a single model the user has used."""

    model: str = Field(..., description="Current model name")
    provider: str = Field(..., description="Current provider name")
    actual_cost: float = Field(..., description="Actual cost incurred")
    input_tokens: int = Field(0, description="Total input tokens")
    output_tokens: int = Field(0, description="Total output tokens")
    alternatives: List[ComparisonAlternative] = Field(default_factory=list)


class ComparisonResponse(BaseModel):
    """Provider cost comparison data."""

    comparisons: List[ComparisonItem] = Field(default_factory=list)
    current_total: float = Field(0.0, description="Total current cost")
    cheapest_total: float = Field(0.0, description="Total cost with cheapest options")


# =============================================================================
# WEBHOOKS
# =============================================================================


class WebhookCreate(BaseModel):
    """Request to register a webhook."""

    url: str = Field(..., min_length=10, description="Webhook URL to POST to")
    event_type: str = Field(
        ...,
        description="Event type",
        pattern="^(budget_warning|budget_exceeded|anomaly)$",
    )


class WebhookResponse(BaseModel):
    """Webhook information."""

    id: str = Field(..., description="Webhook identifier")
    url: str = Field(..., description="Webhook URL")
    event_type: str = Field(..., description="Event type")
    is_active: bool = Field(..., description="Whether webhook is active")
    created_at: datetime = Field(..., description="Creation timestamp")

    class Config:
        from_attributes = True


class WebhookListResponse(BaseModel):
    """List of user's webhooks."""

    webhooks: List[WebhookResponse]


# =============================================================================
# USAGE LOGS EXPLORER
# =============================================================================


class UsageLogResponse(BaseModel):
    """A single usage log entry."""

    id: str
    provider: str
    model: str
    input_tokens: int
    output_tokens: int
    cost_usd: float
    latency_ms: Optional[float] = None
    cache_hit: bool = False
    tags: List[str] = Field(default_factory=list)
    created_at: datetime

    class Config:
        from_attributes = True


class UsageLogsListResponse(BaseModel):
    """Paginated list of usage logs."""

    logs: List[UsageLogResponse]
    total: int
    page: int
    page_size: int
    has_more: bool


# =============================================================================
# TAGS
# =============================================================================


class TagCreate(BaseModel):
    """Request to create a tag."""

    name: str = Field(..., min_length=1, max_length=100, description="Tag name")
    color: str = Field(default="#6366f1", pattern="^#[0-9a-fA-F]{6}$", description="Hex color")


class TagResponse(BaseModel):
    """Tag information."""

    id: str
    name: str
    color: str
    usage_count: int = Field(0, description="Number of logs with this tag")
    created_at: datetime

    class Config:
        from_attributes = True


class TagListResponse(BaseModel):
    """List of user's tags."""

    tags: List[TagResponse]


class TagAttach(BaseModel):
    """Request to attach tags to a log entry."""

    tag_ids: List[str] = Field(..., description="List of tag IDs to attach")


# =============================================================================
# FORECAST
# =============================================================================


class ForecastResponse(BaseModel):
    """Cost forecast based on historical trends."""

    predicted_next_month_usd: float = Field(0.0, description="Predicted next month cost")
    daily_average_usd: float = Field(0.0, description="Daily average spend")
    trend: str = Field("stable", description="Trend direction: increasing, decreasing, stable")
    trend_pct_change: float = Field(0.0, description="Percentage change in trend")
    confidence: str = Field("low", description="Forecast confidence: low, medium, high")
    projected_daily: List[DailyCost] = Field(default_factory=list, description="30-day projected daily costs")


# =============================================================================
# ANOMALY DETECTION
# =============================================================================


class AnomalyEvent(BaseModel):
    """A detected spending anomaly."""

    type: str = Field(..., description="Anomaly type: spend_spike, model_switch, token_surge")
    message: str = Field(..., description="Human-readable description")
    severity: str = Field("warning", description="Severity: info, warning, critical")
    current_value: float = Field(0.0, description="Current value that triggered the anomaly")
    expected_value: float = Field(0.0, description="Expected/average value")
    deviation_factor: float = Field(0.0, description="How many std deviations above mean")
    detected_at: datetime


class AnomalyResponse(BaseModel):
    """Recent anomaly events."""

    anomalies: List[AnomalyEvent] = Field(default_factory=list)
    has_active_anomaly: bool = Field(False, description="Whether there's an active anomaly right now")


# =============================================================================
# CACHE
# =============================================================================


class CacheStatsResponse(BaseModel):
    """Cache statistics."""

    hit_rate: float = Field(0.0, description="Cache hit rate (0-1)")
    total_hits: int = Field(0, description="Total cache hits")
    total_misses: int = Field(0, description="Total cache misses")
    size: int = Field(0, description="Current cache size")
    max_size: int = Field(0, description="Maximum cache size")


# =============================================================================
# HEALTH
# =============================================================================


class HealthResponse(BaseModel):
    """API health check response."""

    status: str = Field(default="healthy", description="Service status")
    database: str = Field(..., description="Database connection status")
    version: str = Field(default="1.0.0", description="API version")
    uptime_seconds: int = Field(..., description="Server uptime in seconds")


# =============================================================================
# ERROR RESPONSES
# =============================================================================


class ErrorResponse(BaseModel):
    """Standard error response."""

    success: bool = False
    error: str = Field(..., description="Error message")
    detail: Optional[str] = Field(None, description="Additional error details")
