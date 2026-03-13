import random
from datetime import datetime, timedelta, timezone

import pytest

from llmlab.db import (
    _insert_usage_logs_batch,
    create_project,
    get_or_create_db,
)
from llmlab.forecaster import ProjectForecaster


def generate_synthetic_project(tmp_path, monkeypatch, days=14, base_cost=10.0, noise=0.2):
    db_path = tmp_path / "costs.db"
    monkeypatch.setattr("llmlab.db._DB_PATH", db_path)
    monkeypatch.setattr("llmlab.db._conn", None)
    project_id = create_project(
        name="test",
        path=str(tmp_path),
        baseline_daily_cost=base_cost,
        baseline_total_days=days,
        baseline_total_cost=base_cost * days,
    )
    conn = get_or_create_db()
    actual_daily_costs = []
    base = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    items = []
    for i in range(days):
        mult = 1.0 + random.uniform(-noise, noise)
        cost = base_cost * mult
        actual_daily_costs.append(cost)
        ts = (base - timedelta(days=days - 1 - i)).isoformat()
        items.append((project_id, ts, "gpt-4o-mini", "openai", 1000, 500, cost, None))
    _insert_usage_logs_batch(conn, items)
    return project_id, actual_daily_costs, db_path


def insert_usage_logs(conn, project_id, daily_costs, model="gpt-4o-mini"):
    base = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    items = []
    for i, cost in enumerate(daily_costs):
        ts = (base - timedelta(days=len(daily_costs) - 1 - i)).isoformat()
        items.append((project_id, ts, model, "openai", 1000, 500, cost, None))
    _insert_usage_logs_batch(conn, items)


@pytest.mark.benchmark
def test_accuracy_improves_over_iterations(tmp_path, monkeypatch):
    project_id, actual_costs, db_path = generate_synthetic_project(tmp_path, monkeypatch, days=14)
    monkeypatch.setattr("llmlab.db._DB_PATH", db_path)
    monkeypatch.setattr("llmlab.db._conn", None)
    conn = get_or_create_db()
    conn.execute("DELETE FROM usage_logs WHERE project_id = ?", (project_id,))
    conn.commit()

    def run_forecast_at_day(n):
        conn.execute("DELETE FROM usage_logs WHERE project_id = ?", (project_id,))
        conn.commit()
        insert_usage_logs(conn, project_id, actual_costs[:n])
        f = ProjectForecaster(project_id)
        return f.calculate_forecast()

    r3 = run_forecast_at_day(3)
    actual_3 = sum(actual_costs[:3])
    mape_3 = abs(r3["projected_total"] - actual_3) / actual_3 * 100 if actual_3 > 0 else 0

    r7 = run_forecast_at_day(7)
    actual_7 = sum(actual_costs[:7])
    mape_7 = abs(r7["projected_total"] - actual_7) / actual_7 * 100 if actual_7 > 0 else 0

    r14 = run_forecast_at_day(14)
    actual_14 = sum(actual_costs)
    mape_14 = abs(r14["projected_total"] - actual_14) / actual_14 * 100 if actual_14 > 0 else 0

    assert mape_7 < mape_3
    assert mape_14 < 15


@pytest.mark.benchmark
def test_handles_weekend_gaps(tmp_path, monkeypatch):
    project_id, _, db_path = generate_synthetic_project(tmp_path, monkeypatch, days=14)
    conn = get_or_create_db()
    conn.execute("DELETE FROM usage_logs WHERE project_id = ?", (project_id,))
    conn.commit()
    daily_costs = [10.0 if i not in (5, 6, 12, 13) else 0.0 for i in range(14)]
    items = []
    base = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    for i in range(14):
        if daily_costs[i] > 0:
            ts = (base - timedelta(days=13 - i)).isoformat()
            items.append((project_id, ts, "gpt-4o-mini", "openai", 1000, 500, daily_costs[i], None))
    _insert_usage_logs_batch(conn, items)
    f = ProjectForecaster(project_id)
    result = f.calculate_forecast()
    assert result["projected_total"] > 0
    assert result["projected_total"] < 500


@pytest.mark.benchmark
def test_model_switch_detection(tmp_path, monkeypatch):
    project_id, _, db_path = generate_synthetic_project(tmp_path, monkeypatch, days=14)
    monkeypatch.setattr("llmlab.db._DB_PATH", db_path)
    monkeypatch.setattr("llmlab.db._conn", None)
    conn = get_or_create_db()
    conn.execute("DELETE FROM usage_logs WHERE project_id = ?", (project_id,))
    conn.commit()
    base = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    mini_costs = [1.0] * 7
    gpt4_costs = [15.0] * 7
    for i, cost in enumerate(mini_costs):
        ts = (base - timedelta(days=13 - i)).isoformat()
        conn.execute(
            """
            INSERT INTO usage_logs (project_id, timestamp, model,
                provider, tokens_in, tokens_out, cost_usd, metadata)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (project_id, ts, "gpt-4o-mini", "openai", 1000, 500, cost, None),
        )
    for i, cost in enumerate(gpt4_costs):
        ts = (base - timedelta(days=6 - i)).isoformat()
        conn.execute(
            """
            INSERT INTO usage_logs (project_id, timestamp, model,
                provider, tokens_in, tokens_out, cost_usd, metadata)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (project_id, ts, "gpt-4o", "openai", 1000, 500, cost, None),
        )
    conn.commit()
    f = ProjectForecaster(project_id)
    result = f.calculate_forecast()
    mini_only_projection = 14 * 1.0
    assert result["projected_total"] > mini_only_projection


@pytest.mark.benchmark
def test_scope_drift_detection(tmp_path, monkeypatch):
    project_id, _, db_path = generate_synthetic_project(
        tmp_path, monkeypatch, days=14, base_cost=10.0
    )
    monkeypatch.setattr("llmlab.db._DB_PATH", db_path)
    monkeypatch.setattr("llmlab.db._conn", None)
    conn = get_or_create_db()
    conn.execute("DELETE FROM usage_logs WHERE project_id = ?", (project_id,))
    conn.commit()
    daily_costs = [10.0] * 9 + [20.0] * 5
    base = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    for i, cost in enumerate(daily_costs):
        ts = (base - timedelta(days=13 - i)).isoformat()
        conn.execute(
            """
            INSERT INTO usage_logs (project_id, timestamp, model,
                provider, tokens_in, tokens_out, cost_usd, metadata)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (project_id, ts, "gpt-4o-mini", "openai", 1000, 500, cost, None),
        )
    conn.commit()
    f = ProjectForecaster(project_id)
    result = f.calculate_forecast()
    assert result["drift_status"] == "over_budget"
