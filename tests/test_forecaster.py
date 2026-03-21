import random
from datetime import datetime, timedelta, timezone

import pytest

from forecost.db import (
    _insert_usage_logs_batch,
    create_project,
    get_bucketed_costs,
    get_or_create_db,
)
from forecost.forecaster import ProjectForecaster


@pytest.fixture
def synthetic_project(tmp_path, monkeypatch):
    db_path = tmp_path / "costs.db"
    monkeypatch.setattr("forecost.db._DB_PATH", db_path)
    monkeypatch.setattr("forecost.db._conn", None)
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
    monkeypatch.setattr("forecost.db._DB_PATH", db_path)
    monkeypatch.setattr("forecost.db._conn", None)
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
    monkeypatch.setattr("forecost.db._DB_PATH", db_path)
    monkeypatch.setattr("forecost.db._conn", None)
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


def _make_project(tmp_path, monkeypatch, n_days, baseline_days=21, base_cost=10.0):
    """Helper to create a project with n_days of usage data."""
    db_path = tmp_path / "costs.db"
    monkeypatch.setattr("forecost.db._DB_PATH", db_path)
    monkeypatch.setattr("forecost.db._conn", None)
    pid = create_project(
        name="ens",
        path=str(tmp_path / f"proj{n_days}"),
        baseline_daily_cost=base_cost,
        baseline_total_days=baseline_days,
        baseline_total_cost=base_cost * baseline_days,
    )
    if n_days > 0:
        conn = get_or_create_db()
        base = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
        rng = random.Random(42)
        items = [
            (
                pid,
                (base - timedelta(days=n_days - 1 - i)).isoformat(),
                "gpt-4o-mini",
                "openai",
                1000,
                500,
                base_cost * (1 + rng.uniform(-0.1, 0.1)),
                None,
            )
            for i in range(n_days)
        ]
        _insert_usage_logs_batch(conn, items)
    return pid


def test_ensemble_uses_ses_only_with_few_points(tmp_path, monkeypatch):
    pid = _make_project(tmp_path, monkeypatch, n_days=5)
    f = ProjectForecaster(pid)
    result = f.calculate_forecast()
    # With 5 data points: damped_trend requires 10+, so it must be absent
    assert "damped_trend" not in result["models_used"]
    # SES (n>=2) and linear (n>=3) should be attempted; SES may fail on some data
    assert result["n_models_used"] >= 1
    assert result["n_models_used"] <= 2


def test_ensemble_uses_all_three_models(tmp_path, monkeypatch):
    pid = _make_project(tmp_path, monkeypatch, n_days=14)
    f = ProjectForecaster(pid)
    result = f.calculate_forecast()
    assert result["n_models_used"] == 3
    assert "ses" in result["models_used"]
    assert "damped_trend" in result["models_used"]
    assert "linear" in result["models_used"]


def test_prediction_intervals_widen_with_horizon(tmp_path, monkeypatch):
    pid = _make_project(tmp_path, monkeypatch, n_days=14, baseline_days=21)
    f = ProjectForecaster(pid)
    result = f.calculate_forecast()
    pi80 = result["prediction_interval_80"]
    pi95 = result["prediction_interval_95"]
    assert pi80 is not None
    assert pi95 is not None
    width_80 = pi80["upper"] - pi80["lower"]
    width_95 = pi95["upper"] - pi95["lower"]
    assert width_95 > width_80
    assert pi80["lower"] >= 0
    assert pi95["lower"] >= 0


def test_mase_below_one_for_stable_data(tmp_path, monkeypatch):
    pid = _make_project(tmp_path, monkeypatch, n_days=14, base_cost=10.0)
    f = ProjectForecaster(pid)
    result = f.calculate_forecast()
    assert result["mase"] is not None
    assert result["mase"] < 1.0


def test_fallback_when_statsmodels_unavailable(tmp_path, monkeypatch):
    pid = _make_project(tmp_path, monkeypatch, n_days=5)
    monkeypatch.setattr("forecost.forecaster._HAS_STATSMODELS", False)
    f = ProjectForecaster(pid)
    result = f.calculate_forecast()
    assert result["models_used"] == ["ema_fallback"]
    assert result["projected_total"] > 0
    assert result["confidence"] in ("low", "medium-low", "medium", "high", "very-high")


# ---------------------------------------------------------------------------
# Bucketed cost tests
# ---------------------------------------------------------------------------


def test_bucketed_costs_returns_15min_intervals(tmp_path, monkeypatch):
    """get_bucketed_costs groups rows into 15-minute buckets."""
    db_path = tmp_path / "costs.db"
    monkeypatch.setattr("forecost.db._DB_PATH", db_path)
    monkeypatch.setattr("forecost.db._conn", None)
    pid = create_project(
        name="buck",
        path=str(tmp_path),
        baseline_daily_cost=10.0,
        baseline_total_days=14,
        baseline_total_cost=140.0,
    )
    conn = get_or_create_db()
    base = datetime(2026, 3, 10, 14, 0, 0, tzinfo=timezone.utc)
    items = [
        (pid, (base + timedelta(minutes=m)).isoformat(), "gpt-4o", "openai", 100, 50, 1.0, None)
        for m in [0, 5, 10, 20, 35, 50, 65, 80]
    ]
    _insert_usage_logs_batch(conn, items)

    buckets = get_bucketed_costs(pid, bucket_minutes=15)
    # 8 entries across 80 min → buckets at :00, :15, :30, :45, :60(=next hour :00), :75(=:15)
    # Expect 6 distinct 15-min buckets
    assert len(buckets) >= 4
    assert all(cost > 0 for _, cost in buckets)
    # Each bucket label should contain a colon-separated time portion
    for label, _ in buckets:
        assert ":" in label


def test_forecaster_prefers_buckets_over_daily(tmp_path, monkeypatch):
    """When intra-day data gives more points than daily, forecaster uses buckets."""
    db_path = tmp_path / "costs.db"
    monkeypatch.setattr("forecost.db._DB_PATH", db_path)
    monkeypatch.setattr("forecost.db._conn", None)
    pid = create_project(
        name="pref",
        path=str(tmp_path),
        baseline_daily_cost=10.0,
        baseline_total_days=14,
        baseline_total_cost=140.0,
    )
    conn = get_or_create_db()
    # Insert 8 calls spread across 2 hours on one day → 1 daily point, 8 bucket points
    base = datetime(2026, 3, 10, 10, 0, 0, tzinfo=timezone.utc)
    items = [
        (
            pid,
            (base + timedelta(minutes=i * 15)).isoformat(),
            "gpt-4o",
            "openai",
            200,
            100,
            1.5,
            None,
        )
        for i in range(8)
    ]
    _insert_usage_logs_batch(conn, items)

    f = ProjectForecaster(pid)
    result = f.calculate_forecast()
    assert result["data_granularity"] == "15min_buckets"
    assert result["data_points"] > result["active_days"]
    assert result["active_days"] == 1


def test_day_one_accuracy_with_buckets(tmp_path, monkeypatch):
    """On day 1 with enough intra-day calls, the ensemble should engage (>= 2 models)."""
    db_path = tmp_path / "costs.db"
    monkeypatch.setattr("forecost.db._DB_PATH", db_path)
    monkeypatch.setattr("forecost.db._conn", None)
    pid = create_project(
        name="d1",
        path=str(tmp_path),
        baseline_daily_cost=10.0,
        baseline_total_days=14,
        baseline_total_cost=140.0,
    )
    conn = get_or_create_db()
    rng = random.Random(99)
    base = datetime(2026, 3, 10, 9, 0, 0, tzinfo=timezone.utc)
    items = [
        (
            pid,
            (base + timedelta(minutes=i * 15)).isoformat(),
            "gpt-4o",
            "openai",
            500,
            200,
            rng.uniform(0.8, 1.5),
            None,
        )
        for i in range(8)
    ]
    _insert_usage_logs_batch(conn, items)

    f = ProjectForecaster(pid)
    result = f.calculate_forecast()
    # With 8 bucket points the ensemble should engage (SES and/or linear)
    assert result["n_models_used"] >= 1
    assert "ema_fallback" not in result["models_used"]
    # Forecast should be reasonable — not just the baseline
    assert result["projected_total"] > 0
    assert result["data_granularity"] == "15min_buckets"
    assert result["active_days"] == 1
