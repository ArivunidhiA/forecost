from __future__ import annotations

import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

import hypothesis.strategies as st
from hypothesis import given
import pytest

from forecost.db import _insert_usage_logs_batch, create_project, get_active_days, get_or_create_db
from forecost.pricing import DEFAULT_COST, calculate_cost
from forecost.tracker import get_session_summary, log_call


@given(
    model=st.text(min_size=1, max_size=64),
    tokens_in=st.integers(min_value=0, max_value=10_000_000),
    tokens_out=st.integers(min_value=0, max_value=10_000_000),
)
def test_calculate_cost_is_never_negative(model: str, tokens_in: int, tokens_out: int) -> None:
    assert calculate_cost(model, tokens_in, tokens_out) >= 0.0


@given(
    base_in=st.integers(min_value=0, max_value=5_000_000),
    base_out=st.integers(min_value=0, max_value=5_000_000),
    extra_in=st.integers(min_value=0, max_value=5_000_000),
    extra_out=st.integers(min_value=0, max_value=5_000_000),
)
def test_known_model_cost_is_monotonic(
    base_in: int, base_out: int, extra_in: int, extra_out: int
) -> None:
    low = calculate_cost("gpt-4o-mini", base_in, base_out)
    high = calculate_cost("gpt-4o-mini", base_in + extra_in, base_out + extra_out)
    assert high >= low


@given(
    model_suffix=st.text(
        alphabet=st.characters(blacklist_categories=("Cs",)),
        min_size=1,
        max_size=24,
    ),
    tokens_in=st.integers(min_value=0, max_value=10_000_000),
    tokens_out=st.integers(min_value=0, max_value=10_000_000),
)
def test_unknown_model_uses_default_rate(
    model_suffix: str, tokens_in: int, tokens_out: int
) -> None:
    model = f"zz-unknown-{model_suffix}"
    expected = (tokens_in / 1_000_000) * DEFAULT_COST["input"] + (
        (tokens_out / 1_000_000) * DEFAULT_COST["output"]
    )
    assert calculate_cost(model, tokens_in, tokens_out) == expected


@given(
    calls=st.lists(
        st.tuples(
            st.integers(min_value=0, max_value=20_000),
            st.integers(min_value=0, max_value=20_000),
        ),
        min_size=1,
        max_size=25,
    )
)
def test_log_call_accumulates_consistent_session_totals(calls: list[tuple[int, int]]) -> None:
    import forecost.tracker as tracker_mod

    with pytest.MonkeyPatch.context() as patch:
        tracker_mod._session_stats = {}
        patch.setattr("forecost.tracker._find_project", lambda: None)

        for tokens_in, tokens_out in calls:
            log_call("gpt-4o-mini", tokens_in, tokens_out)

        summary = get_session_summary()
        assert summary["calls"] == len(calls)
        expected_tokens = sum(tokens_in + tokens_out for tokens_in, tokens_out in calls)
        assert summary["total_tokens"] == expected_tokens
        assert summary["total_cost"] >= 0.0


@given(
    n_days=st.integers(min_value=1, max_value=12),
    costs=st.lists(
        st.floats(min_value=0.0, max_value=100.0, allow_nan=False, allow_infinity=False),
        min_size=1,
        max_size=12,
    ),
)
def test_active_days_never_exceeds_inserted_distinct_days(n_days: int, costs: list[float]) -> None:
    with tempfile.TemporaryDirectory() as tmp_dir:
        db_path = Path(tmp_dir) / "costs.db"
        conn = None
        try:
            with pytest.MonkeyPatch.context() as patch:
                patch.setattr("forecost.db._DB_PATH", db_path)
                patch.setattr("forecost.db._conn", None)

                pid = create_project(
                    name="prop-db",
                    path=str(Path(tmp_dir) / f"proj-{n_days}"),
                    baseline_daily_cost=5.0,
                    baseline_total_days=14,
                    baseline_total_cost=70.0,
                )
                conn = get_or_create_db()
                base = datetime(2026, 1, 1, tzinfo=timezone.utc)

                items = []
                for i in range(n_days):
                    day_ts = (base + timedelta(days=i)).isoformat()
                    cost = float(costs[i % len(costs)])
                    items.append((pid, day_ts, "gpt-4o-mini", "openai", 100, 50, cost, None))

                _insert_usage_logs_batch(conn, items)
                assert get_active_days(pid) <= n_days
        finally:
            if conn is not None:
                conn.close()

            import forecost.db as db_mod

            if hasattr(db_mod, "_conn") and db_mod._conn is not None:
                try:
                    db_mod._conn.close()
                except Exception:
                    pass
                db_mod._conn = None
