"""Ledger v2 schema: a multi-currency, event-sourced flight recorder.

Design (round3-architecture.md §3.2-3.3): usage_events stores the physical
facts of a call (tokens, model, source); postings stores valuations of that
event in one or more currencies (USD, provider credits, subscription quota).
One event can carry multiple simultaneous postings — a USD estimate from a
pricing snapshot, a quota debit against a Max-plan window, a source-reported
authoritative cost — without schema churn every time a new currency appears.

Lives at ~/.forecost/ledger.db — a NEW file. The legacy ~/.forecost/costs.db
(forecost/db.py) is untouched; `forecost migrate` ports it once (ledger/migrate_v1.py).

This amends CLAUDE.md's "no database migrations" rule for the ledger package
specifically: the metadata-JSON-column pattern absorbs *attribute* growth, but
multi-currency and reconciliation are *relational* growth. Versioning here is a
linear PRAGMA user_version ladder, not a migration framework.
"""

from __future__ import annotations

import sqlite3

SCHEMA_VERSION = 6

_DDL = """
CREATE TABLE IF NOT EXISTS workspaces (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    name          TEXT NOT NULL,
    root_path     TEXT NOT NULL UNIQUE,
    created_at    TEXT NOT NULL,
    metadata      TEXT
);

CREATE TABLE IF NOT EXISTS sessions (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    session_uid   TEXT NOT NULL UNIQUE,
    workspace_id  INTEGER REFERENCES workspaces(id),
    agent         TEXT NOT NULL,
    started_at    TEXT NOT NULL,
    ended_at      TEXT,
    metadata      TEXT
);
CREATE INDEX IF NOT EXISTS idx_sessions_ws ON sessions(workspace_id, started_at);

CREATE TABLE IF NOT EXISTS usage_events (
    id                 INTEGER PRIMARY KEY AUTOINCREMENT,
    event_uid          TEXT NOT NULL UNIQUE,
    ts                 TEXT NOT NULL,
    source             TEXT NOT NULL,
    session_id         INTEGER REFERENCES sessions(id),
    workspace_id       INTEGER REFERENCES workspaces(id),
    run_id             TEXT,
    provider           TEXT,
    model              TEXT NOT NULL,
    tokens_in          INTEGER NOT NULL DEFAULT 0,
    tokens_out         INTEGER NOT NULL DEFAULT 0,
    tokens_cache_read  INTEGER NOT NULL DEFAULT 0,
    tokens_cache_write INTEGER NOT NULL DEFAULT 0,
    metadata           TEXT
);
CREATE INDEX IF NOT EXISTS idx_events_ts       ON usage_events(ts);
CREATE INDEX IF NOT EXISTS idx_events_session  ON usage_events(session_id);
CREATE INDEX IF NOT EXISTS idx_events_ws_ts    ON usage_events(workspace_id, ts);
CREATE INDEX IF NOT EXISTS idx_events_run      ON usage_events(run_id);

CREATE TABLE IF NOT EXISTS postings (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    event_id        INTEGER NOT NULL REFERENCES usage_events(id),
    currency        TEXT NOT NULL,
    amount          REAL NOT NULL,
    basis           TEXT NOT NULL,
    pricing_version TEXT,
    created_at      TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_postings_event    ON postings(event_id);
CREATE INDEX IF NOT EXISTS idx_postings_currency ON postings(currency, created_at);

CREATE TABLE IF NOT EXISTS plans (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    plan_uid     TEXT NOT NULL UNIQUE,
    display_name TEXT NOT NULL,
    windows      TEXT NOT NULL,
    metadata     TEXT
);

CREATE TABLE IF NOT EXISTS budgets (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    name          TEXT NOT NULL,
    scope         TEXT NOT NULL,
    workspace_id  INTEGER REFERENCES workspaces(id),
    currency      TEXT NOT NULL,
    soft_limit    REAL,
    hard_limit    REAL,
    action        TEXT NOT NULL DEFAULT 'warn',
    origin        TEXT NOT NULL DEFAULT 'local',
    active        INTEGER NOT NULL DEFAULT 1,
    created_at    TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS estimates (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    estimate_uid    TEXT NOT NULL UNIQUE,
    session_id      INTEGER REFERENCES sessions(id),
    workspace_id    INTEGER REFERENCES workspaces(id),
    run_id          TEXT,
    created_at      TEXT NOT NULL,
    currency        TEXT NOT NULL,
    p10             REAL,
    p50             REAL NOT NULL,
    p90             REAL,
    method          TEXT NOT NULL,
    n_samples       INTEGER NOT NULL DEFAULT 0,
    category        TEXT,
    shadow          INTEGER NOT NULL DEFAULT 1,
    features        TEXT,
    pricing_version TEXT
);
CREATE INDEX IF NOT EXISTS idx_estimates_run ON estimates(run_id);

CREATE TABLE IF NOT EXISTS reconciliations (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    estimate_id    INTEGER NOT NULL REFERENCES estimates(id),
    actual_amount  REAL NOT NULL,
    currency       TEXT NOT NULL,
    within_band    INTEGER,
    abs_pct_error  REAL,
    reconciled_at  TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS policy_decisions (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    ts          TEXT NOT NULL,
    session_id  INTEGER REFERENCES sessions(id),
    rule_id     TEXT NOT NULL,
    hook_event  TEXT NOT NULL,
    action      TEXT NOT NULL,
    reason      TEXT,
    context     TEXT
);
CREATE INDEX IF NOT EXISTS idx_decisions_ts ON policy_decisions(ts);

CREATE TABLE IF NOT EXISTS ingest_state (
    source      TEXT NOT NULL,
    cursor_key  TEXT NOT NULL,
    cursor_val  TEXT NOT NULL,
    updated_at  TEXT NOT NULL,
    PRIMARY KEY (source, cursor_key)
);

CREATE TABLE IF NOT EXISTS outcomes (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id        TEXT NOT NULL,
    session_id    INTEGER REFERENCES sessions(id),
    outcome_type  TEXT NOT NULL DEFAULT 'task',
    outcome_status TEXT NOT NULL,
    signal_source TEXT NOT NULL,
    files_touched INTEGER,
    lines_changed INTEGER,
    verified_at   TEXT NOT NULL,
    metadata      TEXT
);
CREATE INDEX IF NOT EXISTS idx_outcomes_run ON outcomes(run_id);

CREATE TABLE IF NOT EXISTS guard_flags (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id    INTEGER REFERENCES sessions(id),
    run_id        TEXT,
    ts            TEXT NOT NULL,
    rule_id       TEXT NOT NULL,
    evidence      TEXT NOT NULL,
    shadow        INTEGER NOT NULL DEFAULT 1,
    user_action   TEXT
);

-- v4: immutable, content-free causal/economic evidence.  These tables are
-- intentionally additive: v3 usage_events/postings remain readable while
-- adapters graduate to the receipt kernel.
CREATE TABLE IF NOT EXISTS journal_observations (
    observation_id TEXT PRIMARY KEY,
    schema_version INTEGER NOT NULL,
    producer       TEXT NOT NULL,
    source_sequence INTEGER NOT NULL,
    idempotency_key TEXT NOT NULL,
    event_kind     TEXT NOT NULL,
    occurred_at    TEXT NOT NULL,
    observed_at    TEXT NOT NULL,
    causal_json    TEXT NOT NULL,
    payload_json   TEXT NOT NULL,
    supersedes_observation_id TEXT,
    UNIQUE(producer, idempotency_key)
);
CREATE INDEX IF NOT EXISTS idx_journal_projection_order
    ON journal_observations(producer, source_sequence, idempotency_key);
CREATE INDEX IF NOT EXISTS idx_journal_occurred_at ON journal_observations(occurred_at);

CREATE TABLE IF NOT EXISTS causal_runs (
    run_id          TEXT PRIMARY KEY,
    conversation_id TEXT NOT NULL,
    trace_id        TEXT NOT NULL,
    lifecycle       TEXT NOT NULL,
    created_at      TEXT NOT NULL,
    observed_at     TEXT NOT NULL,
    stop_reason     TEXT,
    source_coverage_json TEXT NOT NULL DEFAULT '{}'
);

CREATE TABLE IF NOT EXISTS causal_spans (
    span_id          TEXT PRIMARY KEY,
    run_id           TEXT NOT NULL,
    conversation_id  TEXT NOT NULL,
    trace_id         TEXT NOT NULL,
    parent_span_id   TEXT,
    operation_kind   TEXT NOT NULL,
    lifecycle        TEXT NOT NULL,
    agent_id         TEXT,
    workflow_node_id TEXT,
    branch_id        TEXT,
    attempt_of_span_id TEXT,
    checkpoint_id    TEXT,
    occurred_at      TEXT NOT NULL,
    observed_at      TEXT NOT NULL,
    source_order     TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_causal_spans_run ON causal_spans(run_id, source_order);

CREATE TABLE IF NOT EXISTS span_links (
    span_id          TEXT NOT NULL,
    linked_span_id   TEXT NOT NULL,
    link_type        TEXT NOT NULL,
    observation_id   TEXT NOT NULL,
    PRIMARY KEY(span_id, linked_span_id, link_type, observation_id)
);

CREATE TABLE IF NOT EXISTS meter_facts (
    fact_id          TEXT PRIMARY KEY,
    span_id          TEXT NOT NULL,
    meter_name       TEXT NOT NULL,
    unit             TEXT NOT NULL,
    quantity_micros  INTEGER NOT NULL,
    aggregation      TEXT NOT NULL,
    dimensions_json  TEXT NOT NULL,
    source           TEXT NOT NULL,
    finality         TEXT NOT NULL,
    occurred_at      TEXT NOT NULL,
    observed_at      TEXT NOT NULL,
    observation_id   TEXT NOT NULL UNIQUE
);
CREATE INDEX IF NOT EXISTS idx_meter_facts_span ON meter_facts(span_id, meter_name);

CREATE TABLE IF NOT EXISTS charges (
    charge_id        TEXT PRIMARY KEY,
    fact_id          TEXT,
    span_id          TEXT NOT NULL,
    amount_micros    INTEGER NOT NULL,
    currency         TEXT NOT NULL,
    authority        TEXT NOT NULL,
    line_item        TEXT NOT NULL,
    tariff_json      TEXT NOT NULL,
    account_scope    TEXT,
    billing_period   TEXT,
    finality         TEXT NOT NULL,
    occurred_at      TEXT NOT NULL,
    observed_at      TEXT NOT NULL,
    supersedes_charge_id TEXT,
    observation_id   TEXT NOT NULL UNIQUE
);
CREATE INDEX IF NOT EXISTS idx_charges_span ON charges(span_id, currency, authority);

CREATE TABLE IF NOT EXISTS outcome_evidence (
    evidence_id      TEXT PRIMARY KEY,
    run_id           TEXT NOT NULL,
    outcome_status   TEXT NOT NULL,
    reason_code      TEXT,
    evidence_type    TEXT NOT NULL,
    source           TEXT NOT NULL,
    confidence       TEXT NOT NULL,
    observed_at      TEXT NOT NULL,
    supersedes_evidence_id TEXT,
    observation_id   TEXT NOT NULL UNIQUE
);
CREATE INDEX IF NOT EXISTS idx_outcome_evidence_run ON outcome_evidence(run_id, observed_at);

CREATE TABLE IF NOT EXISTS receipt_snapshots (
    receipt_id       TEXT PRIMARY KEY,
    run_id           TEXT NOT NULL,
    schema_version   INTEGER NOT NULL,
    generated_at     TEXT NOT NULL,
    evidence_state   TEXT NOT NULL,
    payload_json     TEXT NOT NULL,
    UNIQUE(run_id, schema_version, generated_at)
);
CREATE INDEX IF NOT EXISTS idx_receipts_run ON receipt_snapshots(run_id, generated_at DESC);

-- v5: reproducible, source-aware reconciliation.  Aggregate provider exports
-- are evidence too; they are not force-matched to a local callback.
CREATE TABLE IF NOT EXISTS reconciliation_batches (
    batch_id          TEXT PRIMARY KEY,
    schema_version    INTEGER NOT NULL,
    run_id            TEXT,
    source_set_json   TEXT NOT NULL,
    account_scope     TEXT,
    dimensions_json   TEXT NOT NULL,
    window_start      TEXT NOT NULL,
    window_end        TEXT NOT NULL,
    watermarks_json   TEXT NOT NULL,
    expected_count    INTEGER NOT NULL,
    observed_count    INTEGER NOT NULL,
    unmatched_local_count INTEGER NOT NULL,
    unmatched_provider_count INTEGER NOT NULL,
    local_amount_micros INTEGER NOT NULL,
    provider_amount_micros INTEGER NOT NULL,
    residual_micros   INTEGER NOT NULL,
    tolerance_micros  INTEGER NOT NULL,
    finality          TEXT NOT NULL,
    state             TEXT NOT NULL,
    created_at        TEXT NOT NULL,
    supersedes_batch_id TEXT
);
CREATE INDEX IF NOT EXISTS idx_reconciliation_batches_run
    ON reconciliation_batches(run_id, created_at DESC);

CREATE TABLE IF NOT EXISTS reconciliation_evidence (
    batch_id          TEXT NOT NULL REFERENCES reconciliation_batches(batch_id),
    observation_id    TEXT NOT NULL,
    source_role       TEXT NOT NULL,
    match_state       TEXT NOT NULL,
    PRIMARY KEY(batch_id, observation_id)
);

-- v6: local, reservation-based resource envelopes.  This is intentionally a
-- single-host SQLite boundary, never a provider-side or distributed guarantee.
CREATE TABLE IF NOT EXISTS resource_scopes (
    scope_id          TEXT PRIMARY KEY,
    parent_scope_id   TEXT REFERENCES resource_scopes(scope_id),
    dimension         TEXT NOT NULL,
    capacity_micros   INTEGER NOT NULL,
    settled_micros    INTEGER NOT NULL DEFAULT 0,
    reserved_micros   INTEGER NOT NULL DEFAULT 0,
    returned_micros   INTEGER NOT NULL DEFAULT 0,
    adjustment_micros INTEGER NOT NULL DEFAULT 0,
    mode              TEXT NOT NULL DEFAULT 'shadow',
    created_at        TEXT NOT NULL,
    metadata_json     TEXT NOT NULL DEFAULT '{}'
);
CREATE INDEX IF NOT EXISTS idx_resource_scopes_parent ON resource_scopes(parent_scope_id);

CREATE TABLE IF NOT EXISTS resource_reservations (
    reservation_id    TEXT PRIMARY KEY,
    scope_id          TEXT NOT NULL REFERENCES resource_scopes(scope_id),
    child_scope_id    TEXT,
    dimension         TEXT NOT NULL,
    requested_micros  INTEGER NOT NULL,
    granted_micros    INTEGER NOT NULL,
    settled_micros    INTEGER NOT NULL DEFAULT 0,
    state             TEXT NOT NULL,
    idempotency_key   TEXT NOT NULL,
    lease_expires_at  TEXT,
    fencing_token     INTEGER NOT NULL,
    provenance_json   TEXT NOT NULL DEFAULT '{}',
    created_at        TEXT NOT NULL,
    updated_at        TEXT NOT NULL,
    UNIQUE(scope_id, idempotency_key)
);
CREATE INDEX IF NOT EXISTS idx_resource_reservations_live
    ON resource_reservations(scope_id, state, lease_expires_at);
"""


def apply_schema(conn: sqlite3.Connection) -> None:
    """Create the ledger schema if absent, and run any pending migration steps.

    Args:
        conn: An open sqlite3 connection to ~/.forecost/ledger.db.
    """
    conn.executescript(_DDL)
    (current_version,) = conn.execute("PRAGMA user_version").fetchone()
    if current_version < 3:
        _migrate_reconciliation_uniqueness(conn)
        current_version = 3
    if current_version < 4:
        _migrate_v4_receipt_kernel(conn)
        current_version = 4
    if current_version < 5:
        _migrate_v5_reconciliation_batches(conn)
        current_version = 5
    if current_version < 6:
        _migrate_v6_resource_envelopes(conn)


def _migrate_reconciliation_uniqueness(conn: sqlite3.Connection) -> None:
    """Make estimate reconciliation idempotent across concurrent processes.

    Earlier databases allowed duplicate rows for one estimate. Keep the oldest
    deterministic receipt before adding the unique index; the whole migration
    is transactional so a failed index build cannot leave a partially-deduped
    database or an advanced schema version.
    """
    conn.execute("BEGIN IMMEDIATE")
    try:
        conn.execute(
            """
            DELETE FROM reconciliations
            WHERE EXISTS (
                SELECT 1 FROM reconciliations older
                WHERE older.estimate_id = reconciliations.estimate_id
                  AND older.id < reconciliations.id
            )
            """
        )
        conn.execute(
            "CREATE UNIQUE INDEX IF NOT EXISTS "
            "idx_reconciliations_estimate ON reconciliations(estimate_id)"
        )
        conn.execute("PRAGMA user_version = 3")
        conn.commit()
    except BaseException:
        conn.rollback()
        raise


def _migrate_v4_receipt_kernel(conn: sqlite3.Connection) -> None:
    """Mark the additive receipt kernel migration complete transactionally.

    The DDL is idempotent and runs before this marker.  We still use an
    immediate transaction so a failed version update cannot advertise a schema
    that was only partly initialized.
    """
    conn.execute("BEGIN IMMEDIATE")
    try:
        conn.execute("PRAGMA user_version = 4")
        conn.commit()
    except BaseException:
        conn.rollback()
        raise


def _migrate_v5_reconciliation_batches(conn: sqlite3.Connection) -> None:
    """Mark additive reconciliation evidence tables as available."""
    conn.execute("BEGIN IMMEDIATE")
    try:
        conn.execute("PRAGMA user_version = 5")
        conn.commit()
    except BaseException:
        conn.rollback()
        raise


def _migrate_v6_resource_envelopes(conn: sqlite3.Connection) -> None:
    """Mark additive local resource-envelope tables as available."""
    conn.execute("BEGIN IMMEDIATE")
    try:
        conn.execute("PRAGMA user_version = 6")
        conn.commit()
    except BaseException:
        conn.rollback()
        raise
