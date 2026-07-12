"""Burn trajectory: trailing spend rate → projected time until a budget limit.

This is the honest, demoted descendant of the old calendar forecaster: it makes no
claim about what future tasks will cost — it states the measured trailing burn rate
and the arithmetic consequence "at this rate, you hit limit X in Y hours." A measured
fact plus arithmetic, per law L1; never a prediction about workload.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone


@dataclass(frozen=True)
class BurnReport:
    currency: str
    window_hours: float
    spent_in_window: float
    hourly_rate: float
    budget_name: str | None = None
    budget_limit: float | None = None
    spent_toward_budget: float | None = None
    hours_to_limit: float | None = None  # None = no active burn or no budget


def _spend_since(conn: sqlite3.Connection, currency: str, since_iso: str) -> float:
    row = conn.execute(
        """
        SELECT COALESCE(SUM(p.amount), 0) AS total
        FROM postings p JOIN usage_events e ON e.id = p.event_id
        WHERE p.currency = ? AND e.ts >= ?
        """,
        (currency, since_iso),
    ).fetchone()
    return row["total"]


def burn_report(
    conn: sqlite3.Connection, currency: str = "USD", window_hours: float = 24.0
) -> list[BurnReport]:
    """Trailing burn rate, projected against every active budget in this currency.

    Returns one BurnReport per active budget, or a single budget-less report when
    no budgets are configured (the rate is still worth glancing at).
    """
    now = datetime.now(timezone.utc)
    since = (now - timedelta(hours=window_hours)).isoformat()
    spent = _spend_since(conn, currency, since)
    hourly = spent / window_hours if window_hours > 0 else 0.0

    budgets = conn.execute(
        "SELECT name, scope, hard_limit FROM budgets WHERE active = 1 AND currency = ? "
        "AND hard_limit IS NOT NULL",
        (currency,),
    ).fetchall()

    if not budgets:
        return [
            BurnReport(
                currency=currency,
                window_hours=window_hours,
                spent_in_window=spent,
                hourly_rate=hourly,
            )
        ]

    scope_windows = {"day": 24.0, "week": 168.0, "month": 720.0}
    reports = []
    for b in budgets:
        scope_h = scope_windows.get(b["scope"])
        if scope_h is not None:
            scope_since = (now - timedelta(hours=scope_h)).isoformat()
            spent_toward = _spend_since(conn, currency, scope_since)
        else:  # run/session scopes have no meaningful trailing window here
            spent_toward = spent
        remaining = max(0.0, b["hard_limit"] - spent_toward)
        hours_to_limit = remaining / hourly if hourly > 0 else None
        reports.append(
            BurnReport(
                currency=currency,
                window_hours=window_hours,
                spent_in_window=spent,
                hourly_rate=hourly,
                budget_name=b["name"],
                budget_limit=b["hard_limit"],
                spent_toward_budget=spent_toward,
                hours_to_limit=hours_to_limit,
            )
        )
    return reports
