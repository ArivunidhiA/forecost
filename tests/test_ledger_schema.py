"""Focused tests for durable ledger schema migrations."""

import sqlite3

import pytest

from forecost.ledger.schema import SCHEMA_VERSION, apply_schema


def test_schema_v3_deduplicates_reconciliations_before_unique_index(tmp_path):
    path = tmp_path / "ledger-v2.db"
    conn = sqlite3.connect(path)
    conn.executescript(
        """
        CREATE TABLE reconciliations (
            id             INTEGER PRIMARY KEY AUTOINCREMENT,
            estimate_id    INTEGER NOT NULL,
            actual_amount  REAL NOT NULL,
            currency       TEXT NOT NULL,
            within_band    INTEGER,
            abs_pct_error  REAL,
            reconciled_at  TEXT NOT NULL
        );
        INSERT INTO reconciliations
            (estimate_id, actual_amount, currency, within_band, abs_pct_error, reconciled_at)
        VALUES
            (7, 1.25, 'USD', 1, 0.1, '2026-08-01T00:00:00+00:00'),
            (7, 9.99, 'USD', 0, 9.0, '2026-08-02T00:00:00+00:00');
        PRAGMA user_version = 2;
        """
    )

    apply_schema(conn)

    assert conn.execute("PRAGMA user_version").fetchone()[0] == SCHEMA_VERSION
    rows = conn.execute(
        "SELECT id, estimate_id, actual_amount FROM reconciliations ORDER BY id"
    ).fetchall()
    assert rows == [(1, 7, 1.25)]
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(
            """
            INSERT INTO reconciliations
                (estimate_id, actual_amount, currency, reconciled_at)
            VALUES (7, 2.0, 'USD', '2026-08-03T00:00:00+00:00')
            """
        )
    conn.close()
