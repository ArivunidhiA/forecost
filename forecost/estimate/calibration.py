"""Close the estimate → actual loop: reconcile shadow estimates against the ledger.

Every preflight writes a (shadow) estimate row keyed by run_id; every ingest writes
the actual usage events keyed by the same run_id. This module joins the two, records
a reconciliations row per estimate (within-band or not, absolute percent error), and
exposes the rolling calibration record — the number the whole trust story rests on
(BASEMENT.md law L8: "publish our own error").

Cold-start estimates (method='cold_start_prior') are skipped: a 0/0/0 band is not a
claim, so scoring it would corrupt the record in either direction.
"""

from __future__ import annotations

import sqlite3
from datetime import datetime, timezone


def reconcile_estimates(conn: sqlite3.Connection) -> int:
    """Match unreconciled, non-cold-start estimates to actuals by run_id.

    Returns the number of new reconciliations written. Idempotent: an estimate
    with an existing reconciliation row is never re-scored.
    """
    candidates = conn.execute(
        """
        SELECT est.id, est.run_id, est.currency, est.p10, est.p50, est.p90
        FROM estimates est
        WHERE est.method != 'cold_start_prior'
          AND est.run_id IS NOT NULL
          AND NOT EXISTS (
              SELECT 1 FROM reconciliations r WHERE r.estimate_id = est.id
          )
        """
    ).fetchall()

    written = 0
    now = datetime.now(timezone.utc).isoformat()
    for est in candidates:
        row = conn.execute(
            """
            SELECT COALESCE(SUM(p.amount), 0) AS actual, COUNT(*) AS n
            FROM usage_events e
            JOIN postings p ON p.event_id = e.id
            WHERE e.run_id = ? AND p.currency = ? AND p.basis = 'pricing_table'
            """,
            (est["run_id"], est["currency"]),
        ).fetchone()
        if row["n"] == 0:
            continue  # actuals not ingested yet; try again on the next reconcile pass
        actual = row["actual"]
        within_band = 1 if est["p10"] <= actual <= est["p90"] else 0
        abs_pct_error = abs(actual - est["p50"]) / max(actual, 0.001)
        conn.execute(
            """
            INSERT INTO reconciliations
                (estimate_id, actual_amount, currency, within_band, abs_pct_error, reconciled_at)
            VALUES (?,?,?,?,?,?)
            """,
            (est["id"], actual, est["currency"], within_band, abs_pct_error, now),
        )
        written += 1
    conn.commit()
    return written


def calibration_by_category(conn: sqlite3.Connection, currency: str = "USD") -> list[dict]:
    """Per-category calibration record: n, band coverage, median-ish APE."""
    rows = conn.execute(
        """
        SELECT est.category,
               COUNT(*) AS n,
               AVG(r.within_band) AS coverage,
               AVG(r.abs_pct_error) AS mape
        FROM reconciliations r
        JOIN estimates est ON est.id = r.estimate_id
        WHERE r.currency = ?
        GROUP BY est.category
        ORDER BY n DESC
        """,
        (currency,),
    ).fetchall()
    return [dict(r) for r in rows]
