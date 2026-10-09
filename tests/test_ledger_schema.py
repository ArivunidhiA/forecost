"""Focused tests for durable ledger schema migrations."""

import json
import sqlite3
from datetime import datetime, timezone

import pytest

from forecost.core.paths import UnsafeDataPathError
from forecost.ledger.contracts import CausalIdentity
from forecost.ledger.db import get_readonly_ledger_db
from forecost.ledger.evidence import append_observation, observation
from forecost.ledger.schema import SCHEMA_VERSION, apply_schema


def test_readonly_open_never_creates_a_missing_ledger(tmp_path):
    path = tmp_path / "missing.db"

    with pytest.raises(UnsafeDataPathError, match="does not exist"):
        get_readonly_ledger_db(path)

    assert not path.exists()
    assert not path.with_name(path.name + "-wal").exists()
    assert not path.with_name(path.name + "-shm").exists()


def test_readonly_open_refuses_to_migrate_an_old_schema(tmp_path):
    path = tmp_path / "old.db"
    conn = sqlite3.connect(path)
    conn.execute(f"PRAGMA user_version = {SCHEMA_VERSION - 1}")
    conn.close()
    path.chmod(0o600)

    with pytest.raises(sqlite3.DatabaseError, match="explicit ledger migration"):
        get_readonly_ledger_db(path)

    check = sqlite3.connect(path)
    try:
        assert check.execute("PRAGMA user_version").fetchone()[0] == SCHEMA_VERSION - 1
    finally:
        check.close()


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


def test_v9_migration_rebuilds_reused_span_ids_with_trace_scoped_keys(tmp_path):
    path = tmp_path / "v9-collision.db"
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    apply_schema(conn)
    when = datetime(2026, 1, 1, tzinfo=timezone.utc)
    for sequence, trace_id, run_id in (
        (1, "1" * 32, "run-one"),
        (2, "2" * 32, "run-two"),
    ):
        append_observation(
            conn,
            observation(
                producer="legacy",
                event_kind="span",
                causal=CausalIdentity(
                    f"conversation-{sequence}",
                    trace_id,
                    run_id,
                    "a" * 16,
                    source_sequence=sequence,
                    idempotency_key=f"legacy-{sequence}",
                ),
                payload={"operation_kind": "agent", "lifecycle": "completed"},
                occurred_at=when,
                observed_at=when,
            ),
        )
    # Model the old projection loss while retaining the authoritative journal.
    conn.execute("DROP TABLE causal_spans")
    conn.execute(
        "CREATE TABLE causal_spans("
        "span_id TEXT PRIMARY KEY, run_id TEXT NOT NULL, conversation_id TEXT NOT NULL, "
        "trace_id TEXT NOT NULL, parent_span_id TEXT, operation_kind TEXT NOT NULL, "
        "lifecycle TEXT NOT NULL, agent_id TEXT, workflow_node_id TEXT, branch_id TEXT, "
        "attempt_of_span_id TEXT, checkpoint_id TEXT, occurred_at TEXT NOT NULL, "
        "observed_at TEXT NOT NULL, source_order TEXT NOT NULL)"
    )
    conn.execute("PRAGMA user_version = 9")
    conn.commit()

    apply_schema(conn)

    assert conn.execute("PRAGMA user_version").fetchone()[0] == SCHEMA_VERSION
    rows = conn.execute(
        "SELECT trace_id, span_id, span_key FROM causal_spans ORDER BY trace_id"
    ).fetchall()
    assert len(rows) == 2
    assert rows[0][1] == rows[1][1] == "a" * 16
    assert rows[0][2] != rows[1][2]
    conn.close()


def test_v9_migration_fails_closed_on_ambiguous_run_identity(tmp_path):
    conn = sqlite3.connect(tmp_path / "v9-ambiguous.db")
    conn.executescript(
        """
        CREATE TABLE journal_observations (
            observation_id TEXT PRIMARY KEY, schema_version INTEGER NOT NULL,
            producer TEXT NOT NULL, source_sequence INTEGER NOT NULL,
            idempotency_key TEXT NOT NULL, event_kind TEXT NOT NULL,
            occurred_at TEXT NOT NULL, observed_at TEXT NOT NULL,
            causal_json TEXT NOT NULL, payload_json TEXT NOT NULL,
            supersedes_observation_id TEXT, journal_sequence INTEGER,
            previous_digest TEXT, entry_digest TEXT,
            UNIQUE(producer, idempotency_key)
        );
        PRAGMA user_version = 9;
        """
    )
    for sequence, conversation, trace in (
        (1, "conversation-one", "1" * 32),
        (2, "conversation-two", "2" * 32),
    ):
        causal = {
            "conversation_id": conversation,
            "trace_id": trace,
            "run_id": "shared-run",
            "span_id": f"{sequence:016x}",
        }
        conn.execute(
            "INSERT INTO journal_observations("
            "observation_id,schema_version,producer,source_sequence,idempotency_key,event_kind,"
            "occurred_at,observed_at,causal_json,payload_json,journal_sequence) "
            "VALUES (?,?,?,?,?,'span',?,?,?,?,?)",
            (
                f"observation-{sequence}",
                1,
                "legacy",
                sequence,
                f"event-{sequence}",
                "2026-01-01T00:00:00+00:00",
                "2026-01-01T00:00:00+00:00",
                json.dumps(causal),
                '{"operation_kind":"agent","lifecycle":"completed"}',
                sequence,
            ),
        )
    conn.commit()

    with pytest.raises(RuntimeError, match="legacy identity ambiguity"):
        apply_schema(conn)

    assert conn.execute("PRAGMA user_version").fetchone()[0] == 9
    assert conn.execute("SELECT COUNT(*) FROM journal_observations").fetchone()[0] == 2
    conn.close()
