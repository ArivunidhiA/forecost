# Changelog

All notable changes to LLMLab are documented in this file.

## [0.5.0] - Week 5: Polish, Performance & Launch Readiness

### Security
- **Sort parameter whitelisting**: `sort_by` in logs endpoint now only accepts known column names, preventing arbitrary attribute access
- **Secure export downloads**: Replaced `<a href>` export links (which leaked JWT in URLs) with `fetch()` + Blob downloads using proper `Authorization` headers
- **Date input validation**: Logs and export endpoints now return 400 errors for malformed dates and validate that `date_from <= date_to`

### Performance
- **SQL aggregation for stats**: Rewrote `GET /api/v1/stats` to use `func.sum`, `func.count`, `func.avg`, and `GROUP BY` instead of loading all logs into Python memory
- **Composite database indexes**: Added `(user_id, created_at)` and `(user_id, provider, created_at)` indexes on `usage_logs` for faster query plans

### Rate Limiting
- Added rate limits to all Week 4 endpoints:
  - `GET /api/v1/logs` — 60/minute
  - `GET /api/v1/export/csv` — 10/minute
  - `GET /api/v1/export/json` — 10/minute
  - `GET /api/v1/stats/forecast` — 30/minute
  - `GET /api/v1/stats/anomalies` — 30/minute
  - `POST /api/v1/tags` — 30/minute
  - `GET /api/v1/tags` — 60/minute

### SDK
- Added `tags` parameter to `patch()` for cost attribution: `patch(openai, proxy_key="...", tags=["backend"])`
- Added `set_tags()` and `clear_tags()` helpers for runtime tag changes
- Tags are sent as `X-LLMLab-Tags` header via `default_headers` on patched clients

### Documentation
- Created this CHANGELOG.md
- Updated README.md with Week 3-4 features

---

## [0.4.0] - Week 4: Advanced Analytics

### Added
- **Usage Logs Explorer**: Paginated, filterable, sortable view of individual API calls (`GET /api/v1/logs`)
- **Project Tags**: User-defined tags for cost attribution with CRUD endpoints and auto-tagging via `X-LLMLab-Tags` header
- **Data Export**: CSV and JSON streaming downloads with filter support (`GET /api/v1/export/csv`, `GET /api/v1/export/json`)
- **Cost Forecasting**: Linear trend projection for next month's spend (`GET /api/v1/stats/forecast`)
- **Anomaly Detection**: Z-score based detection for spend spikes and token surges with webhook notifications (`GET /api/v1/stats/anomalies`)
- Frontend: Logs Explorer page, Tag Management in Settings, Export buttons, Forecast Card, Anomaly Alert Banner
- CLI: `llmlab export` command with provider/model filters

---

## [0.3.0] - Week 3: Production Readiness

### Added
- **Streaming support**: Full SSE streaming proxy for OpenAI, Anthropic, and Google with post-stream cost logging
- **Docker deployment**: Multi-stage Dockerfile and docker-compose for backend, frontend, and Redis
- **CI/CD pipeline**: GitHub Actions workflow for lint, test, build, and deploy
- **Redis caching**: Semantic response cache with Redis backend and configurable TTL
- **SDK polish**: `@track_cost` decorator, `patch()` function for zero-code-change integration
- **CLI improvements**: `llmlab status`, `llmlab optimize`, `llmlab proxy-key` commands

---

## [0.2.0] - Week 2: Smart Features

### Added
- **Cost recommendations**: AI-powered suggestions for model downgrades and cost savings
- **Usage heatmap**: Day-of-week x hour-of-day activity visualization
- **Provider comparison**: Side-by-side cost/performance comparison across providers
- **Response caching**: Content-hash based cache to avoid duplicate API calls
- **Budget system**: Monthly budgets with configurable alert thresholds
- **Webhook alerts**: Budget warning/exceeded notifications via webhooks

---

## [0.1.0] - Week 1: Core Foundation

### Added
- **Proxy architecture**: Transparent API proxy for OpenAI, Anthropic, and Google Gemini
- **Authentication**: GitHub OAuth with JWT sessions
- **Cost tracking**: Automatic per-request cost calculation based on model pricing
- **Dashboard**: Real-time cost breakdown by model, daily spending trends
- **API key management**: Encrypted storage with unique proxy keys
- **CLI**: Basic command-line interface for status and key management
- **SDK**: Python SDK with `patch()` for zero-code-change integration
