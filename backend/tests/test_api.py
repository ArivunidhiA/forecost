"""
Tests for LLMLab API endpoints.

Tests the actual endpoints in main.py using the conftest fixtures.
"""

import pytest
from fastapi.testclient import TestClient


# =============================================================================
# HEALTH
# =============================================================================


class TestHealth:
    def test_health_check(self, client: TestClient):
        """Health endpoint should return healthy status."""
        response = client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] in ("healthy", "degraded")
        assert "database" in data
        assert "version" in data
        assert "uptime_seconds" in data


# =============================================================================
# API KEYS
# =============================================================================


class TestApiKeys:
    def test_create_key(self, client: TestClient, auth_headers: dict):
        """Should create an API key and return a proxy key."""
        response = client.post(
            "/api/v1/keys",
            json={"provider": "openai", "api_key": "sk-test-key-123456789012345"},
            headers=auth_headers,
        )
        assert response.status_code == 200
        data = response.json()
        assert data["provider"] == "openai"
        assert data["proxy_key"].startswith("llmlab_pk_")
        assert data["is_active"] is True

    def test_create_key_duplicate_provider(
        self, client: TestClient, auth_headers: dict, test_openai_key
    ):
        """Should reject duplicate key for same provider."""
        response = client.post(
            "/api/v1/keys",
            json={"provider": "openai", "api_key": "sk-another-key-12345678901"},
            headers=auth_headers,
        )
        assert response.status_code == 400

    def test_create_key_invalid_provider(self, client: TestClient, auth_headers: dict):
        """Should reject invalid provider names."""
        response = client.post(
            "/api/v1/keys",
            json={"provider": "invalid", "api_key": "sk-test-key-123456789012345"},
            headers=auth_headers,
        )
        assert response.status_code == 422

    def test_create_key_google(self, client: TestClient, auth_headers: dict):
        """Should accept google as a valid provider."""
        response = client.post(
            "/api/v1/keys",
            json={"provider": "google", "api_key": "AIzaSyTestKey123456"},
            headers=auth_headers,
        )
        assert response.status_code == 200
        assert response.json()["provider"] == "google"

    def test_list_keys(self, client: TestClient, auth_headers: dict, test_openai_key):
        """Should list user's active API keys."""
        response = client.get("/api/v1/keys", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert "keys" in data
        assert len(data["keys"]) == 1
        assert data["keys"][0]["provider"] == "openai"

    def test_delete_key(self, client: TestClient, auth_headers: dict, test_openai_key):
        """Should deactivate an API key."""
        response = client.delete(
            f"/api/v1/keys/{test_openai_key.id}", headers=auth_headers
        )
        assert response.status_code == 200
        assert response.json()["success"] is True

        # Verify it's gone from list
        list_response = client.get("/api/v1/keys", headers=auth_headers)
        assert len(list_response.json()["keys"]) == 0

    def test_delete_key_not_found(self, client: TestClient, auth_headers: dict):
        """Should return 404 for non-existent key."""
        response = client.delete(
            "/api/v1/keys/nonexistent-id", headers=auth_headers
        )
        assert response.status_code == 404

    def test_create_key_unauthenticated(self, client: TestClient):
        """Should reject unauthenticated requests."""
        response = client.post(
            "/api/v1/keys",
            json={"provider": "openai", "api_key": "sk-test-key-123456789012345"},
        )
        assert response.status_code in (401, 403)


# =============================================================================
# STATS
# =============================================================================


class TestStats:
    def test_get_stats_default(
        self, client: TestClient, auth_headers: dict, test_usage_logs
    ):
        """Should return stats for the default period (month)."""
        response = client.get("/api/v1/stats", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert data["period"] == "month"
        assert data["total_usd"] > 0
        assert data["total_calls"] > 0
        assert data["total_tokens"] > 0
        assert "today_usd" in data
        assert "month_usd" in data
        assert "all_time_usd" in data
        assert isinstance(data["by_model"], list)
        assert isinstance(data["by_day"], list)

        # Latency fields
        assert "avg_latency_ms" in data
        assert data["avg_latency_ms"] > 0

        # Cache fields
        assert "cache_hits" in data
        assert "cache_misses" in data
        assert "cache_savings_usd" in data
        assert isinstance(data["cache_hits"], int)
        assert isinstance(data["cache_misses"], int)

        # Per-model latency
        for model in data["by_model"]:
            assert "avg_latency_ms" in model

    def test_get_stats_today(
        self, client: TestClient, auth_headers: dict, test_usage_logs
    ):
        """Should return today's stats only."""
        response = client.get(
            "/api/v1/stats?period=today", headers=auth_headers
        )
        assert response.status_code == 200
        data = response.json()
        assert data["period"] == "today"

    def test_get_stats_all(
        self, client: TestClient, auth_headers: dict, test_usage_logs
    ):
        """Should return all-time stats."""
        response = client.get(
            "/api/v1/stats?period=all", headers=auth_headers
        )
        assert response.status_code == 200
        data = response.json()
        assert data["period"] == "all"
        assert data["total_calls"] == 5  # All 5 test logs (including 1 cache hit)

    def test_get_stats_empty(self, client: TestClient, auth_headers: dict):
        """Should return zero stats when no usage logs exist."""
        response = client.get("/api/v1/stats", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert data["total_usd"] == 0
        assert data["total_calls"] == 0

    def test_get_stats_unauthenticated(self, client: TestClient):
        """Should reject unauthenticated requests."""
        response = client.get("/api/v1/stats")
        assert response.status_code in (401, 403)

    def test_get_stats_tag_filter(
        self, client: TestClient, auth_headers: dict, test_tagged_logs
    ):
        """Stats filtered by tag should only include tagged logs."""
        response = client.get("/api/v1/stats?period=all&tag=backend", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        # Only the log tagged with "backend" should be included
        assert data["total_calls"] >= 1
        assert data["total_usd"] > 0

    def test_get_stats_cache_savings(
        self, client: TestClient, auth_headers: dict, test_usage_logs
    ):
        """Cache savings should be non-negative when cache hits exist."""
        response = client.get("/api/v1/stats?period=all", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert data["cache_hits"] >= 1
        assert data["cache_savings_usd"] >= 0.0

    def test_get_stats_by_model_aggregation(
        self, client: TestClient, auth_headers: dict, test_usage_logs
    ):
        """by_model should group correctly with per-model stats."""
        response = client.get("/api/v1/stats?period=all", headers=auth_headers)
        data = response.json()
        by_model = data["by_model"]
        assert len(by_model) >= 2  # At least gpt-4o and claude-3-5-sonnet

        for model_entry in by_model:
            assert "model" in model_entry
            assert "provider" in model_entry
            assert "total_tokens" in model_entry
            assert "cost_usd" in model_entry
            assert "call_count" in model_entry
            assert model_entry["call_count"] > 0

    def test_get_stats_by_day_aggregation(
        self, client: TestClient, auth_headers: dict, test_usage_logs
    ):
        """by_day should have entries for different days."""
        response = client.get("/api/v1/stats?period=all", headers=auth_headers)
        data = response.json()
        by_day = data["by_day"]
        assert len(by_day) >= 2  # Logs span multiple days

        for day_entry in by_day:
            assert "date" in day_entry
            assert "cost_usd" in day_entry
            assert "call_count" in day_entry

        # Should be sorted by date
        dates = [d["date"] for d in by_day]
        assert dates == sorted(dates)

    def test_get_stats_today_month_alltime(
        self, client: TestClient, auth_headers: dict, test_usage_logs
    ):
        """today_usd, month_usd, all_time_usd should be independent values."""
        response = client.get("/api/v1/stats?period=all", headers=auth_headers)
        data = response.json()
        assert data["today_usd"] >= 0
        assert data["month_usd"] >= 0
        assert data["all_time_usd"] >= 0
        # all_time >= month >= today
        assert data["all_time_usd"] >= data["month_usd"]
        assert data["month_usd"] >= data["today_usd"]


# =============================================================================
# BUDGETS
# =============================================================================


class TestBudgets:
    def test_create_budget(self, client: TestClient, auth_headers: dict):
        """Should create a budget."""
        response = client.post(
            "/api/v1/budgets",
            json={"amount_usd": 100.0, "alert_threshold": 80.0},
            headers=auth_headers,
        )
        assert response.status_code == 200
        data = response.json()
        assert data["amount_usd"] == 100.0
        assert data["alert_threshold"] == 80.0
        assert data["status"] == "ok"

    def test_update_budget(self, client: TestClient, auth_headers: dict):
        """Should update an existing budget (upsert)."""
        # Create
        client.post(
            "/api/v1/budgets",
            json={"amount_usd": 100.0},
            headers=auth_headers,
        )
        # Update
        response = client.post(
            "/api/v1/budgets",
            json={"amount_usd": 200.0, "alert_threshold": 90.0},
            headers=auth_headers,
        )
        assert response.status_code == 200
        assert response.json()["amount_usd"] == 200.0
        assert response.json()["alert_threshold"] == 90.0

    def test_get_budgets(self, client: TestClient, auth_headers: dict):
        """Should list user's budgets."""
        # Create first
        client.post(
            "/api/v1/budgets",
            json={"amount_usd": 50.0},
            headers=auth_headers,
        )

        response = client.get("/api/v1/budgets", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert "budgets" in data
        assert len(data["budgets"]) == 1
        assert data["budgets"][0]["amount_usd"] == 50.0

    def test_get_budgets_empty(self, client: TestClient, auth_headers: dict):
        """Should return empty list when no budgets exist."""
        response = client.get("/api/v1/budgets", headers=auth_headers)
        assert response.status_code == 200
        assert response.json()["budgets"] == []

    def test_delete_budget(self, client: TestClient, auth_headers: dict):
        """Should delete a budget."""
        # Create
        create_resp = client.post(
            "/api/v1/budgets",
            json={"amount_usd": 50.0},
            headers=auth_headers,
        )
        budget_id = create_resp.json()["id"]

        # Delete
        response = client.delete(
            f"/api/v1/budgets/{budget_id}", headers=auth_headers
        )
        assert response.status_code == 200
        assert response.json()["success"] is True

    def test_delete_budget_not_found(self, client: TestClient, auth_headers: dict):
        """Should return 404 for non-existent budget."""
        response = client.delete(
            "/api/v1/budgets/nonexistent-id", headers=auth_headers
        )
        assert response.status_code == 404


# =============================================================================
# RECOMMENDATIONS
# =============================================================================


class TestRecommendations:
    def test_get_recommendations_empty(self, client: TestClient, auth_headers: dict):
        """Should return empty recommendations when no usage data."""
        response = client.get("/api/v1/recommendations", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert "recommendations" in data
        assert isinstance(data["recommendations"], list)
        assert "total_potential_savings" in data

    def test_get_recommendations_with_data(
        self, client: TestClient, auth_headers: dict, test_usage_logs
    ):
        """Should return recommendations based on usage data."""
        response = client.get("/api/v1/recommendations", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert "recommendations" in data
        assert "total_potential_savings" in data
        assert "analyzed_period_days" in data

    def test_recommendations_unauthenticated(self, client: TestClient):
        """Should reject unauthenticated requests."""
        response = client.get("/api/v1/recommendations")
        assert response.status_code in (401, 403)


# =============================================================================
# USER
# =============================================================================


class TestUser:
    def test_get_me(self, client: TestClient, auth_headers: dict, test_user):
        """Should return current user profile."""
        response = client.get("/api/v1/me", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert data["email"] == "test@example.com"
        assert data["username"] == "testuser"

    def test_get_me_unauthenticated(self, client: TestClient):
        """Should reject unauthenticated requests."""
        response = client.get("/api/v1/me")
        assert response.status_code in (401, 403)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
