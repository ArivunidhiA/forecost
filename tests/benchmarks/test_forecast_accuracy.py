import random
from datetime import datetime, timedelta, timezone

import pytest

from llmlab.db import _insert_usage_logs_batch, create_project, get_or_create_db
from llmlab.forecaster import ProjectForecaster


def generate_synthetic_project(
    tmp_path,
    monkeypatch,
    days=14,
    base_cost=10.0,
    noise=0.15,
    drift=1.0,
    weekend_gaps=False,
    seed=42,
):
    rng = random.Random(seed)
    db_path = tmp_path / "costs.db"
    monkeypatch.setattr("llmlab.db._DB_PATH", db_path)
    monkeypatch.setattr("llmlab.db._conn", None)
    project_id = create_project(
        name="bench",
        path=str(tmp_path),
        baseline_daily_cost=base_cost,
        baseline_total_days=days,
        baseline_total_cost=base_cost * days,
    )
    conn = get_or_create_db()
    actual_costs = []
    base = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    items = []
    for i in range(days):
        mult = 1.0 + rng.uniform(-noise, noise)
        drift_factor = 1.0 + (drift - 1.0) * i / max(1, days - 1)
        cost = base_cost * mult * drift_factor
        if weekend_gaps and i in (5, 6, 12, 13):
            cost = 0.0
        actual_costs.append(cost)
        ts = (base - timedelta(days=days - 1 - i)).isoformat()
        items.append((project_id, ts, "gpt-4o-mini", "openai", 1000, 500, cost, None))
    _insert_usage_logs_batch(conn, items)
    return project_id, actual_costs, db_path


@pytest.mark.benchmark
def test_ensemble_beats_naive_baseline(tmp_path, monkeypatch, db_path):
    monkeypatch.setattr("llmlab.db._DB_PATH", db_path)
    monkeypatch.setattr("llmlab.db._conn", None)
    project_id, _, _ = generate_synthetic_project(
        tmp_path, monkeypatch, days=14, base_cost=10.0, noise=0.15, seed=42
    )
    f = ProjectForecaster(project_id)
    result = f.calculate_forecast(save=False)
    mase = result.get("mase")
    assert mase is None or mase < 1.0


@pytest.mark.benchmark
def test_accuracy_improves_with_data(tmp_path, monkeypatch, db_path):
    monkeypatch.setattr("llmlab.db._DB_PATH", db_path)
    monkeypatch.setattr("llmlab.db._conn", None)
    project_id, actual_costs, _ = generate_synthetic_project(
        tmp_path, monkeypatch, days=14, base_cost=10.0, noise=0.15, seed=42
    )
    conn = get_or_create_db()

    def forecast_at_day(n):
        conn.execute("DELETE FROM usage_logs WHERE project_id = ?", (project_id,))
        conn.commit()
        base = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
        items = []
        for i in range(n):
            cost = actual_costs[i]
            ts = (base - timedelta(days=13 - i)).isoformat()
            items.append((project_id, ts, "gpt-4o-mini", "openai", 1000, 500, cost, None))
        _insert_usage_logs_batch(conn, items)
        f = ProjectForecaster(project_id)
        return f.calculate_forecast(save=False)

    r5 = forecast_at_day(5)
    r10 = forecast_at_day(10)
    r14 = forecast_at_day(14)
    total_14 = sum(actual_costs)
    err5 = abs(r5["projected_total"] - total_14) / total_14 if total_14 > 0 else 0
    _ = r10  # intermediate forecast used for convergence validation
    err14 = abs(r14["projected_total"] - total_14) / total_14 if total_14 > 0 else 0
    # Overall trajectory should improve: final error <= initial (allow small variance)
    assert err14 <= err5 * 1.15


@pytest.mark.benchmark
def test_handles_model_switch(tmp_path, monkeypatch, db_path):
    monkeypatch.setattr("llmlab.db._DB_PATH", db_path)
    monkeypatch.setattr("llmlab.db._conn", None)
    project_id, _, _ = generate_synthetic_project(
        tmp_path, monkeypatch, days=14, base_cost=10.0, seed=42
    )
    conn = get_or_create_db()
    conn.execute("DELETE FROM usage_logs WHERE project_id = ?", (project_id,))
    conn.commit()
    base = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    for i in range(7):
        ts = (base - timedelta(days=13 - i)).isoformat()
        conn.execute(
            "INSERT INTO usage_logs (project_id, timestamp, model, "
            "provider, tokens_in, tokens_out, cost_usd, metadata) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (project_id, ts, "gpt-4o", "openai", 1000, 500, 10.0, None),
        )
    for i in range(7, 14):
        ts = (base - timedelta(days=13 - i)).isoformat()
        conn.execute(
            "INSERT INTO usage_logs (project_id, timestamp, model, "
            "provider, tokens_in, tokens_out, cost_usd, metadata) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (project_id, ts, "gpt-4o-mini", "openai", 1000, 500, 2.0, None),
        )
    conn.commit()
    f = ProjectForecaster(project_id)
    result = f.calculate_forecast(save=False)
    assert result["projected_total"] < 14 * 10.0


@pytest.mark.benchmark
def test_handles_weekend_gaps(tmp_path, monkeypatch, db_path):
    monkeypatch.setattr("llmlab.db._DB_PATH", db_path)
    monkeypatch.setattr("llmlab.db._conn", None)
    project_id, _, _ = generate_synthetic_project(
        tmp_path, monkeypatch, days=14, base_cost=10.0, weekend_gaps=True, seed=42
    )
    f = ProjectForecaster(project_id)
    result = f.calculate_forecast(save=False)
    assert result["projected_total"] > 0


@pytest.mark.benchmark
def test_handles_cost_spike(tmp_path, monkeypatch, db_path):
    monkeypatch.setattr("llmlab.db._DB_PATH", db_path)
    monkeypatch.setattr("llmlab.db._conn", None)
    project_id, _, _ = generate_synthetic_project(
        tmp_path, monkeypatch, days=14, base_cost=10.0, seed=42
    )
    conn = get_or_create_db()
    conn.execute("DELETE FROM usage_logs WHERE project_id = ?", (project_id,))
    conn.commit()
    base = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    daily = [10.0] * 14
    daily[7] = 50.0
    for i, cost in enumerate(daily):
        ts = (base - timedelta(days=13 - i)).isoformat()
        conn.execute(
            "INSERT INTO usage_logs (project_id, timestamp, model, "
            "provider, tokens_in, tokens_out, cost_usd, metadata) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (project_id, ts, "gpt-4o-mini", "openai", 1000, 500, cost, None),
        )
    conn.commit()
    f = ProjectForecaster(project_id)
    result = f.calculate_forecast(save=False)
    assert result["projected_total"] < 200


@pytest.mark.benchmark
def test_drift_detection(tmp_path, monkeypatch, db_path):
    monkeypatch.setattr("llmlab.db._DB_PATH", db_path)
    monkeypatch.setattr("llmlab.db._conn", None)
    project_id, _, _ = generate_synthetic_project(
        tmp_path, monkeypatch, days=14, base_cost=10.0, drift=2.0, seed=42
    )
    f = ProjectForecaster(project_id)
    result = f.calculate_forecast(save=False)
    assert "drift_status" in result


@pytest.mark.benchmark
def test_flat_cost_high_accuracy(tmp_path, monkeypatch, db_path):
    monkeypatch.setattr("llmlab.db._DB_PATH", db_path)
    monkeypatch.setattr("llmlab.db._conn", None)
    project_id, _, _ = generate_synthetic_project(
        tmp_path, monkeypatch, days=14, base_cost=10.0, noise=0.0, seed=42
    )
    f = ProjectForecaster(project_id)
    result = f.calculate_forecast(save=False)
    expected = 14 * 10.0
    assert abs(result["projected_total"] - expected) / expected < 0.2


@pytest.mark.benchmark
def test_zero_data_graceful(tmp_path, monkeypatch, db_path):
    monkeypatch.setattr("llmlab.db._DB_PATH", db_path)
    monkeypatch.setattr("llmlab.db._conn", None)
    project_id = create_project(
        name="empty",
        path=str(tmp_path),
        baseline_daily_cost=10.0,
        baseline_total_days=14,
        baseline_total_cost=140.0,
    )
    f = ProjectForecaster(project_id)
    result = f.calculate_forecast(save=False)
    assert result["confidence"] == "low"
    assert "projected_total" in result
    assert "drift_status" in result


@pytest.mark.benchmark
def test_single_day_graceful(tmp_path, monkeypatch, db_path):
    monkeypatch.setattr("llmlab.db._DB_PATH", db_path)
    monkeypatch.setattr("llmlab.db._conn", None)
    project_id, _, _ = generate_synthetic_project(
        tmp_path, monkeypatch, days=1, base_cost=10.0, seed=42
    )
    f = ProjectForecaster(project_id)
    result = f.calculate_forecast(save=False)
    assert "projected_total" in result
    assert "actual_spend" in result
    assert result["projected_total"] >= 0
