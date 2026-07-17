"""Read-only query API over the ledger. The only read surface for estimate/ and policy/.

Valuation semantics (the fix for the double-count bug)
------------------------------------------------------
A single event can carry several postings in the same currency — forecost's own
``pricing_table`` computation *and*, for gateway sources, the ``source_reported``
cost the gateway billed. Those are alternative *valuations* of one event, not
additive spend. Summing them (the historical bug) inflated every total by up to
2x for gateway users. So every operational spend read here selects exactly ONE
posting per ``(event_id, currency)`` — the *canonical* basis — and never adds two
valuations of the same event.

Canonical precedence (``CANONICAL_BASIS_ORDER``): prefer ``source_reported`` (what
the source actually billed — closest to "what it cost"), fall back to
``pricing_table`` (forecost's independent computation, present for every event).
Callers may pin a specific basis instead (``basis="pricing_table"`` /
``"source_reported"``) to view one valuation in isolation; ``reconcile`` compares
the two. See BASEMENT.md L1/L8 and the deep-audit finding P0-1.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass

# Highest precedence first. A posting whose basis is not listed sorts last.
CANONICAL_BASIS_ORDER = ("source_reported", "pricing_table")

# Selects exactly one posting per (event_id, currency): the highest-precedence
# basis available. Static SQL (no interpolation) — bind :currency once.
_CANONICAL_CTE = """
    SELECT event_id, currency, amount FROM (
        SELECT p.event_id, p.currency, p.amount,
               ROW_NUMBER() OVER (
                   PARTITION BY p.event_id, p.currency
                   ORDER BY CASE p.basis
                       WHEN 'source_reported' THEN 0
                       WHEN 'pricing_table' THEN 1
                       ELSE 2 END, p.id
               ) AS _rn
        FROM postings p
        WHERE p.currency = ?
    ) WHERE _rn = 1
"""

_BASIS_CTE = "SELECT event_id, currency, amount FROM postings WHERE currency = ? AND basis = ?"


def _posting_source(currency: str, basis: str) -> tuple[str, tuple]:
    """Return (SQL selecting one amount per (event,currency), bind params).

    ``basis="canonical"`` dedups by precedence; a concrete basis name filters to
    that single valuation. Raises ValueError on an unknown basis.
    """
    if basis == "canonical":
        return _CANONICAL_CTE, (currency,)
    if basis in ("pricing_table", "source_reported"):
        return _BASIS_CTE, (currency, basis)
    raise ValueError(f"unknown posting basis: {basis!r}")


def _with_src(src_sql: str, body: str) -> str:
    """Wrap a trusted canonical/basis CTE around a query body.

    ``src_sql`` is always one of the two module-constant CTEs above and ``body``
    is a module-constant query fragment — never caller input — so the composed
    SQL carries no injection surface; all values bind as parameters.
    """
    return f"WITH src AS ({src_sql}) {body}"


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
    basis: str = "canonical",
) -> ScopeSpend:
    """Canonical spend in one currency since a timestamp, optionally scoped to a workspace."""
    src_sql, src_params = _posting_source(currency, basis)
    body = (
        "SELECT COALESCE(SUM(src.amount), 0) AS total, COUNT(*) AS n "
        "FROM src JOIN usage_events e ON e.id = src.event_id WHERE e.ts >= ?"
    )
    params: list = [*src_params, since_iso]
    if workspace_id is not None:
        body += " AND e.workspace_id = ?"
        params.append(workspace_id)
    row = conn.execute(_with_src(src_sql, body), params).fetchone()
    return ScopeSpend(currency=currency, total=row["total"], n_events=row["n"])


def session_spend(
    conn: sqlite3.Connection, session_id: int, currency: str = "USD", basis: str = "canonical"
) -> float:
    src_sql, src_params = _posting_source(currency, basis)
    body = (
        "SELECT COALESCE(SUM(src.amount), 0) AS total "
        "FROM src JOIN usage_events e ON e.id = src.event_id WHERE e.session_id = ?"
    )
    row = conn.execute(_with_src(src_sql, body), [*src_params, session_id]).fetchone()
    return row["total"]


def spend_by_model(
    conn: sqlite3.Connection, currency: str = "USD", basis: str = "canonical", limit: int = 10
) -> list[sqlite3.Row]:
    """Top models by canonical spend (event count + summed canonical amount)."""
    src_sql, src_params = _posting_source(currency, basis)
    body = (
        "SELECT e.model AS model, COUNT(*) AS n, COALESCE(SUM(src.amount), 0) AS total "
        "FROM src JOIN usage_events e ON e.id = src.event_id "
        "GROUP BY e.model ORDER BY total DESC LIMIT ?"
    )
    return conn.execute(_with_src(src_sql, body), [*src_params, limit]).fetchall()


def spend_by_workspace(
    conn: sqlite3.Connection, currency: str = "USD", basis: str = "canonical"
) -> list[sqlite3.Row]:
    """Canonical spend grouped by workspace."""
    src_sql, src_params = _posting_source(currency, basis)
    body = (
        "SELECT w.name AS name, w.root_path AS root_path, "
        "COUNT(*) AS n, COALESCE(SUM(src.amount), 0) AS total "
        "FROM src JOIN usage_events e ON e.id = src.event_id "
        "JOIN workspaces w ON w.id = e.workspace_id GROUP BY w.id ORDER BY total DESC"
    )
    return conn.execute(_with_src(src_sql, body), list(src_params)).fetchall()


def history_by_category(
    conn: sqlite3.Connection, category: str, currency: str = "USD", limit: int = 500
) -> list[float]:
    """Historical per-run actual costs for a task category, for the estimator's
    empirical quantiles.

    Reads the ``reconciliations`` table — the labeled (category -> actual cost)
    training set that the stop-hook produces by associating each estimate with
    its own run's actuals (session + time window; see calibration.py). This
    deliberately does NOT re-derive the estimate->actual link via ``run_id``,
    which never matches across the hook/transcript boundary (deep-audit P0-3);
    every reconciled run — including cold-start turns — contributes one sample.
    Empty list for categories with no reconciled history yet.
    """
    rows = conn.execute(
        """
        SELECT r.actual_amount AS total
        FROM reconciliations r JOIN estimates est ON est.id = r.estimate_id
        WHERE est.category = ? AND r.currency = ?
        ORDER BY r.reconciled_at DESC LIMIT ?
        """,
        (category, currency, limit),
    ).fetchall()
    return [r["total"] for r in rows if r["total"] is not None]


def global_history(
    conn: sqlite3.Connection, currency: str = "USD", limit: int = 2000
) -> list[float]:
    """All reconciled per-run actual costs across every category — the pool the
    estimator shrinks a small category toward (empirical-Bayes style)."""
    rows = conn.execute(
        """
        SELECT actual_amount AS total FROM reconciliations
        WHERE currency = ? ORDER BY reconciled_at DESC LIMIT ?
        """,
        (currency, limit),
    ).fetchall()
    return [r["total"] for r in rows if r["total"] is not None]


def session_window_spend(
    conn: sqlite3.Connection,
    session_id: int,
    currency: str,
    since_iso: str,
    until_iso: str | None = None,
    basis: str = "canonical",
) -> tuple[float, int]:
    """Canonical (total, n_events) for one session within [since, until).

    The estimate->actual association key: an estimate recorded at time ``since``
    is scored against its session's events up to the next estimate (``until``),
    or open-ended when it is the latest estimate. Returns (0.0, 0) when the
    window is empty (actuals not ingested yet)."""
    src_sql, src_params = _posting_source(currency, basis)
    body = (
        "SELECT COALESCE(SUM(src.amount), 0) AS total, COUNT(*) AS n "
        "FROM src JOIN usage_events e ON e.id = src.event_id "
        "WHERE e.session_id = ? AND e.ts >= ?"
    )
    params: list = [*src_params, session_id, since_iso]
    if until_iso is not None:
        body += " AND e.ts < ?"
        params.append(until_iso)
    row = conn.execute(_with_src(src_sql, body), params).fetchone()
    return row["total"], row["n"]


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
    # COUNT(within_band) counts only scored (non-cold-start) reconciliations;
    # cold-start rows carry a NULL band and are excluded from the published record.
    row = conn.execute(
        """
        SELECT COUNT(within_band) AS n,
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
