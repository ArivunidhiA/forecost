"""Connection management for the ledger database (~/.forecost/ledger.db)."""

from __future__ import annotations

import contextlib
import sqlite3
import threading
from datetime import datetime, timezone
from pathlib import Path

from forecost.adapters.base import content_free_identifier
from forecost.core.paths import (
    UnsafeDataPathError,
    chmod_private,
    ensure_private_dir,
    forecost_home,
    validate_private_file,
)
from forecost.ledger.schema import SCHEMA_VERSION, apply_schema

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
    """Resolve a workspace without retaining its raw path at rest."""
    root_path = content_free_identifier("workspace", root_path)
    with ledger_write_lock:
        row = conn.execute("SELECT id FROM workspaces WHERE root_path = ?", (root_path,)).fetchone()
        if row:
            return _row_id(row)
        now = datetime.now(timezone.utc).isoformat()
        name = f"workspace-{root_path.rsplit(':', 1)[-1][:10]}"
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
        validate_private_file(p)


def _open_ledger(path: Path) -> sqlite3.Connection:
    """Open a regular owner-controlled file and detect direct replacement races."""
    if ".." in path.parts:
        raise UnsafeDataPathError("ledger path must not contain parent traversal")
    validate_private_file(path)
    before = path.stat(follow_symlinks=False) if path.exists() else None
    conn = sqlite3.connect(str(path), check_same_thread=False)
    try:
        validate_private_file(path, may_not_exist=False)
        after = path.stat(follow_symlinks=False)
        if before is not None and (before.st_dev, before.st_ino) != (after.st_dev, after.st_ino):
            raise UnsafeDataPathError("ledger file changed while it was being opened")
        return conn
    except BaseException:
        conn.close()
        raise


def _open_readonly_ledger(path: Path) -> sqlite3.Connection:
    """Open an existing current-schema ledger without creating or migrating it."""
    if ".." in path.parts:
        raise UnsafeDataPathError("ledger path must not contain parent traversal")
    validate_private_file(path, may_not_exist=False)
    before = path.stat(follow_symlinks=False)
    uri = f"{path.resolve().as_uri()}?mode=ro"
    conn = sqlite3.connect(uri, uri=True, check_same_thread=False)
    try:
        validate_private_file(path, may_not_exist=False)
        after = path.stat(follow_symlinks=False)
        if (before.st_dev, before.st_ino) != (after.st_dev, after.st_ino):
            raise UnsafeDataPathError("ledger file changed while it was being opened")
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA query_only=ON")
        conn.execute("PRAGMA busy_timeout=5000")
        conn.execute("PRAGMA foreign_keys=ON")
        version = int(conn.execute("PRAGMA user_version").fetchone()[0])
        if version != SCHEMA_VERSION:
            raise sqlite3.DatabaseError(
                f"ledger schema {version} is not readable as schema {SCHEMA_VERSION}; "
                "run an explicit ledger migration first"
            )
        return conn
    except BaseException:
        conn.close()
        raise


def _apply_pragmas(conn: sqlite3.Connection) -> None:
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=5000")
    # The receipt journal is Forecost's canonical evidence store.  FULL makes a
    # successful commit wait for SQLite's WAL and commit boundary to be synced,
    # rather than accepting NORMAL's documented power-loss window.  This is a
    # local durability boundary, not protection from a same-user rewrite or a
    # storage device that lies about fsync.
    conn.execute("PRAGMA synchronous=FULL")
    conn.execute("PRAGMA foreign_keys=ON")
    # Runtime cursor migration deletes legacy transcript-path keys. Overwrite
    # deleted cells instead of retaining their bytes on SQLite's freelist; the
    # migrator separately attempts to truncate obsolete WAL frames.
    conn.execute("PRAGMA secure_delete=ON")


def create_verified_snapshot(source: sqlite3.Connection, destination_path: Path) -> None:
    """Create and integrity-check a standalone SQLite snapshot.

    SQLite's backup API includes committed pages that still live in WAL; a
    filesystem copy of only the main file does not.  Callers own destination
    naming, collision policy, permission hardening, and cleanup on failure.
    """
    destination = sqlite3.connect(str(destination_path))
    try:
        destination.execute("PRAGMA synchronous=FULL")
        source.backup(destination)
        findings = [str(row[0]) for row in destination.execute("PRAGMA integrity_check")]
        if findings != ["ok"]:
            detail = "; ".join(findings[:3]) or "no result"
            raise sqlite3.DatabaseError(f"snapshot failed SQLite integrity_check: {detail}")
        destination.commit()
    finally:
        destination.close()


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
        conn = _open_ledger(path)
        conn.row_factory = sqlite3.Row
        _apply_pragmas(conn)
        apply_schema(conn)
        _lock_down_db_files(path)
        return conn

    with _conn_lock:
        if _conn is not None:
            return _conn
        _ensure_dir()
        _conn = _open_ledger(LEDGER_PATH)
        _conn.row_factory = sqlite3.Row
        _apply_pragmas(_conn)
        apply_schema(_conn)
        _lock_down_db_files(LEDGER_PATH)  # main + -wal/-shm sidecars
        return _conn


def get_readonly_ledger_db(path: Path | None = None) -> sqlite3.Connection:
    """Return a non-cached, query-only connection to an existing current ledger.

    Unlike :func:`get_ledger_db`, this function never creates the data root,
    creates a database, applies pragmas that change journal state, or migrates a
    schema. SQLite may create or update WAL/SHM coordination sidecars while
    opening a live WAL database; those are not Forecost evidence mutations.
    Callers must close the returned connection.
    """
    return _open_readonly_ledger(path or LEDGER_PATH)


def reset_connection_for_tests() -> None:
    """Close and clear the cached connection. Test-only helper."""
    global _conn
    with _conn_lock:
        if _conn is not None:
            with contextlib.suppress(sqlite3.Error):
                _conn.close()
            _conn = None
