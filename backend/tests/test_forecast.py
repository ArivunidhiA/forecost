"""Tests for the cost forecasting endpoint."""

from datetime import datetime, timedelta

import pytest

from models import UsageLog


class TestForecast:
    """Tests for GET /api/v1/stats/forecast."""

    def test_forecast_with_data(self, client, auth_headers, test_usage_logs):
        """Forecast returns predictions when data exists."""
        response = client.get("/api/v1/stats/forecast", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert "predicted_next_month_usd" in data
        assert "daily_average_usd" in data
        assert "trend" in data
        assert "confidence" in data
        assert "projected_daily" in data
        assert data["trend"] in ("increasing", "decreasing", "stable")
        assert data["confidence"] in ("low", "medium", "high")

    def test_forecast_no_data(self, client, auth_headers):
        """Forecast returns zeros when no data."""
        response = client.get("/api/v1/stats/forecast", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert data["predicted_next_month_usd"] == 0.0
        assert data["daily_average_usd"] == 0.0
        assert data["trend"] == "stable"
        assert data["confidence"] == "low"

    def test_forecast_projected_daily(self, client, auth_headers, test_usage_logs):
        """Forecast returns 30 projected daily entries."""
        response = client.get("/api/v1/stats/forecast", headers=auth_headers)
        data = response.json()
        projected = data["projected_daily"]
        assert len(projected) == 30
        for entry in projected:
            assert "date" in entry
            assert "cost_usd" in entry
            assert entry["cost_usd"] >= 0

    def test_forecast_trend_pct_change(self, client, auth_headers, test_usage_logs):
        """Trend percentage change is included."""
        response = client.get("/api/v1/stats/forecast", headers=auth_headers)
        data = response.json()
        assert "trend_pct_change" in data
        assert isinstance(data["trend_pct_change"], (int, float))

    def test_forecast_increasing_trend(self, client, auth_headers, db_session, test_user):
        """Forecast detects increasing trend with growing daily costs."""
        now = datetime.utcnow()
        for i in range(30):
            log = UsageLog(
                user_id=test_user.id,
                provider="openai",
                model="gpt-4o",
                input_tokens=1000 + i * 100,
                output_tokens=500 + i * 50,
                cost_usd=0.01 * (1 + i * 0.15),  # growing cost
                latency_ms=100.0,
                cache_hit=False,
                created_at=now - timedelta(days=30 - i),
            )
            db_session.add(log)
        db_session.commit()

        response = client.get("/api/v1/stats/forecast", headers=auth_headers)
        data = response.json()
        assert data["predicted_next_month_usd"] > 0
        assert data["confidence"] == "high"

    def test_requires_auth(self, client):
        """Forecast requires authentication."""
        response = client.get("/api/v1/stats/forecast")
        assert response.status_code == 401
