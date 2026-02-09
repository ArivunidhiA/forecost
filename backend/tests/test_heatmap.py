"""
Tests for the usage heatmap endpoint.
"""

import pytest
from fastapi.testclient import TestClient


class TestHeatmap:
    def test_get_heatmap(self, client: TestClient, auth_headers: dict, test_usage_logs):
        """Should return heatmap cells with correct structure."""
        response = client.get("/api/v1/stats/heatmap", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert "cells" in data
        assert isinstance(data["cells"], list)

        # Should have some cells from our test logs
        assert len(data["cells"]) > 0

        # Each cell should have the right structure
        for cell in data["cells"]:
            assert "day" in cell
            assert "hour" in cell
            assert "call_count" in cell
            assert "cost_usd" in cell
            assert 0 <= cell["day"] <= 6
            assert 0 <= cell["hour"] <= 23
            assert cell["call_count"] > 0

    def test_get_heatmap_empty(self, client: TestClient, auth_headers: dict):
        """Should return empty cells when no usage data exists."""
        response = client.get("/api/v1/stats/heatmap", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert data["cells"] == []

    def test_get_heatmap_aggregation(self, client: TestClient, auth_headers: dict, test_usage_logs):
        """Cells on the same day/hour should be aggregated."""
        response = client.get("/api/v1/stats/heatmap", headers=auth_headers)
        data = response.json()

        # Verify no duplicate (day, hour) pairs
        seen = set()
        for cell in data["cells"]:
            key = (cell["day"], cell["hour"])
            assert key not in seen, f"Duplicate cell for day={cell['day']}, hour={cell['hour']}"
            seen.add(key)

    def test_get_heatmap_unauthenticated(self, client: TestClient):
        """Should reject unauthenticated requests."""
        response = client.get("/api/v1/stats/heatmap")
        assert response.status_code in (401, 403)
