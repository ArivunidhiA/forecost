"""Estimator v0: hierarchical empirical quantiles with shrinkage toward global.

Matches the method validated (as MARGINAL, not yet PASS) by the calibration
experiment this session (experiments/calib/backtest.py, VERDICT.md): the category
log-quantiles are shrunk toward the *global* log-quantiles by weight w = n/(n+k),
NOT scaled toward zero (the deep-audit P0 bug this file used to have). Consumes the
ledger read-only via forecost.ledger.queries; writes only to the `estimates`
table (never to usage_events/postings).

Cold start: fewer than MIN_CELL_N historical values in a category falls back
to the global distribution and is labeled confidence='low', caveat='cold_start'.
"""

from __future__ import annotations

import math
import sqlite3
import uuid
from datetime import datetime, timezone

from forecost.estimate.types import EstimateRange, TaskContext
from forecost.ledger import queries as q

SHRINK_K = 10
MIN_CELL_N = 3
GLOBAL_CATEGORY_FALLBACK_N = 30


def _log_quantiles(values: list[float]) -> tuple[float, float, float]:
    logs = [math.log1p(max(0.0, v)) for v in values]
    logs.sort()
    n = len(logs)

    def pct(p: float) -> float:
        idx = p * (n - 1)
        lo, hi = int(idx), min(int(idx) + 1, n - 1)
        frac = idx - lo
        return logs[lo] * (1 - frac) + logs[hi] * frac

    return pct(0.10), pct(0.50), pct(0.90)


def _expm1(x: float) -> float:
    return max(0.0, math.expm1(x))


def estimate_cost(
    conn: sqlite3.Connection, task: TaskContext, category: str, currency: str = "USD"
) -> EstimateRange:
    """The v0 estimator: category-conditioned empirical quantiles, shrunk toward
    the global pool, with cold-start fallback. No point estimate anywhere."""
    cell_values = q.history_by_category(conn, category, currency=currency)
    global_values = q.global_history(conn, currency=currency)

    n = len(cell_values)
    if n < MIN_CELL_N:
        return EstimateRange(
            currency=currency,
            unit="USD" if currency == "USD" else "quota_pct",
            p10=0.0,
            p50=0.0,
            p90=0.0,
            n_samples=n,
            method="cold_start_prior",
            confidence="low",
            category=category,
            caveats=("cold_start", "insufficient_local_history"),
        )

    q10, q50, q90 = _log_quantiles(cell_values)
    # Empirical-Bayes shrinkage toward the global log-quantiles (the backtested
    # M1). With no global pool yet, there is nothing to shrink toward, so the
    # category's own quantiles stand. This is a convex blend in log space — it
    # never collapses the estimate toward zero the way the old `w * q` did.
    if global_values:
        g10, g50, g90 = _log_quantiles(global_values)
    else:
        g10, g50, g90 = q10, q50, q90
    w = n / (n + SHRINK_K)
    p10 = _expm1(w * q10 + (1 - w) * g10)
    p50 = _expm1(w * q50 + (1 - w) * g50)
    p90 = _expm1(w * q90 + (1 - w) * g90)

    if n >= GLOBAL_CATEGORY_FALLBACK_N:
        confidence = "high"
    elif n >= 10:
        confidence = "medium"
    else:
        confidence = "low"

    caveats = () if confidence != "low" else ("small_sample",)

    return EstimateRange(
        currency=currency,
        unit="USD" if currency == "USD" else "quota_pct",
        p10=round(p10, 4),
        p50=round(p50, 4),
        p90=round(p90, 4),
        n_samples=n,
        method="empirical_quantiles",
        confidence=confidence,
        category=category,
        caveats=caveats,
    )


def record_estimate(
    conn: sqlite3.Connection,
    estimate: EstimateRange,
    session_id: int | None,
    workspace_id: int | None,
    run_id: str | None,
    shadow: bool = True,
) -> str:
    """Persist an estimate for later reconciliation. Returns the estimate_uid."""
    estimate_uid = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()
    conn.execute(
        """
        INSERT INTO estimates (
            estimate_uid, session_id, workspace_id, run_id, created_at, currency,
            p10, p50, p90, method, n_samples, category, shadow
        ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)
        """,
        (
            estimate_uid,
            session_id,
            workspace_id,
            run_id,
            now,
            estimate.currency,
            estimate.p10,
            estimate.p50,
            estimate.p90,
            estimate.method,
            estimate.n_samples,
            estimate.category,
            int(shadow),
        ),
    )
    conn.commit()
    return estimate_uid
