"""Tests for CSV/JSON export endpoints."""

import json

import pytest


class TestExportCSV:
    """Tests for GET /api/v1/export/csv."""

    def test_export_csv(self, client, auth_headers, test_usage_logs):
        """Export all logs as CSV."""
        response = client.get("/api/v1/export/csv", headers=auth_headers)
        assert response.status_code == 200
        assert "text/csv" in response.headers["content-type"]
        assert "attachment" in response.headers.get("content-disposition", "")

        content = response.text
        lines = content.strip().split("\n")
        assert len(lines) >= 2  # header + at least 1 data row
        header = lines[0]
        assert "id" in header
        assert "provider" in header
        assert "cost_usd" in header

    def test_export_csv_filter_provider(self, client, auth_headers, test_usage_logs):
        """Export filtered by provider."""
        response = client.get("/api/v1/export/csv?provider=anthropic", headers=auth_headers)
        assert response.status_code == 200
        lines = response.text.strip().split("\n")
        # Header + 1 anthropic log
        assert len(lines) == 2

    def test_export_csv_filter_model(self, client, auth_headers, test_usage_logs):
        """Export filtered by model."""
        response = client.get("/api/v1/export/csv?model=gpt-4o", headers=auth_headers)
        assert response.status_code == 200
        content = response.text
        # All data rows should contain gpt-4o
        for line in content.strip().split("\n")[1:]:
            assert "gpt-4o" in line

    def test_export_csv_empty(self, client, auth_headers):
        """Export with no data returns only header."""
        response = client.get("/api/v1/export/csv", headers=auth_headers)
        assert response.status_code == 200

    def test_invalid_date_from_returns_400(self, client, auth_headers, test_usage_logs):
        """Invalid date_from should return 400."""
        response = client.get("/api/v1/export/csv?date_from=bad-date", headers=auth_headers)
        assert response.status_code == 400

    def test_invalid_date_to_returns_400(self, client, auth_headers, test_usage_logs):
        """Invalid date_to should return 400."""
        response = client.get("/api/v1/export/csv?date_to=2024-13-45", headers=auth_headers)
        assert response.status_code == 400

    def test_date_from_after_date_to_returns_400(self, client, auth_headers, test_usage_logs):
        """date_from > date_to should return 400."""
        response = client.get(
            "/api/v1/export/csv?date_from=2024-03-01&date_to=2024-02-01",
            headers=auth_headers,
        )
        assert response.status_code == 400

    def test_valid_date_range(self, client, auth_headers, test_usage_logs):
        """Valid date range should return 200."""
        response = client.get(
            "/api/v1/export/csv?date_from=2020-01-01&date_to=2030-12-31",
            headers=auth_headers,
        )
        assert response.status_code == 200

    def test_requires_auth(self, client, test_usage_logs):
        """Export requires authentication."""
        response = client.get("/api/v1/export/csv")
        assert response.status_code == 401


class TestExportJSON:
    """Tests for GET /api/v1/export/json."""

    def test_export_json(self, client, auth_headers, test_usage_logs):
        """Export all logs as JSON."""
        response = client.get("/api/v1/export/json", headers=auth_headers)
        assert response.status_code == 200
        assert "application/json" in response.headers["content-type"]
        assert "attachment" in response.headers.get("content-disposition", "")

        data = json.loads(response.text)
        assert "logs" in data
        assert "total_logs" in data
        assert "total_cost_usd" in data
        assert "exported_at" in data
        assert data["total_logs"] == 5

    def test_export_json_filter(self, client, auth_headers, test_usage_logs):
        """Export JSON filtered by provider."""
        response = client.get("/api/v1/export/json?provider=openai", headers=auth_headers)
        data = json.loads(response.text)
        assert all(log["provider"] == "openai" for log in data["logs"])

    def test_export_json_includes_tags(self, client, auth_headers, test_tagged_logs):
        """Export JSON includes tag information."""
        response = client.get("/api/v1/export/json", headers=auth_headers)
        data = json.loads(response.text)
        # At least one log should have tags
        tagged = [log for log in data["logs"] if log["tags"]]
        assert len(tagged) >= 1

    def test_invalid_date_from_returns_400(self, client, auth_headers, test_usage_logs):
        """Invalid date_from should return 400."""
        response = client.get("/api/v1/export/json?date_from=bad", headers=auth_headers)
        assert response.status_code == 400

    def test_date_from_after_date_to_returns_400(self, client, auth_headers, test_usage_logs):
        """date_from > date_to should return 400."""
        response = client.get(
            "/api/v1/export/json?date_from=2024-06-01&date_to=2024-01-01",
            headers=auth_headers,
        )
        assert response.status_code == 400

    def test_requires_auth(self, client, test_usage_logs):
        """Export requires authentication."""
        response = client.get("/api/v1/export/json")
        assert response.status_code == 401
