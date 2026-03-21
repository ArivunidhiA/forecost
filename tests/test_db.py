from datetime import datetime, timezone

import pytest

from forecost.db import (
    WriteQueue,
    create_project,
    get_active_days,
    get_bucketed_costs,
    get_daily_costs,
    get_forecast_history,
    get_or_create_db,
    get_project_by_path,
    save_forecast,
)


@pytest.fixture
def db_path(tmp_path, monkeypatch):
    path = tmp_path / "costs.db"
    monkeypatch.setattr("forecost.db._DB_PATH", path)
    monkeypatch.setattr("forecost.db._conn", None)
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def test_create_project_and_get_project_by_path(db_path):
    pid = create_project(
        name="foo",
        path="/tmp/foo",
        baseline_daily_cost=5.0,
        baseline_total_days=14,
        baseline_total_cost=70.0,
    )
    assert pid > 0
    proj = get_project_by_path("/tmp/foo")
    assert proj is not None
    assert proj["name"] == "foo"
    assert proj["path"] == "/tmp/foo"
    assert proj["baseline_daily_cost"] == 5.0
    assert proj["baseline_total_days"] == 14
    assert proj["baseline_total_cost"] == 70.0
    assert get_project_by_path("/nonexistent") is None


def test_write_queue_puts_and_flushes(db_path):
    pid = create_project(
        name="qtest",
        path="/tmp/qtest",
        baseline_daily_cost=1.0,
        baseline_total_days=7,
        baseline_total_cost=7.0,
    )
    q = WriteQueue()
    ts = datetime.now(timezone.utc).isoformat()
    for i in range(5):
        q.put(pid, ts, "gpt-4o-mini", "openai", 100, 50, 0.01 * (i + 1), None)
    q._queue.put(None)
    q._thread.join(timeout=3.0)
    costs = get_daily_costs(pid)
    assert len(costs) >= 1
    total = sum(c for _, c in costs)
    assert total > 0


def test_get_daily_costs_and_get_active_days(db_path):
    pid = create_project(
        name="costs",
        path="/tmp/costs",
        baseline_daily_cost=2.0,
        baseline_total_days=10,
        baseline_total_cost=20.0,
    )
    conn = get_or_create_db()
    ts1 = "2024-01-01T12:00:00+00:00"
    ts2 = "2024-01-02T12:00:00+00:00"
    conn.executemany(
        """
        INSERT INTO usage_logs (project_id, timestamp, model,
            provider, tokens_in, tokens_out, cost_usd, metadata)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        [
            (pid, ts1, "gpt-4o", "openai", 1000, 500, 5.0, None),
            (pid, ts1, "gpt-4o", "openai", 500, 200, 2.0, None),
            (pid, ts2, "gpt-4o-mini", "openai", 100, 50, 0.5, None),
        ],
    )
    conn.commit()
    costs = get_daily_costs(pid)
    assert len(costs) == 2
    days = {d for d, _ in costs}
    assert "2024-01-01" in days
    assert "2024-01-02" in days
    assert sum(c for _, c in costs) == 7.5
    assert get_active_days(pid) == 2


def test_save_forecast_and_get_forecast_history(db_path):
    pid = create_project(
        name="fc",
        path="/tmp/fc",
        baseline_daily_cost=3.0,
        baseline_total_days=14,
        baseline_total_cost=42.0,
    )
    fid = save_forecast(
        project_id=pid,
        iteration=1,
        projected_total=45.0,
        projected_remaining_days=12,
        smoothed_burn_ratio=1.1,
        confidence="medium",
        active_days_count=2,
        mape=8.5,
    )
    assert fid > 0
    history = get_forecast_history(pid)
    assert len(history) == 1
    assert history[0]["projected_total"] == 45.0
    assert history[0]["iteration"] == 1
    assert history[0]["mape"] == 8.5


def test_bucketed_costs_zero_minutes_raises(db_path):
    pid = create_project(
        name="bk0",
        path="/tmp/bk0",
        baseline_daily_cost=1.0,
        baseline_total_days=7,
        baseline_total_cost=7.0,
    )
    with pytest.raises(ValueError, match="bucket_minutes must be >= 1"):
        get_bucketed_costs(pid, bucket_minutes=0)


def test_create_project_duplicate_path_raises(db_path):
    create_project(
        name="dup",
        path="/tmp/dup",
        baseline_daily_cost=1.0,
        baseline_total_days=7,
        baseline_total_cost=7.0,
    )
    import sqlite3

    with pytest.raises(sqlite3.IntegrityError):
        create_project(
            name="dup2",
            path="/tmp/dup",
            baseline_daily_cost=2.0,
            baseline_total_days=14,
            baseline_total_cost=28.0,
        )


def test_write_queue_on_exit_handles_full_queue(db_path):
    """_on_exit doesn't raise even if the internal queue is at capacity."""
    q = WriteQueue()
    dummy = (1, "2026-01-01T00:00:00Z", "m", "p", 0, 0, 0.0, None)
    for _ in range(10_000):
        try:
            q._queue.put_nowait(dummy)
        except Exception:
            break
    # _on_exit should not raise even when queue is full
    q._on_exit()


def test_calculate_cost_zero_tokens():
    from forecost.pricing import calculate_cost

    assert calculate_cost("gpt-4o", 0, 0) == 0.0


def test_forecaster_nonexistent_project_raises(db_path):
    from forecost.forecaster import ProjectForecaster

    with pytest.raises(ValueError, match="Project 99999 not found"):
        ProjectForecaster(99999)
