"""Connection management for the ledger database (~/.forecost/ledger.db)."""

from __future__ import annotations

import contextlib
import sqlite3
import threading
from pathlib import Path

from forecost.core.paths import forecost_home
from forecost.ledger.schema import apply_schema

LEDGER_PATH = forecost_home() / "ledger.db"

_conn: sqlite3.Connection | None = None
_conn_lock = threading.Lock()


def _ensure_dir(path: Path = LEDGER_PATH) -> None:
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)


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
        with contextlib.suppress(OSError):
            LEDGER_PATH.chmod(0o600)
        return _conn


def reset_connection_for_tests() -> None:
    """Close and clear the cached connection. Test-only helper."""
    global _conn
    with _conn_lock:
        if _conn is not None:
            with contextlib.suppress(sqlite3.Error):
                _conn.close()
            _conn = None
