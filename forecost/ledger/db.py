"""Connection management for the ledger database (~/.forecost/ledger.db)."""

from __future__ import annotations

import contextlib
import sqlite3
import threading
from pathlib import Path

from forecost.core.paths import chmod_private, ensure_private_dir, forecost_home
from forecost.ledger.schema import apply_schema

LEDGER_PATH = forecost_home() / "ledger.db"

_conn: sqlite3.Connection | None = None
_conn_lock = threading.Lock()


def _ensure_dir(path: Path = LEDGER_PATH) -> None:
    ensure_private_dir(path.parent)


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
