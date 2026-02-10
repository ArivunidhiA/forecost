"""Tests for cache management endpoints."""

import pytest


class TestCacheStats:
    """Tests for GET /api/v1/cache/stats."""

    def test_get_cache_stats(self, client, auth_headers):
        """Cache stats endpoint returns stats object."""
        response = client.get("/api/v1/cache/stats", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert "total_hits" in data
        assert "total_misses" in data
        assert "size" in data
        assert "hit_rate" in data

    def test_cache_stats_requires_auth(self, client):
        """Cache stats requires authentication."""
        response = client.get("/api/v1/cache/stats")
        assert response.status_code == 401


class TestClearCache:
    """Tests for DELETE /api/v1/cache."""

    def test_clear_cache(self, client, auth_headers):
        """Clear cache returns success."""
        response = client.delete("/api/v1/cache", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True

    def test_clear_cache_requires_auth(self, client):
        """Clear cache requires authentication."""
        response = client.delete("/api/v1/cache")
        assert response.status_code == 401
