"""Tests for export endpoint authentication via Authorization header (not URL tokens)."""

import pytest


class TestExportAuth:
    """Verify export endpoints use proper header-based auth."""

    def test_csv_export_with_bearer_auth(self, client, auth_headers, test_usage_logs):
        """CSV export with Authorization: Bearer header should succeed."""
        response = client.get("/api/v1/export/csv", headers=auth_headers)
        assert response.status_code == 200
        assert "text/csv" in response.headers["content-type"]

    def test_csv_export_without_auth_returns_401(self, client, test_usage_logs):
        """CSV export without auth should return 401."""
        response = client.get("/api/v1/export/csv")
        assert response.status_code == 401

    def test_json_export_with_bearer_auth(self, client, auth_headers, test_usage_logs):
        """JSON export with Authorization: Bearer header should succeed."""
        response = client.get("/api/v1/export/json", headers=auth_headers)
        assert response.status_code == 200
        assert "application/json" in response.headers["content-type"]

    def test_json_export_without_auth_returns_401(self, client, test_usage_logs):
        """JSON export without auth should return 401."""
        response = client.get("/api/v1/export/json")
        assert response.status_code == 401

    def test_csv_export_has_attachment_header(self, client, auth_headers, test_usage_logs):
        """CSV export should have Content-Disposition: attachment header."""
        response = client.get("/api/v1/export/csv", headers=auth_headers)
        assert response.status_code == 200
        assert "attachment" in response.headers.get("content-disposition", "")
        assert "filename=" in response.headers.get("content-disposition", "")

    def test_json_export_has_attachment_header(self, client, auth_headers, test_usage_logs):
        """JSON export should have Content-Disposition: attachment header."""
        response = client.get("/api/v1/export/json", headers=auth_headers)
        assert response.status_code == 200
        assert "attachment" in response.headers.get("content-disposition", "")
