from datetime import datetime, timedelta, timezone

import pytest

from llmlab.db import (
    _insert_usage_logs_batch,
    create_project,
    get_or_create_db,
)
from llmlab.forecaster import ProjectForecaster


@pytest.fixture
def synthetic_project(tmp_path, monkeypatch):
    db_path = tmp_path / "costs.db"
    monkeypatch.setattr("llmlab.db._DB_PATH", db_path)
    monkeypatch.setattr("llmlab.db._conn", None)
    pid = create_project(
        name="fc",
        path=str(tmp_path),
        baseline_daily_cost=10.0,
        baseline_total_days=14,
        baseline_total_cost=140.0,
    )
    conn = get_or_create_db()
    base = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    items = [
        (
            pid,
            (base - timedelta(days=13 - i)).isoformat(),
            "gpt-4o-mini",
            "openai",
            1000,
            500,
            10.0,
            None,
        )
        for i in range(14)
    ]
    _insert_usage_logs_batch(conn, items)
    return pid


def test_project_forecaster_with_synthetic_data(synthetic_project):
    f = ProjectForecaster(synthetic_project)
    result = f.calculate_forecast()
    assert result["project_id"] == synthetic_project
    assert result["actual_spend"] == 140.0
    assert result["projected_total"] > 0
    assert result["active_days"] == 14
    assert "confidence" in result
    assert "drift_status" in result


def test_confidence_scoring_at_different_day_counts(tmp_path, monkeypatch):
    db_path = tmp_path / "costs.db"
    monkeypatch.setattr("llmlab.db._DB_PATH", db_path)
    monkeypatch.setattr("llmlab.db._conn", None)
    pid = create_project(
        name="conf",
        path=str(tmp_path),
        baseline_daily_cost=5.0,
        baseline_total_days=14,
        baseline_total_cost=70.0,
    )
    conn = get_or_create_db()
    base = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)

    # Explicitly test n=0 (project with 0 usage data)
    conn.execute("DELETE FROM usage_logs WHERE project_id = ?", (pid,))
    conn.commit()
    f = ProjectForecaster(pid)
    result = f.calculate_forecast()
    assert result["confidence"] == "low"

    for n, expected_conf in [(2, "medium-low"), (5, "medium"), (10, "high")]:
        conn.execute("DELETE FROM usage_logs WHERE project_id = ?", (pid,))
        conn.commit()
        items = [
            (
                pid,
                (base - timedelta(days=n - 1 - i)).isoformat(),
                "gpt-4o-mini",
                "openai",
                100,
                50,
                1.0,
                None,
            )
            for i in range(n)
        ]
        _insert_usage_logs_batch(conn, items)
        f = ProjectForecaster(pid)
        result = f.calculate_forecast()
        assert result["confidence"] == expected_conf


def test_drift_detection_over_budget(tmp_path, monkeypatch):
    db_path = tmp_path / "costs.db"
    monkeypatch.setattr("llmlab.db._DB_PATH", db_path)
    monkeypatch.setattr("llmlab.db._conn", None)
    pid = create_project(
        name="drift",
        path=str(tmp_path),
        baseline_daily_cost=10.0,
        baseline_total_days=14,
        baseline_total_cost=140.0,
    )
    conn = get_or_create_db()
    base = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    daily_costs = [10.0] * 9 + [20.0] * 5
    items = [
        (
            pid,
            (base - timedelta(days=13 - i)).isoformat(),
            "gpt-4o-mini",
            "openai",
            1000,
            500,
            c,
            None,
        )
        for i, c in enumerate(daily_costs)
    ]
    _insert_usage_logs_batch(conn, items)
    f = ProjectForecaster(pid)
    result = f.calculate_forecast()
    assert result["drift_status"] == "over_budget"
