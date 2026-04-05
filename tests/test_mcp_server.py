"""Tests for the ForeCost MCP server tools."""

from __future__ import annotations

import json
import sqlite3
from unittest.mock import MagicMock, patch

import pytest
from pydantic import ValidationError

from forecost.mcp.server import (
    RecentCallsInput,
    TrackCallInput,
    forecost_get_anomalies,
    forecost_get_cost_summary,
    forecost_get_forecast,
    forecost_get_recent_calls,
    forecost_list_projects,
    forecost_track_call,
)

# ---------------------------------------------------------------------------
# Tool 1: forecost_list_projects
# ---------------------------------------------------------------------------


@patch("forecost.mcp.server.get_or_create_db")
def test_list_projects_returns_valid_json(mock_db: MagicMock) -> None:
    """forecost_list_projects returns valid JSON list with 2 projects."""
    mock_conn = MagicMock()
    mock_db.return_value = mock_conn

    row1 = {
        "id": 1,
        "name": "proj-a",
        "path": "/a",
        "baseline_daily_cost": 10.0,
        "baseline_total_days": 30,
        "baseline_total_cost": 300.0,
        "created_at": "2025-01-01T00:00:00",
    }
    row2 = {
        "id": 2,
        "name": "proj-b",
        "path": "/b",
        "baseline_daily_cost": 5.0,
        "baseline_total_days": 60,
        "baseline_total_cost": 300.0,
        "created_at": "2025-02-01T00:00:00",
    }

    mock_row1 = MagicMock()
    mock_row1.keys.return_value = list(row1.keys())
    mock_row1.__iter__ = lambda s: iter(row1.values())
    mock_row1.__getitem__ = lambda s, k: row1[k]

    mock_row2 = MagicMock()
    mock_row2.keys.return_value = list(row2.keys())
    mock_row2.__iter__ = lambda s: iter(row2.values())
    mock_row2.__getitem__ = lambda s, k: row2[k]

    # dict(row) needs to work on the mock rows
    mock_conn.execute.return_value.fetchall.return_value = [row1, row2]

    result = forecost_list_projects()
    data = json.loads(result)
    assert isinstance(data, list)
    assert len(data) == 2
    assert data[0]["name"] == "proj-a"
    assert data[1]["name"] == "proj-b"


# ---------------------------------------------------------------------------
# Tool 2: forecost_get_cost_summary
# ---------------------------------------------------------------------------


@patch("forecost.mcp.server.get_or_create_db")
@patch("forecost.mcp.server.get_daily_costs")
def test_cost_summary_day_returns_totals(mock_daily: MagicMock, mock_db: MagicMock) -> None:
    """forecost_get_cost_summary with group_by='day' returns totals dict."""
    mock_conn = MagicMock()
    mock_db.return_value = mock_conn
    mock_conn.execute.return_value.fetchone.return_value = {"cnt": 7}
    mock_daily.return_value = [
        ("2025-01-01", 5.0, 1000),
        ("2025-01-02", 3.0, 800),
    ]

    result = forecost_get_cost_summary(project_id=1, group_by="day")
    data = json.loads(result)
    assert data["group_by"] == "day"
    assert len(data["data"]) == 2
    assert data["totals"]["total_cost_usd"] == pytest.approx(8.0)
    assert data["totals"]["total_tokens"] == 1800
    assert data["totals"]["total_calls"] == 7


@patch("forecost.mcp.server.get_or_create_db")
def test_cost_summary_model_returns_breakdown(mock_db: MagicMock) -> None:
    """forecost_get_cost_summary with group_by='model' returns model breakdown."""
    mock_conn = MagicMock()
    mock_db.return_value = mock_conn
    mock_conn.execute.return_value.fetchall.return_value = [
        {"model": "gpt-4o", "total_cost": 10.0, "total_tokens": 5000, "call_count": 3},
        {"model": "gpt-4o-mini", "total_cost": 2.0, "total_tokens": 2000, "call_count": 5},
    ]

    result = forecost_get_cost_summary(project_id=1, group_by="model")
    data = json.loads(result)
    assert data["group_by"] == "model"
    assert len(data["data"]) == 2
    assert data["totals"]["total_cost_usd"] == pytest.approx(12.0)
    assert data["totals"]["total_calls"] == 8


# ---------------------------------------------------------------------------
# Tool 3: forecost_get_forecast
# ---------------------------------------------------------------------------


@patch("forecost.mcp.server.ProjectForecaster")
def test_forecast_valid_project(mock_forecaster_cls: MagicMock) -> None:
    """forecost_get_forecast with valid project returns forecast dict."""
    mock_instance = MagicMock()
    mock_forecaster_cls.return_value = mock_instance
    mock_instance.calculate_forecast.return_value = {
        "project_id": 1,
        "projected_total": 250.0,
        "confidence": "high",
        "drift_status": "on_track",
    }

    result = forecost_get_forecast(project_id=1)
    data = json.loads(result)
    assert data["project_id"] == 1
    assert data["projected_total"] == 250.0
    mock_instance.calculate_forecast.assert_called_once_with(save=False)


@patch("forecost.mcp.server.ProjectForecaster")
def test_forecast_invalid_project_returns_error(mock_forecaster_cls: MagicMock) -> None:
    """forecost_get_forecast with invalid project_id returns actionable error."""
    mock_forecaster_cls.side_effect = ValueError("Project 999 not found")

    result = forecost_get_forecast(project_id=999)
    assert "Error" in result
    assert "forecost_list_projects" in result


# ---------------------------------------------------------------------------
# Tool 4: forecost_get_anomalies
# ---------------------------------------------------------------------------


@patch("forecost.mcp.server.ProjectForecaster")
def test_anomalies_over_budget(mock_forecaster_cls: MagicMock) -> None:
    """forecost_get_anomalies with over_budget drift returns recommendation."""
    mock_instance = MagicMock()
    mock_forecaster_cls.return_value = mock_instance
    mock_instance.calculate_forecast.return_value = {
        "drift_status": "over_budget",
        "smoothed_burn_ratio": 2.0,
        "confidence": "high",
        "actual_spend": 100.0,
        "projected_total": 500.0,
        "baseline_total_cost": 300.0,
        "model_breakdown": [{"model": "gpt-4o", "spent": 100.0, "projected": 500.0, "share": 1.0}],
    }

    result = forecost_get_anomalies(project_id=1)
    data = json.loads(result)
    assert data["drift_status"] == "over_budget"
    assert "over baseline" in data["recommendation"]
    assert "lower-tier" in data["recommendation"]
    mock_instance.calculate_forecast.assert_called_once_with(save=False)


@patch("forecost.mcp.server.ProjectForecaster")
def test_anomalies_on_track(mock_forecaster_cls: MagicMock) -> None:
    """forecost_get_anomalies with on_track drift returns 'no anomalies'."""
    mock_instance = MagicMock()
    mock_forecaster_cls.return_value = mock_instance
    mock_instance.calculate_forecast.return_value = {
        "drift_status": "on_track",
        "smoothed_burn_ratio": 1.0,
        "confidence": "medium",
        "actual_spend": 50.0,
        "projected_total": 290.0,
        "baseline_total_cost": 300.0,
        "model_breakdown": [],
    }

    result = forecost_get_anomalies(project_id=1)
    data = json.loads(result)
    assert data["drift_status"] == "on_track"
    assert "No anomalies" in data["recommendation"]


# ---------------------------------------------------------------------------
# Tool 5: forecost_get_recent_calls
# ---------------------------------------------------------------------------


@patch("forecost.mcp.server.get_recent_usage_logs")
def test_recent_calls_returns_list(mock_logs: MagicMock) -> None:
    """forecost_get_recent_calls returns list capped by limit."""
    mock_logs.return_value = [
        {"id": 1, "model": "gpt-4o", "cost_usd": 0.05},
        {"id": 2, "model": "gpt-4o-mini", "cost_usd": 0.01},
    ]

    result = forecost_get_recent_calls(project_id=1, limit=5)
    data = json.loads(result)
    assert isinstance(data, list)
    assert len(data) == 2
    mock_logs.assert_called_once_with(1, 5)


# ---------------------------------------------------------------------------
# Tool 6: forecost_track_call
# ---------------------------------------------------------------------------


@patch("forecost.mcp.server.get_or_create_db")
@patch("forecost.mcp.server.get_provider", return_value="openai")
@patch("forecost.mcp.server.calculate_cost", return_value=0.025)
def test_track_call_auto_calculates_cost(
    mock_calc: MagicMock, mock_provider: MagicMock, mock_db: MagicMock
) -> None:
    """forecost_track_call with cost_usd=None auto-calculates cost."""
    mock_conn = MagicMock()
    mock_db.return_value = mock_conn
    # First execute returns project existence check, second is the INSERT
    mock_conn.execute.return_value.fetchone.return_value = {"id": 1}

    result = forecost_track_call(
        project_id=1, model="gpt-4o", tokens_in=1000, tokens_out=500
    )
    data = json.loads(result)
    assert data["cost_usd"] == pytest.approx(0.025)
    assert data["source"] == "mcp"
    assert data["provider"] == "openai"
    mock_calc.assert_called_once_with("gpt-4o", 1000, 500)
    assert mock_conn.execute.call_count == 2
    mock_conn.commit.assert_called_once()


@patch("forecost.mcp.server.get_or_create_db")
@patch("forecost.mcp.server.get_provider", return_value="anthropic")
@patch("forecost.mcp.server.calculate_cost")
def test_track_call_explicit_cost(
    mock_calc: MagicMock, mock_provider: MagicMock, mock_db: MagicMock
) -> None:
    """forecost_track_call with explicit cost_usd uses that value."""
    mock_conn = MagicMock()
    mock_db.return_value = mock_conn
    mock_conn.execute.return_value.fetchone.return_value = {"id": 1}

    result = forecost_track_call(
        project_id=1,
        model="claude-sonnet-4-20250514",
        tokens_in=2000,
        tokens_out=1000,
        cost_usd=0.10,
    )
    data = json.loads(result)
    assert data["cost_usd"] == pytest.approx(0.10)
    mock_calc.assert_not_called()


# ---------------------------------------------------------------------------
# Input validation
# ---------------------------------------------------------------------------


def test_validation_negative_tokens() -> None:
    """Negative tokens_in raises validation error."""
    with pytest.raises(ValidationError):
        TrackCallInput(
            project_id=1, model="gpt-4o", tokens_in=-1, tokens_out=0
        )


def test_validation_limit_zero() -> None:
    """limit=0 raises validation error."""
    with pytest.raises(ValidationError):
        RecentCallsInput(project_id=1, limit=0)


# ---------------------------------------------------------------------------
# Database error handling
# ---------------------------------------------------------------------------


@patch("forecost.mcp.server.get_or_create_db")
def test_database_error_returns_actionable_message(mock_db: MagicMock) -> None:
    """Database error returns actionable message, not a crash."""
    mock_db.side_effect = sqlite3.OperationalError("disk I/O error")

    result = forecost_list_projects()
    assert "Error" in result
    assert "Database error" in result
    assert "forecost init" in result


# ---------------------------------------------------------------------------
# Additional coverage: provider grouping, days filter, under_budget,
# zero baseline, nonexistent project
# ---------------------------------------------------------------------------


@patch("forecost.mcp.server.get_or_create_db")
def test_cost_summary_provider_grouping(mock_db: MagicMock) -> None:
    """forecost_get_cost_summary with group_by='provider' returns provider breakdown."""
    mock_conn = MagicMock()
    mock_db.return_value = mock_conn
    mock_conn.execute.return_value.fetchall.return_value = [
        {"provider": "openai", "total_cost": 8.0, "total_tokens": 4000, "call_count": 5},
        {"provider": "anthropic", "total_cost": 4.0, "total_tokens": 2000, "call_count": 3},
    ]

    result = forecost_get_cost_summary(project_id=1, group_by="provider")
    data = json.loads(result)
    assert data["group_by"] == "provider"
    assert len(data["data"]) == 2
    assert data["totals"]["total_cost_usd"] == pytest.approx(12.0)
    assert data["totals"]["total_calls"] == 8


@patch("forecost.mcp.server.get_or_create_db")
@patch("forecost.mcp.server.get_daily_costs")
def test_cost_summary_with_days_filter(mock_daily: MagicMock, mock_db: MagicMock) -> None:
    """forecost_get_cost_summary with days=7 filters to recent data only."""
    from datetime import datetime, timedelta, timezone

    today = datetime.now(tz=timezone.utc).date()
    mock_conn = MagicMock()
    mock_db.return_value = mock_conn
    # Return 30 days of data; only recent 7 should survive the filter
    daily_data = [
        ((today - timedelta(days=i)).isoformat(), 5.0, 1000) for i in range(30)
    ]
    mock_daily.return_value = daily_data
    mock_conn.execute.return_value.fetchone.return_value = {"cnt": 7}

    result = forecost_get_cost_summary(project_id=1, group_by="day", days=7)
    data = json.loads(result)
    assert data["group_by"] == "day"
    assert len(data["data"]) <= 8  # 7 days + possible today
    assert data["totals"]["total_calls"] == 7


@patch("forecost.mcp.server.ProjectForecaster")
def test_anomalies_under_budget(mock_forecaster_cls: MagicMock) -> None:
    """forecost_get_anomalies with under_budget drift mentions conservative."""
    mock_instance = MagicMock()
    mock_forecaster_cls.return_value = mock_instance
    mock_instance.calculate_forecast.return_value = {
        "drift_status": "under_budget",
        "smoothed_burn_ratio": 0.3,
        "confidence": "medium",
        "actual_spend": 20.0,
        "projected_total": 80.0,
        "baseline_total_cost": 300.0,
        "model_breakdown": [],
    }

    result = forecost_get_anomalies(project_id=1)
    data = json.loads(result)
    assert data["drift_status"] == "under_budget"
    assert "conservative" in data["recommendation"].lower()


@patch("forecost.mcp.server.ProjectForecaster")
def test_anomalies_zero_baseline(mock_forecaster_cls: MagicMock) -> None:
    """forecost_get_anomalies with baseline_total_cost=0 does not crash."""
    mock_instance = MagicMock()
    mock_forecaster_cls.return_value = mock_instance
    mock_instance.calculate_forecast.return_value = {
        "drift_status": "on_track",
        "smoothed_burn_ratio": 0.0,
        "confidence": "low",
        "actual_spend": 0.0,
        "projected_total": 0.0,
        "baseline_total_cost": 0.0,
        "model_breakdown": [],
    }

    result = forecost_get_anomalies(project_id=1)
    data = json.loads(result)
    assert data["drift_status"] == "on_track"
    assert data["overshoot_pct"] is None
    assert "No anomalies" in data["recommendation"]


@patch("forecost.mcp.server.get_or_create_db")
@patch("forecost.mcp.server.get_provider", return_value="openai")
@patch("forecost.mcp.server.calculate_cost", return_value=0.01)
def test_track_call_nonexistent_project(
    mock_calc: MagicMock, mock_provider: MagicMock, mock_db: MagicMock
) -> None:
    """forecost_track_call with nonexistent project returns error."""
    mock_conn = MagicMock()
    mock_db.return_value = mock_conn
    mock_conn.execute.return_value.fetchone.return_value = None

    result = forecost_track_call(
        project_id=9999, model="gpt-4o", tokens_in=100, tokens_out=50
    )
    assert "Error" in result
    assert "not found" in result
