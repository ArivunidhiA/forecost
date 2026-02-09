"""Tests for the Usage Logs Explorer endpoints."""

import pytest


class TestGetLogs:
    """Tests for GET /api/v1/logs."""

    def test_list_logs_default(self, client, auth_headers, test_usage_logs):
        """Default request returns paginated logs, newest first."""
        response = client.get("/api/v1/logs", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert "logs" in data
        assert "total" in data
        assert data["total"] == 5
        assert data["page"] == 1
        assert data["page_size"] == 50
        assert len(data["logs"]) == 5

    def test_list_logs_pagination(self, client, auth_headers, test_usage_logs):
        """Pagination works correctly."""
        response = client.get("/api/v1/logs?page=1&page_size=2", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert len(data["logs"]) == 2
        assert data["total"] == 5
        assert data["has_more"] is True

        # Page 2
        response = client.get("/api/v1/logs?page=2&page_size=2", headers=auth_headers)
        data = response.json()
        assert len(data["logs"]) == 2

        # Page 3
        response = client.get("/api/v1/logs?page=3&page_size=2", headers=auth_headers)
        data = response.json()
        assert len(data["logs"]) == 1
        assert data["has_more"] is False

    def test_filter_by_provider(self, client, auth_headers, test_usage_logs):
        """Filter by provider returns only matching logs."""
        response = client.get("/api/v1/logs?provider=anthropic", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert all(log["provider"] == "anthropic" for log in data["logs"])
        assert data["total"] == 1

    def test_filter_by_model(self, client, auth_headers, test_usage_logs):
        """Filter by model returns only matching logs."""
        response = client.get("/api/v1/logs?model=gpt-4o", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert all(log["model"] == "gpt-4o" for log in data["logs"])

    def test_filter_by_cache_hit(self, client, auth_headers, test_usage_logs):
        """Filter by cache_hit returns only cached results."""
        response = client.get("/api/v1/logs?cache_hit=true", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert all(log["cache_hit"] is True for log in data["logs"])
        assert data["total"] == 1

    def test_sort_by_cost(self, client, auth_headers, test_usage_logs):
        """Sort by cost descending returns highest cost first."""
        response = client.get("/api/v1/logs?sort_by=cost_usd&sort_order=desc", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        costs = [log["cost_usd"] for log in data["logs"]]
        assert costs == sorted(costs, reverse=True)

    def test_logs_include_tags(self, client, auth_headers, test_tagged_logs):
        """Logs include tag names."""
        response = client.get("/api/v1/logs", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        # At least one log should have tags
        tagged = [log for log in data["logs"] if log["tags"]]
        assert len(tagged) >= 1

    def test_filter_by_tag(self, client, auth_headers, test_tagged_logs):
        """Filter by tag name returns only tagged logs."""
        response = client.get("/api/v1/logs?tag=backend", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert data["total"] >= 1
        for log in data["logs"]:
            assert "backend" in log["tags"]

    def test_requires_auth(self, client, test_usage_logs):
        """Endpoint requires authentication."""
        response = client.get("/api/v1/logs")
        assert response.status_code == 401

    def test_log_structure(self, client, auth_headers, test_usage_logs):
        """Log entries have all expected fields."""
        response = client.get("/api/v1/logs", headers=auth_headers)
        data = response.json()
        log = data["logs"][0]
        assert "id" in log
        assert "provider" in log
        assert "model" in log
        assert "input_tokens" in log
        assert "output_tokens" in log
        assert "cost_usd" in log
        assert "latency_ms" in log
        assert "cache_hit" in log
        assert "tags" in log
        assert "created_at" in log


class TestGetLog:
    """Tests for GET /api/v1/logs/{log_id}."""

    def test_get_single_log(self, client, auth_headers, test_usage_logs):
        """Get a single log entry by ID."""
        log_id = test_usage_logs[0].id
        response = client.get(f"/api/v1/logs/{log_id}", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert data["id"] == log_id
        assert data["provider"] == "openai"

    def test_get_nonexistent_log(self, client, auth_headers):
        """Requesting a non-existent log returns 404."""
        response = client.get("/api/v1/logs/nonexistent-id", headers=auth_headers)
        assert response.status_code == 404

    def test_requires_auth(self, client, test_usage_logs):
        """Endpoint requires authentication."""
        response = client.get(f"/api/v1/logs/{test_usage_logs[0].id}")
        assert response.status_code == 401
