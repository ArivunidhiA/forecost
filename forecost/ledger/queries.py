"""Read-only query API over the ledger. The only read surface for estimate/ and policy/."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass


@dataclass(frozen=True)
class ScopeSpend:
    currency: str
    total: float
    n_events: int


def scope_spend(
    conn: sqlite3.Connection,
    currency: str,
    since_iso: str,
    workspace_id: int | None = None,
) -> ScopeSpend:
    """Sum postings in one currency since a timestamp, optionally scoped to a workspace."""
    if workspace_id is not None:
        row = conn.execute(
            """
            SELECT COALESCE(SUM(p.amount), 0) AS total, COUNT(*) AS n
            FROM postings p
            JOIN usage_events e ON e.id = p.event_id
            WHERE p.currency = ? AND e.ts >= ? AND e.workspace_id = ?
            """,
            (currency, since_iso, workspace_id),
        ).fetchone()
    else:
        row = conn.execute(
            """
            SELECT COALESCE(SUM(p.amount), 0) AS total, COUNT(*) AS n
            FROM postings p
            JOIN usage_events e ON e.id = p.event_id
            WHERE p.currency = ? AND e.ts >= ?
            """,
            (currency, since_iso),
        ).fetchone()
    return ScopeSpend(currency=currency, total=row["total"], n_events=row["n"])


def session_spend(conn: sqlite3.Connection, session_id: int, currency: str = "USD") -> float:
    row = conn.execute(
        """
        SELECT COALESCE(SUM(p.amount), 0) AS total
        FROM postings p JOIN usage_events e ON e.id = p.event_id
        WHERE e.session_id = ? AND p.currency = ?
        """,
        (session_id, currency),
    ).fetchone()
    return row["total"]


def history_by_category(
    conn: sqlite3.Connection, category: str, currency: str = "USD", limit: int = 500
) -> list[float]:
    """Historical per-run costs for a task category, for the estimator's empirical
    quantiles. Joins estimates.category (set at preflight time) back to actuals via
    run_id; falls back to an empty list for categories never seen."""
    rows = conn.execute(
        """
        SELECT SUM(p.amount) AS total
        FROM estimates est
        JOIN usage_events e ON e.run_id = est.run_id
        JOIN postings p ON p.event_id = e.id
        WHERE est.category = ? AND p.currency = ?
        GROUP BY est.run_id
        ORDER BY MAX(e.ts) DESC
        LIMIT ?
        """,
        (category, currency, limit),
    ).fetchall()
    return [r["total"] for r in rows if r["total"] is not None]


def active_budgets(
    conn: sqlite3.Connection, workspace_id: int | None, currency: str
) -> list[sqlite3.Row]:
    return conn.execute(
        """
        SELECT * FROM budgets
        WHERE active = 1 AND currency = ?
          AND (workspace_id IS NULL OR workspace_id = ?)
        """,
        (currency, workspace_id),
    ).fetchall()


def recent_flags(conn: sqlite3.Connection, session_id: int, limit: int = 20) -> list[sqlite3.Row]:
    return conn.execute(
        "SELECT * FROM guard_flags WHERE session_id = ? ORDER BY ts DESC LIMIT ?",
        (session_id, limit),
    ).fetchall()


def calibration_summary(conn: sqlite3.Connection, currency: str = "USD") -> dict:
    """G1-G4 style calibration record: coverage of the P10-P90 band on reconciled
    estimates. Returns None-valued fields when no reconciliations exist yet."""
    row = conn.execute(
        """
        SELECT COUNT(*) AS n,
               AVG(within_band) AS coverage,
               AVG(abs_pct_error) AS mape
        FROM reconciliations WHERE currency = ?
        """,
        (currency,),
    ).fetchone()
    return {
        "n": row["n"] or 0,
        "coverage": row["coverage"],
        "mape": row["mape"],
    }
