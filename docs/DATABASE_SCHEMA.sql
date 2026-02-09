-- LLMLab Database Schema (PostgreSQL)
-- Use with Supabase PostgreSQL
--
-- Aligned with SQLAlchemy ORM models in backend/models.py
-- Tables: users, api_keys, usage_logs, budgets, webhooks, tags, usage_log_tags

-- ============================================================================
-- USERS TABLE
-- ============================================================================

CREATE TABLE users (
    id VARCHAR(36) PRIMARY KEY,
    github_id INTEGER UNIQUE NOT NULL,
    email VARCHAR(255) NOT NULL,
    username VARCHAR(255),
    avatar_url VARCHAR(500),
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    is_active BOOLEAN NOT NULL DEFAULT true
);

CREATE INDEX idx_users_github_id ON users(github_id);
CREATE INDEX idx_users_email ON users(email);

-- ============================================================================
-- API KEYS TABLE
-- ============================================================================

CREATE TABLE api_keys (
    id VARCHAR(36) PRIMARY KEY,
    user_id VARCHAR(36) NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    provider VARCHAR(50) NOT NULL,
    encrypted_key TEXT NOT NULL,
    proxy_key VARCHAR(50) UNIQUE NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    last_used_at TIMESTAMP,
    is_active BOOLEAN NOT NULL DEFAULT true
);

CREATE INDEX idx_api_keys_user_id ON api_keys(user_id);
CREATE INDEX idx_api_keys_provider ON api_keys(provider);
CREATE INDEX idx_api_keys_proxy_key ON api_keys(proxy_key);

-- ============================================================================
-- USAGE LOGS TABLE
-- ============================================================================

CREATE TABLE usage_logs (
    id VARCHAR(36) PRIMARY KEY,
    user_id VARCHAR(36) NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    provider VARCHAR(50) NOT NULL,
    model VARCHAR(100) NOT NULL,
    input_tokens INTEGER NOT NULL DEFAULT 0,
    output_tokens INTEGER NOT NULL DEFAULT 0,
    cost_usd FLOAT NOT NULL DEFAULT 0.0,
    latency_ms FLOAT,
    cache_hit BOOLEAN NOT NULL DEFAULT false,
    request_id VARCHAR(100),
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_usage_logs_user_id ON usage_logs(user_id);
CREATE INDEX idx_usage_logs_provider ON usage_logs(provider);
CREATE INDEX idx_usage_logs_model ON usage_logs(model);
CREATE INDEX idx_usage_logs_cost_usd ON usage_logs(cost_usd);
CREATE INDEX idx_usage_logs_created_at ON usage_logs(created_at);

-- Composite indexes for common query patterns (stats, logs, forecast)
CREATE INDEX idx_usage_logs_user_created ON usage_logs(user_id, created_at DESC);
CREATE INDEX idx_usage_logs_user_provider_created ON usage_logs(user_id, provider, created_at DESC);

-- ============================================================================
-- BUDGETS TABLE
-- ============================================================================

CREATE TABLE budgets (
    id VARCHAR(36) PRIMARY KEY,
    user_id VARCHAR(36) NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    amount_usd FLOAT NOT NULL,
    period VARCHAR(20) NOT NULL DEFAULT 'monthly',
    alert_threshold FLOAT NOT NULL DEFAULT 80.0,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_budgets_user_id ON budgets(user_id);

-- ============================================================================
-- WEBHOOKS TABLE
-- ============================================================================

CREATE TABLE webhooks (
    id VARCHAR(36) PRIMARY KEY,
    user_id VARCHAR(36) NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    url VARCHAR(500) NOT NULL,
    event_type VARCHAR(50) NOT NULL,
    is_active BOOLEAN NOT NULL DEFAULT true,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_webhooks_user_id ON webhooks(user_id);

-- ============================================================================
-- TAGS TABLE
-- ============================================================================

CREATE TABLE tags (
    id VARCHAR(36) PRIMARY KEY,
    user_id VARCHAR(36) NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    name VARCHAR(100) NOT NULL,
    color VARCHAR(7) NOT NULL DEFAULT '#6366f1',
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_tags_user_id ON tags(user_id);

-- ============================================================================
-- USAGE LOG TAGS (junction table)
-- ============================================================================

CREATE TABLE usage_log_tags (
    usage_log_id VARCHAR(36) NOT NULL REFERENCES usage_logs(id) ON DELETE CASCADE,
    tag_id VARCHAR(36) NOT NULL REFERENCES tags(id) ON DELETE CASCADE,
    PRIMARY KEY (usage_log_id, tag_id)
);

CREATE INDEX idx_usage_log_tags_tag_id ON usage_log_tags(tag_id);

-- ============================================================================
-- VIEWS (for analytics)
-- ============================================================================

-- Total spend by user
CREATE VIEW user_total_spend AS
SELECT 
    user_id,
    SUM(cost_usd) as total_usd,
    COUNT(*) as call_count,
    SUM(input_tokens + output_tokens) as total_tokens,
    MAX(created_at) as last_call
FROM usage_logs
GROUP BY user_id;

-- Spend by model
CREATE VIEW user_spend_by_model AS
SELECT 
    user_id,
    model,
    provider,
    SUM(cost_usd) as total_usd,
    COUNT(*) as call_count,
    SUM(input_tokens + output_tokens) as total_tokens
FROM usage_logs
GROUP BY user_id, model, provider;

-- Daily spend
CREATE VIEW user_daily_spend AS
SELECT 
    user_id,
    DATE(created_at) as date,
    SUM(cost_usd) as daily_spend_usd,
    COUNT(*) as call_count
FROM usage_logs
GROUP BY user_id, DATE(created_at)
ORDER BY user_id, date DESC;

-- Budget status
CREATE VIEW budget_status AS
SELECT 
    b.id,
    b.user_id,
    b.amount_usd,
    b.alert_threshold,
    COALESCE(SUM(ul.cost_usd), 0) as spent_usd,
    b.amount_usd - COALESCE(SUM(ul.cost_usd), 0) as remaining_usd,
    ROUND(100.0 * COALESCE(SUM(ul.cost_usd), 0) / NULLIF(b.amount_usd, 0), 2) as percentage_used
FROM budgets b
LEFT JOIN usage_logs ul ON ul.user_id = b.user_id 
    AND ul.created_at >= CURRENT_DATE - INTERVAL '30 days'
GROUP BY b.id, b.user_id, b.amount_usd, b.alert_threshold;

-- ============================================================================
-- SECURITY NOTES
-- ============================================================================
/*
1. API keys are encrypted with Fernet before storage (encrypted_key column)
2. Users authenticate via GitHub OAuth (no password storage)
3. All queries use parameterized statements via SQLAlchemy ORM
4. Proxy keys are unique random tokens (llmlab_pk_xxx format)
5. Row-level security (RLS) should be enabled in production
*/

-- ============================================================================
-- MIGRATION NOTES
-- ============================================================================
/*
The SQLAlchemy ORM in backend/models.py is the source of truth.
This SQL file is provided for reference and manual DB setup.

To create tables automatically:
  python -c "from database import init_db; init_db()"

Or run with Alembic for production migrations.
*/
