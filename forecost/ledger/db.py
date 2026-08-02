"""Connection management for the ledger database (~/.forecost/ledger.db)."""

from __future__ import annotations

import contextlib
import sqlite3
import threading
from datetime import datetime, timezone
from pathlib import Path

from forecost.adapters.base import content_free_identifier
from forecost.core.paths import chmod_private, ensure_private_dir, forecost_home
from forecost.ledger.schema import apply_schema

LEDGER_PATH = forecost_home() / "ledger.db"

_conn: sqlite3.Connection | None = None
_conn_lock = threading.Lock()

# sqlite3 connections may be opened with ``check_same_thread=False``, but a
# transaction must still never be interleaved by two callers sharing that
# connection.  Synchronous sinks use this process-wide lock around the complete
# event + postings transaction.  Separate async connections are serialized by
# SQLite's ``BEGIN IMMEDIATE`` lock.
ledger_write_lock = threading.RLock()


def _row_id(row: sqlite3.Row | tuple) -> int:
    return int(row["id"] if isinstance(row, sqlite3.Row) else row[0])


def get_or_create_workspace(
    conn: sqlite3.Connection, root_path: str, *, commit: bool = True
) -> int:
    """Resolve a workspace without splitting a caller-owned transaction."""
    with ledger_write_lock:
        row = conn.execute("SELECT id FROM workspaces WHERE root_path = ?", (root_path,)).fetchone()
        if row:
            return _row_id(row)
        now = datetime.now(timezone.utc).isoformat()
        name = root_path.rstrip("/").rsplit("/", 1)[-1] or root_path
        conn.execute(
            "INSERT OR IGNORE INTO workspaces (name, root_path, created_at) VALUES (?,?,?)",
            (name, root_path, now),
        )
        row = conn.execute("SELECT id FROM workspaces WHERE root_path = ?", (root_path,)).fetchone()
        if row is None:  # pragma: no cover - INSERT/SELECT invariant
            raise RuntimeError("workspace insert did not yield an id")
        if commit:
            conn.commit()
        return _row_id(row)


def get_or_create_session(
    conn: sqlite3.Connection,
    session_uid: str,
    workspace_id: int | None,
    agent: str,
    ts: str,
    *,
    commit: bool = True,
) -> int:
    """Resolve a session without splitting a caller-owned transaction."""
    session_uid = content_free_identifier("session", session_uid)
    with ledger_write_lock:
        row = conn.execute(
            "SELECT id FROM sessions WHERE session_uid = ?", (session_uid,)
        ).fetchone()
        if row:
            return _row_id(row)
        conn.execute(
            """
            INSERT OR IGNORE INTO sessions
                (session_uid, workspace_id, agent, started_at)
            VALUES (?,?,?,?)
            """,
            (session_uid, workspace_id, agent, ts),
        )
        row = conn.execute(
            "SELECT id FROM sessions WHERE session_uid = ?", (session_uid,)
        ).fetchone()
        if row is None:  # pragma: no cover - INSERT/SELECT invariant
            raise RuntimeError("session insert did not yield an id")
        if commit:
            conn.commit()
        return _row_id(row)


def _ensure_dir(path: Path | None = None) -> None:
    """Create the parent for ``path`` with owner-only permissions.

    ``LEDGER_PATH`` can be redirected by tests and by embedders.  Resolving the
    default at call time avoids capturing the import-time value in a default
    argument and accidentally creating the original directory instead.
    """
    ensure_private_dir((path or LEDGER_PATH).parent)


def _lock_down_db_files(path: Path) -> None:
    """Make the DB and its WAL/SHM sidecars owner-only — the sidecars hold the
    same spend data as the main file, so all three must be private."""
    for p in (path, path.with_name(path.name + "-wal"), path.with_name(path.name + "-shm")):
        chmod_private(p)


def _apply_pragmas(conn: sqlite3.Connection) -> None:
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=5000")
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.execute("PRAGMA foreign_keys=ON")


def get_ledger_db(path: Path | None = None) -> sqlite3.Connection:
    """Return the process-wide ledger connection, creating it if needed.

    Args:
        path: Override the ledger file path (used by tests). When omitted,
            reuses (and caches) the process-wide connection at LEDGER_PATH.

    Returns:
        sqlite3.Connection: Initialized connection with schema and pragmas applied.
    """
    global _conn
    if path is not None and path != LEDGER_PATH:
        _ensure_dir(path)
        conn = sqlite3.connect(str(path), check_same_thread=False)
        conn.row_factory = sqlite3.Row
        _apply_pragmas(conn)
        apply_schema(conn)
        _lock_down_db_files(path)
        return conn

    with _conn_lock:
        if _conn is not None:
            return _conn
        _ensure_dir()
        _conn = sqlite3.connect(str(LEDGER_PATH), check_same_thread=False)
        _conn.row_factory = sqlite3.Row
        _apply_pragmas(_conn)
        apply_schema(_conn)
        _lock_down_db_files(LEDGER_PATH)  # main + -wal/-shm sidecars
        return _conn


def reset_connection_for_tests() -> None:
    """Close and clear the cached connection. Test-only helper."""
    global _conn
    with _conn_lock:
        if _conn is not None:
            with contextlib.suppress(sqlite3.Error):
                _conn.close()
            _conn = None
