from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from forecost.db import _insert_usage_logs_batch, create_project, get_or_create_db
from forecost.forecaster import ProjectForecaster
from forecost.pricing import calculate_cost


@pytest.mark.benchmark
def test_benchmark_calculate_cost_hot_path(benchmark) -> None:
    benchmark(lambda: calculate_cost("gpt-4o-mini", 12_000, 6_000))


@pytest.mark.benchmark
def test_benchmark_project_forecast_hot_path(db_path, benchmark) -> None:
    project_id = create_project(
        name="bench-hot",
        path=str(db_path.parent / "bench-hot"),
        baseline_daily_cost=6.0,
        baseline_total_days=14,
        baseline_total_cost=84.0,
    )
    conn = get_or_create_db()
    base = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)

    items = []
    for i in range(14):
        ts = (base - timedelta(days=13 - i)).isoformat()
        items.append((project_id, ts, "gpt-4o-mini", "openai", 1500, 700, 6.0 + (i % 3), None))

    _insert_usage_logs_batch(conn, items)

    forecaster = ProjectForecaster(project_id)
    result = benchmark(lambda: forecaster.calculate_forecast(save=False))
    assert result["projected_total"] > 0
