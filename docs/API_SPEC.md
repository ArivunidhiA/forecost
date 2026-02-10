# LLMLab API Specification

## Overview

LLMLab uses **GitHub OAuth → JWT** for authentication. There is no email/password signup or login.

**Base URL**: `https://llmlab-backend.up.railway.app` (or `http://localhost:8000` for local dev)

**Authentication**: JWT token in `Authorization: Bearer {token}` header (obtained via GitHub OAuth)

---

## Authentication Endpoints

### POST /auth/github

Exchange a GitHub OAuth authorization code for a JWT token.

**Request**:
```json
{
  "code": "github_oauth_authorization_code"
}
```

**Response** (200):
```json
{
  "user_id": "550e8400-e29b-41d4-a716-446655440000",
  "email": "user@example.com",
  "username": "octocat",
  "token": "eyJhbGciOiJIUzI1NiIs...",
  "expires_in": 86400
}
```

**Errors**:
- 400: Invalid or expired OAuth code
- 422: Validation error

---

### POST /auth/dev-login

Dev-only login (disabled in production). Returns a JWT for local development.

**Response** (200):
```json
{
  "user_id": "dev-user-id",
  "email": "dev@localhost",
  "username": "dev",
  "token": "eyJhbGciOiJIUzI1NiIs...",
  "expires_in": 86400
}
```

---

### GET /api/v1/me

Get the authenticated user's profile.

**Response** (200):
```json
{
  "id": "550e8400-e29b-41d4-a716-446655440000",
  "github_id": 12345678,
  "email": "user@example.com",
  "username": "octocat",
  "avatar_url": "https://avatars.githubusercontent.com/u/12345678",
  "created_at": "2026-01-15T08:30:00Z"
}
```

---

## API Key Endpoints

### POST /api/v1/keys

Store an encrypted API key for a provider.

**Request**:
```json
{
  "provider": "openai",
  "api_key": "sk-proj-abc123def456..."
}
```

**Validation**:
- `provider`: must be `openai`, `anthropic`, or `google`
- `api_key`: minimum 10 characters

**Response** (201):
```json
{
  "id": "key_550e8400",
  "provider": "openai",
  "proxy_key": "pql_openai_abc123",
  "created_at": "2026-02-10T12:00:00Z",
  "last_used_at": null,
  "is_active": true
}
```

---

### GET /api/v1/keys

List all API keys for the authenticated user.

**Response** (200):
```json
{
  "keys": [
    {
      "id": "key_550e8400",
      "provider": "openai",
      "proxy_key": "pql_openai_abc123",
      "created_at": "2026-02-10T12:00:00Z",
      "last_used_at": "2026-02-10T14:30:00Z",
      "is_active": true
    },
    {
      "id": "key_660f9500",
      "provider": "anthropic",
      "proxy_key": "pql_anthropic_def456",
      "created_at": "2026-02-10T12:05:00Z",
      "last_used_at": null,
      "is_active": true
    }
  ]
}
```

---

### DELETE /api/v1/keys/{key_id}

Delete an API key.

**Response** (200):
```json
{ "success": true }
```

**Errors**:
- 404: Key not found
- 403: Not authorized

---

## Proxy Endpoints

These endpoints forward requests to LLM providers. Usage and cost are logged automatically.

### POST/GET/etc /api/v1/proxy/openai/{path}

Proxy to OpenAI API. Authenticate with your **proxy key** (from `POST /api/v1/keys`).

### POST/GET/etc /api/v1/proxy/anthropic/{path}

Proxy to Anthropic API.

### POST/GET/etc /api/v1/proxy/google/{path}

Proxy to Google Gemini API.

**Optional Headers**:
- `X-LLMLab-Tags: backend,prod` — Attach tags to the logged call for cost attribution

---

## Usage Statistics Endpoints

### GET /api/v1/stats

Get usage statistics for a time period.

**Query Parameters**:
- `period`: `today` | `week` | `month` | `all` (default: `month`)

**Response** (200):
```json
{
  "period": "month",
  "total_usd": 1234.56,
  "total_calls": 680,
  "total_tokens": 2450000,
  "avg_latency_ms": 320.5,
  "today_usd": 42.10,
  "month_usd": 1234.56,
  "all_time_usd": 5678.90,
  "cache_hits": 120,
  "cache_misses": 560,
  "cache_savings_usd": 18.40,
  "by_model": [
    {
      "model": "gpt-4",
      "provider": "openai",
      "total_tokens": 750000,
      "cost_usd": 500.00,
      "call_count": 100,
      "avg_latency_ms": 450.2
    },
    {
      "model": "claude-3-opus-20240229",
      "provider": "anthropic",
      "total_tokens": 600000,
      "cost_usd": 400.00,
      "call_count": 80,
      "avg_latency_ms": 380.0
    }
  ],
  "by_day": [
    { "date": "2026-02-01", "cost_usd": 40.00, "call_count": 25 },
    { "date": "2026-02-02", "cost_usd": 45.00, "call_count": 30 }
  ]
}
```

---

### GET /api/v1/stats/heatmap

Usage heatmap — call count and cost by day-of-week × hour-of-day.

**Response** (200):
```json
{
  "cells": [
    { "day": 0, "hour": 9, "call_count": 45, "cost_usd": 12.30 },
    { "day": 0, "hour": 10, "call_count": 60, "cost_usd": 18.50 },
    { "day": 1, "hour": 14, "call_count": 30, "cost_usd": 8.20 }
  ]
}
```

Fields: `day` 0=Monday…6=Sunday, `hour` 0–23.

---

### GET /api/v1/stats/comparison

Provider cost comparison with cheaper alternatives.

**Response** (200):
```json
{
  "comparisons": [
    {
      "model": "gpt-4",
      "provider": "openai",
      "actual_cost": 500.00,
      "input_tokens": 500000,
      "output_tokens": 250000,
      "alternatives": [
        { "provider": "anthropic", "model": "claude-3-sonnet-20240229", "estimated_cost": 225.00 },
        { "provider": "google", "model": "gemini-1.5-pro", "estimated_cost": 180.00 }
      ]
    }
  ],
  "current_total": 500.00,
  "cheapest_total": 180.00
}
```

---

### GET /api/v1/stats/forecast

Cost forecast based on historical spending trends.

**Response** (200):
```json
{
  "predicted_next_month_usd": 1450.00,
  "daily_average_usd": 48.33,
  "trend": "increasing",
  "trend_pct_change": 12.5,
  "confidence": "medium",
  "projected_daily": [
    { "date": "2026-03-01", "cost_usd": 47.00, "call_count": 28 },
    { "date": "2026-03-02", "cost_usd": 49.00, "call_count": 30 }
  ]
}
```

---

### GET /api/v1/stats/anomalies

Detected spending anomalies (Z-score based).

**Response** (200):
```json
{
  "anomalies": [
    {
      "type": "spend_spike",
      "message": "Spending on 2026-02-08 was 3.2x above average",
      "severity": "warning",
      "current_value": 150.00,
      "expected_value": 47.00,
      "deviation_factor": 3.2,
      "detected_at": "2026-02-08T23:00:00Z"
    }
  ],
  "has_active_anomaly": true
}
```

---

## Usage Logs Endpoints

### GET /api/v1/logs

List usage logs (paginated).

**Query Parameters**:
- `page` (int, default: 1)
- `page_size` (int, default: 50)
- `provider` (string, optional)
- `model` (string, optional)
- `tag` (string, optional)

**Response** (200):
```json
{
  "logs": [
    {
      "id": "log_abc123",
      "provider": "openai",
      "model": "gpt-4",
      "input_tokens": 1000,
      "output_tokens": 500,
      "cost_usd": 0.045,
      "latency_ms": 1250.5,
      "cache_hit": false,
      "tags": ["backend", "prod"],
      "created_at": "2026-02-10T14:30:00Z"
    }
  ],
  "total": 1234,
  "page": 1,
  "page_size": 50,
  "has_more": true
}
```

---

### GET /api/v1/logs/{log_id}

Get a single usage log entry.

**Response** (200):
```json
{
  "id": "log_abc123",
  "provider": "openai",
  "model": "gpt-4",
  "input_tokens": 1000,
  "output_tokens": 500,
  "cost_usd": 0.045,
  "latency_ms": 1250.5,
  "cache_hit": false,
  "tags": ["backend", "prod"],
  "created_at": "2026-02-10T14:30:00Z"
}
```

**Errors**: 404 — Log not found

---

## Tag Endpoints

### POST /api/v1/tags

Create a tag for cost attribution.

**Request**:
```json
{
  "name": "production",
  "color": "#6366f1"
}
```

**Validation**: `name` 1–100 chars, `color` hex (e.g. `#6366f1`)

**Response** (201):
```json
{
  "id": "tag_abc123",
  "name": "production",
  "color": "#6366f1",
  "usage_count": 0,
  "created_at": "2026-02-10T12:00:00Z"
}
```

---

### GET /api/v1/tags

List all tags.

**Response** (200):
```json
{
  "tags": [
    { "id": "tag_abc123", "name": "production", "color": "#6366f1", "usage_count": 42, "created_at": "2026-02-10T12:00:00Z" },
    { "id": "tag_def456", "name": "backend", "color": "#f59e0b", "usage_count": 18, "created_at": "2026-02-10T12:05:00Z" }
  ]
}
```

---

### DELETE /api/v1/tags/{tag_id}

Delete a tag.

**Response** (200): `{ "success": true }`

---

### POST /api/v1/logs/{log_id}/tags

Attach tags to a log entry.

**Request**:
```json
{
  "tag_ids": ["tag_abc123", "tag_def456"]
}
```

**Response** (200): `{ "success": true }`

---

### DELETE /api/v1/logs/{log_id}/tags/{tag_id}

Detach a tag from a log entry.

**Response** (200): `{ "success": true }`

---

## Export Endpoints

### GET /api/v1/export/csv

Download usage logs as CSV.

**Query Parameters**:
- `provider` (string, optional)
- `start_date` (string, optional): ISO date
- `end_date` (string, optional): ISO date
- `tag` (string, optional)

**Response** (200): CSV file download

---

### GET /api/v1/export/json

Download usage logs as JSON.

**Query Parameters**: Same as CSV export.

**Response** (200): JSON file download

---

## Budget Endpoints

### GET /api/v1/budgets

Get user's budgets.

**Response** (200):
```json
{
  "budgets": [
    {
      "id": "bdg_abc123",
      "amount_usd": 1000.00,
      "period": "monthly",
      "alert_threshold": 80.0,
      "current_spend": 456.78,
      "status": "ok",
      "created_at": "2026-01-01T00:00:00Z",
      "updated_at": "2026-02-10T12:00:00Z"
    }
  ]
}
```

**Status values**: `ok`, `warning`, `exceeded`

---

### POST /api/v1/budgets

Create or update a budget.

**Request**:
```json
{
  "amount_usd": 1000.00,
  "period": "monthly",
  "alert_threshold": 80.0
}
```

**Validation**: `amount_usd` > 0, `alert_threshold` 0–100

**Response** (201):
```json
{
  "id": "bdg_abc123",
  "amount_usd": 1000.00,
  "period": "monthly",
  "alert_threshold": 80.0,
  "current_spend": 0.0,
  "status": "ok",
  "created_at": "2026-02-10T12:00:00Z",
  "updated_at": "2026-02-10T12:00:00Z"
}
```

---

### DELETE /api/v1/budgets/{budget_id}

Delete a budget.

**Response** (200): `{ "success": true }`

**Errors**: 404 — Budget not found

---

## Recommendations Endpoint

### GET /api/v1/recommendations

Cost-saving recommendations based on usage patterns.

**Response** (200):
```json
{
  "recommendations": [
    {
      "type": "model_switch",
      "title": "Switch to GPT-4-turbo for coding tasks",
      "description": "You're using GPT-4 for 80% of calls. GPT-4-turbo is 3x cheaper with comparable quality.",
      "potential_savings": 150.00,
      "priority": "high",
      "current_model": "gpt-4",
      "suggested_model": "gpt-4-turbo"
    },
    {
      "type": "caching",
      "title": "Enable response caching",
      "description": "22% of your requests have identical prompts. Caching could save $40/mo.",
      "potential_savings": 40.00,
      "priority": "medium",
      "current_model": null,
      "suggested_model": null
    }
  ],
  "total_potential_savings": 190.00,
  "analyzed_period_days": 30
}
```

---

## Webhook Endpoints

### POST /api/v1/webhooks

Register a webhook for alerts.

**Request**:
```json
{
  "url": "https://hooks.slack.com/services/T00/B00/xxxx",
  "event_type": "budget_exceeded"
}
```

**Validation**: `url` min 10 chars, `event_type` one of `budget_warning`, `budget_exceeded`, `anomaly`

**Response** (201):
```json
{
  "id": "wh_abc123",
  "url": "https://hooks.slack.com/services/T00/B00/xxxx",
  "event_type": "budget_exceeded",
  "is_active": true,
  "created_at": "2026-02-10T12:00:00Z"
}
```

---

### GET /api/v1/webhooks

List all webhooks.

**Response** (200):
```json
{
  "webhooks": [
    {
      "id": "wh_abc123",
      "url": "https://hooks.slack.com/services/T00/B00/xxxx",
      "event_type": "budget_exceeded",
      "is_active": true,
      "created_at": "2026-02-10T12:00:00Z"
    }
  ]
}
```

---

### DELETE /api/v1/webhooks/{webhook_id}

Delete a webhook.

**Response** (200): `{ "success": true }`

**Errors**: 404 — Webhook not found

---

## Cache Endpoints

### GET /api/v1/cache/stats

Get cache statistics.

**Response** (200):
```json
{
  "hit_rate": 0.22,
  "total_hits": 120,
  "total_misses": 425,
  "size": 545,
  "max_size": 10000
}
```

---

### DELETE /api/v1/cache

Clear the response cache.

**Response** (200): `{ "success": true }`

---

## Health Endpoint

### GET /health

Health check (no authentication required).

**Response** (200):
```json
{
  "status": "healthy",
  "database": "connected",
  "version": "1.0.0",
  "uptime_seconds": 3600
}
```

---

## Error Handling

All errors follow this format:

```json
{
  "success": false,
  "error": "Error message describing what went wrong",
  "detail": "Additional context (optional)"
}
```

**HTTP Status Codes**:
- 200: Success
- 201: Created
- 400: Bad request (validation error)
- 401: Unauthorized (invalid/missing token)
- 403: Forbidden
- 404: Not found
- 422: Validation error
- 429: Rate limit exceeded
- 500: Server error

---

## Authentication Flow

1. **User clicks "Login with GitHub"** in the frontend
2. **GitHub redirects** back with an authorization `code`
3. **Frontend sends** `POST /auth/github` with `{ "code": "..." }`
4. **Backend exchanges** the code with GitHub, fetches user info, creates/finds the user, returns a JWT
5. **Frontend stores** the JWT and sends `Authorization: Bearer {token}` on all requests
6. **Token expires** after `expires_in` seconds — re-authenticate via GitHub

---

## Example Usage

### cURL

```bash
# Authenticate via GitHub OAuth
curl -X POST https://llmlab-backend.up.railway.app/auth/github \
  -H "Content-Type: application/json" \
  -d '{ "code": "github_oauth_code_here" }'

# Store an API key
curl -X POST https://llmlab-backend.up.railway.app/api/v1/keys \
  -H "Authorization: Bearer {token}" \
  -H "Content-Type: application/json" \
  -d '{ "provider": "openai", "api_key": "sk-proj-abc123..." }'

# Make a proxied OpenAI request (uses proxy key)
curl -X POST https://llmlab-backend.up.railway.app/api/v1/proxy/openai/v1/chat/completions \
  -H "Authorization: Bearer pql_openai_abc123" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "gpt-4",
    "messages": [{"role": "user", "content": "Hello!"}]
  }'

# Get usage statistics
curl https://llmlab-backend.up.railway.app/api/v1/stats?period=month \
  -H "Authorization: Bearer {token}"

# Get cost recommendations
curl https://llmlab-backend.up.railway.app/api/v1/recommendations \
  -H "Authorization: Bearer {token}"
```

### Python

```python
import requests

BASE = "https://llmlab-backend.up.railway.app"

# Authenticate via GitHub OAuth (after receiving code from GitHub redirect)
resp = requests.post(f"{BASE}/auth/github", json={"code": "github_oauth_code"})
token = resp.json()["token"]
headers = {"Authorization": f"Bearer {token}"}

# Store an API key
requests.post(
    f"{BASE}/api/v1/keys",
    headers=headers,
    json={"provider": "openai", "api_key": "sk-proj-abc123..."}
)

# Get usage statistics
stats = requests.get(f"{BASE}/api/v1/stats", headers=headers, params={"period": "month"})
print(stats.json())

# Get recommendations
recs = requests.get(f"{BASE}/api/v1/recommendations", headers=headers)
print(recs.json())
```

---

## Rate Limiting

Rate limits are configurable per-endpoint. Default limits:
- Proxy endpoints: 60 requests/minute
- Other endpoints: 100 requests/minute

---

## Pagination

`GET /api/v1/logs` supports pagination:
- `page` — Page number (1-based)
- `page_size` — Results per page (default: 50)
- Response includes `total`, `page`, `page_size`, `has_more`

---

## Timestamps

All timestamps are ISO 8601 (UTC): `2026-02-10T12:00:00Z`

---

## Data Types

- **Cost values**: USD (float)
- **Token counts**: integers
- **Percentages**: floats 0–100 (except `hit_rate` which is 0–1)

---

This API is designed to be **simple**, **intuitive**, and **easy to integrate** with any Python, JavaScript, or web application.
