from __future__ import annotations

import math
from datetime import datetime, timedelta, timezone

import pytest

from forecost.db import (
    _insert_usage_logs_batch,
    create_project,
    get_bucketed_costs,
    get_or_create_db,
)
from forecost.forecaster import ProjectForecaster
from forecost.pricing import calculate_cost


def test_get_project_by_path_sql_injection_string_returns_none(db_path) -> None:
    from forecost.db import get_project_by_path

    malicious = "' OR 1=1; DROP TABLE projects; --"
    assert get_project_by_path(malicious) is None


def test_calculate_cost_handles_very_large_tokens() -> None:
    cost = calculate_cost("gpt-4o", 10**12, 10**12)
    assert cost > 0.0
    assert math.isfinite(cost)


def test_get_bucketed_costs_rejects_negative_minutes(db_path) -> None:
    pid = create_project(
        name="edge-bucket",
        path="/tmp/edge-bucket",
        baseline_daily_cost=1.0,
        baseline_total_days=7,
        baseline_total_cost=7.0,
    )
    with pytest.raises(ValueError) as exc:
        get_bucketed_costs(pid, bucket_minutes=-5)
    assert "bucket_minutes" in str(exc.value)


def test_forecaster_handles_zero_baseline_with_usage_data(db_path) -> None:
    pid = create_project(
        name="edge-forecast",
        path="/tmp/edge-forecast",
        baseline_daily_cost=0.0,
        baseline_total_days=10,
        baseline_total_cost=0.0,
    )
    conn = get_or_create_db()
    base = datetime.now(timezone.utc).replace(hour=12, minute=0, second=0, microsecond=0)
    items = [
        (
            pid,
            (base - timedelta(days=4 - i)).isoformat(),
            "gpt-4o-mini",
            "openai",
            1000,
            500,
            1.0 + i,
            None,
        )
        for i in range(5)
    ]
    _insert_usage_logs_batch(conn, items)

    result = ProjectForecaster(pid).calculate_forecast(save=False)
    assert result["projected_total"] >= result["actual_spend"]
    assert result["confidence"] in {"low", "medium-low", "medium", "high", "very-high"}
