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

SCHEMA_VERSION = 2

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
"""


def apply_schema(conn: sqlite3.Connection) -> None:
    """Create the ledger schema if absent, and run any pending migration steps.

    Args:
        conn: An open sqlite3 connection to ~/.forecost/ledger.db.
    """
    conn.executescript(_DDL)
    (current_version,) = conn.execute("PRAGMA user_version").fetchone()
    if current_version < SCHEMA_VERSION:
        # No prior versions exist yet (this is the initial ledger v2 schema);
        # the ladder below is where future `if current_version < N` steps go.
        conn.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")
    conn.commit()
