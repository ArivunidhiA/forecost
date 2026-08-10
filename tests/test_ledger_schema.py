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


def test_schema_v4_creates_append_only_receipt_kernel(tmp_path):
    conn = sqlite3.connect(tmp_path / "fresh.db")
    apply_schema(conn)

    assert conn.execute("PRAGMA user_version").fetchone()[0] == SCHEMA_VERSION
    tables = {
        row[0]
        for row in conn.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table' AND name LIKE '%_observations' "
            "OR name IN ('causal_runs', 'causal_spans', 'meter_facts', 'charges', "
            "'receipt_snapshots')"
        )
    }
    assert {
        "journal_observations",
        "causal_runs",
        "causal_spans",
        "meter_facts",
        "charges",
        "receipt_snapshots",
    } <= tables
    conn.close()


def test_v6_database_adds_integrity_and_resource_columns_before_indexes(tmp_path):
    conn = sqlite3.connect(tmp_path / "v6.db")
    conn.executescript(
        """
        CREATE TABLE journal_observations (
            observation_id TEXT PRIMARY KEY, schema_version INTEGER NOT NULL,
            producer TEXT NOT NULL, source_sequence INTEGER NOT NULL,
            idempotency_key TEXT NOT NULL, event_kind TEXT NOT NULL,
            occurred_at TEXT NOT NULL, observed_at TEXT NOT NULL,
            causal_json TEXT NOT NULL, payload_json TEXT NOT NULL,
            supersedes_observation_id TEXT,
            UNIQUE(producer, idempotency_key)
        );
        CREATE TABLE resource_scopes (
            scope_id TEXT PRIMARY KEY, parent_scope_id TEXT, dimension TEXT NOT NULL,
            capacity_micros INTEGER NOT NULL, settled_micros INTEGER NOT NULL DEFAULT 0,
            reserved_micros INTEGER NOT NULL DEFAULT 0,
            returned_micros INTEGER NOT NULL DEFAULT 0,
            adjustment_micros INTEGER NOT NULL DEFAULT 0, mode TEXT NOT NULL DEFAULT 'shadow',
            created_at TEXT NOT NULL, metadata_json TEXT NOT NULL DEFAULT '{}'
        );
        CREATE TABLE causal_runs (
            run_id TEXT PRIMARY KEY, conversation_id TEXT NOT NULL, trace_id TEXT NOT NULL,
            lifecycle TEXT NOT NULL, created_at TEXT NOT NULL, observed_at TEXT NOT NULL,
            stop_reason TEXT, source_coverage_json TEXT NOT NULL DEFAULT '{}'
        );
        PRAGMA user_version = 6;
        """
    )

    apply_schema(conn)

    assert conn.execute("PRAGMA user_version").fetchone()[0] == SCHEMA_VERSION
    journal_columns = {row[1] for row in conn.execute("PRAGMA table_info(journal_observations)")}
    resource_columns = {row[1] for row in conn.execute("PRAGMA table_info(resource_scopes)")}
    run_columns = {row[1] for row in conn.execute("PRAGMA table_info(causal_runs)")}
    assert {"journal_sequence", "previous_digest", "entry_digest"} <= journal_columns
    assert {"finalization_reserve_micros", "next_fencing_token", "closed_at"} <= resource_columns
    assert "source_order" in run_columns
    conn.close()
