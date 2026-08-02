"""Close the estimate → actual loop: reconcile shadow estimates against the ledger.

The estimate and the transcript never share a run identity — the UserPromptSubmit
hook has no promptId, and the transcript events key on one (deep-audit P0-3). What
they DO share is the session: a preflight estimate and the events it predicts resolve
to the same ``sessions.id``. So each estimate is associated with its own run by a
session + time window: the events in its session from the estimate's ``created_at`` up
to the next estimate's ``created_at`` (open-ended for the latest estimate). That
canonical windowed spend is the estimate's actual.

Each reconciliation stores the actual amount for EVERY estimate — including cold-start
ones — so the reconciliations table doubles as the estimator's labeled (category ->
actual) training set and can bootstrap from nothing. Band coverage (within_band) and
percent error are recorded only for real estimates; a cold-start 0/0/0 band is not a
claim, so those columns are left NULL and excluded from the published record
(BASEMENT.md law L8: "publish our own error").
"""

from __future__ import annotations

import sqlite3
from datetime import datetime, timezone

from forecost.ledger import queries as q
from forecost.ledger.db import ledger_write_lock


def reconcile_estimates(conn: sqlite3.Connection) -> int:
    """Associate unreconciled estimates with their run's actuals by session+window.

    Returns the number of new reconciliations written. Idempotent: an estimate
    with an existing reconciliation row is never re-scored.
    """
    # The process-wide connection is shared with hook/state writers. Hold the
    # same lock from the initial candidate snapshot through commit so another
    # local thread cannot commit or roll back this reconciliation transaction.
    # The UNIQUE constraint remains the cross-process final arbiter.
    with ledger_write_lock:
        return _reconcile_estimates_locked(conn)


def _reconcile_estimates_locked(conn: sqlite3.Connection) -> int:
    candidates = conn.execute(
        """
        SELECT est.id, est.session_id, est.created_at, est.currency,
               est.p10, est.p50, est.p90, est.method
        FROM estimates est
        WHERE est.session_id IS NOT NULL
          AND NOT EXISTS (
              SELECT 1 FROM reconciliations r WHERE r.estimate_id = est.id
          )
        ORDER BY est.session_id, est.created_at
        """
    ).fetchall()

    written = 0
    now = datetime.now(timezone.utc).isoformat()
    for est in candidates:
        # Window end = the next estimate in this session, else open-ended.
        nxt = conn.execute(
            "SELECT MIN(created_at) AS next_at FROM estimates "
            "WHERE session_id = ? AND created_at > ?",
            (est["session_id"], est["created_at"]),
        ).fetchone()
        actual, n = q.session_window_spend(
            conn, est["session_id"], est["currency"], est["created_at"], nxt["next_at"]
        )
        if n == 0:
            continue  # actuals not ingested yet; try again on the next reconcile pass

        cold_start = est["method"] == "cold_start_prior"
        if cold_start:
            within_band = None  # a 0/0/0 band is not a claim — record the actual only
            abs_pct_error = None
        else:
            within_band = 1 if est["p10"] <= actual <= est["p90"] else 0
            abs_pct_error = abs(actual - est["p50"]) / max(actual, 0.001)
        cursor = conn.execute(
            """
            INSERT INTO reconciliations
                (estimate_id, actual_amount, currency, within_band, abs_pct_error, reconciled_at)
            VALUES (?,?,?,?,?,?)
            ON CONFLICT(estimate_id) DO NOTHING
            """,
            (est["id"], actual, est["currency"], within_band, abs_pct_error, now),
        )
        written += cursor.rowcount
    conn.commit()
    return written


def calibration_by_category(conn: sqlite3.Connection, currency: str = "USD") -> list[dict]:
    """Per-category calibration record: n, band coverage, median-ish APE."""
    rows = conn.execute(
        """
        SELECT est.category,
               COUNT(r.within_band) AS n,
               AVG(r.within_band) AS coverage,
               AVG(r.abs_pct_error) AS mape
        FROM reconciliations r
        JOIN estimates est ON est.id = r.estimate_id
        WHERE r.currency = ?
        GROUP BY est.category
        HAVING COUNT(r.within_band) > 0
        ORDER BY n DESC
        """,
        (currency,),
    ).fetchall()
    return [dict(r) for r in rows]
