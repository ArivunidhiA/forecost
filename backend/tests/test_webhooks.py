"""
Tests for webhook CRUD endpoints.
"""

import pytest
from fastapi.testclient import TestClient


class TestWebhooks:
    def test_create_webhook(self, client: TestClient, auth_headers: dict):
        """Should create a webhook and return response fields."""
        response = client.post(
            "/api/v1/webhooks",
            json={"url": "https://example.com/hook", "event_type": "budget_warning"},
            headers=auth_headers,
        )
        assert response.status_code == 200
        data = response.json()
        assert data["url"] == "https://example.com/hook"
        assert data["event_type"] == "budget_warning"
        assert data["is_active"] is True
        assert "id" in data
        assert "created_at" in data

    def test_create_webhook_exceeded(self, client: TestClient, auth_headers: dict):
        """Should create webhook with budget_exceeded event type."""
        response = client.post(
            "/api/v1/webhooks",
            json={"url": "https://example.com/alert", "event_type": "budget_exceeded"},
            headers=auth_headers,
        )
        assert response.status_code == 200
        assert response.json()["event_type"] == "budget_exceeded"

    def test_create_webhook_invalid_event_type(self, client: TestClient, auth_headers: dict):
        """Should reject invalid event_type."""
        response = client.post(
            "/api/v1/webhooks",
            json={"url": "https://example.com/hook", "event_type": "invalid_type"},
            headers=auth_headers,
        )
        assert response.status_code == 422

    def test_create_webhook_missing_url(self, client: TestClient, auth_headers: dict):
        """Should reject missing URL."""
        response = client.post(
            "/api/v1/webhooks",
            json={"event_type": "budget_warning"},
            headers=auth_headers,
        )
        assert response.status_code == 422

    def test_list_webhooks(self, client: TestClient, auth_headers: dict, test_webhook):
        """Should list user's active webhooks."""
        response = client.get("/api/v1/webhooks", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert "webhooks" in data
        assert len(data["webhooks"]) == 1
        assert data["webhooks"][0]["url"] == "https://example.com/webhook"

    def test_list_webhooks_empty(self, client: TestClient, auth_headers: dict):
        """Should return empty list when no webhooks exist."""
        response = client.get("/api/v1/webhooks", headers=auth_headers)
        assert response.status_code == 200
        assert response.json()["webhooks"] == []

    def test_delete_webhook(self, client: TestClient, auth_headers: dict, test_webhook):
        """Should soft-delete a webhook."""
        response = client.delete(
            f"/api/v1/webhooks/{test_webhook.id}", headers=auth_headers
        )
        assert response.status_code == 200
        assert response.json()["success"] is True

        # Verify it's gone from list
        list_response = client.get("/api/v1/webhooks", headers=auth_headers)
        assert len(list_response.json()["webhooks"]) == 0

    def test_delete_webhook_not_found(self, client: TestClient, auth_headers: dict):
        """Should return 404 for non-existent webhook."""
        response = client.delete(
            "/api/v1/webhooks/nonexistent-id", headers=auth_headers
        )
        assert response.status_code == 404

    def test_webhooks_unauthenticated(self, client: TestClient):
        """All webhook endpoints should require authentication."""
        assert client.get("/api/v1/webhooks").status_code in (401, 403)
        assert client.post(
            "/api/v1/webhooks",
            json={"url": "https://example.com/hook", "event_type": "budget_warning"},
        ).status_code in (401, 403)
        assert client.delete("/api/v1/webhooks/some-id").status_code in (401, 403)
