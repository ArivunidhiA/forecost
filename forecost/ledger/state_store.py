"""IngestStateStore backed by the ledger's ingest_state table."""

from __future__ import annotations

import sqlite3
from collections.abc import Callable
from contextlib import contextmanager, suppress
from datetime import datetime, timezone
from typing import TypeAlias

from forecost.adapters.base import IngestStateStore
from forecost.ledger.db import ledger_write_lock

_MIGRATION_SAVEPOINT = "forecost_ingest_key_migration"
_CursorMember: TypeAlias = tuple[str, str]
_CursorGroups: TypeAlias = dict[str, list[_CursorMember]]


def _begin_migration(conn: sqlite3.Connection, *, nested: bool) -> None:
    if nested:
        conn.execute(f"SAVEPOINT {_MIGRATION_SAVEPOINT}")
        return
    # Serialize the read/map/write migration across processes so a concurrent
    # adapter cannot add or advance a legacy row between validation and deletion.
    conn.execute("BEGIN IMMEDIATE")


def _commit_migration(conn: sqlite3.Connection, *, nested: bool) -> None:
    if nested:
        conn.execute(f"RELEASE SAVEPOINT {_MIGRATION_SAVEPOINT}")
        return
    conn.commit()


def _rollback_migration(conn: sqlite3.Connection, *, nested: bool) -> None:
    if nested:
        conn.execute(f"ROLLBACK TO SAVEPOINT {_MIGRATION_SAVEPOINT}")
        conn.execute(f"RELEASE SAVEPOINT {_MIGRATION_SAVEPOINT}")
        return
    conn.rollback()


@contextmanager
def _migration_transaction(conn: sqlite3.Connection):
    nested = bool(conn.in_transaction)
    _begin_migration(conn, nested=nested)
    try:
        yield
    except BaseException:
        _rollback_migration(conn, nested=nested)
        raise
    else:
        _commit_migration(conn, nested=nested)


def _load_cursor_values(conn: sqlite3.Connection, source: str) -> dict[str, str]:
    rows = conn.execute(
        "SELECT cursor_key, cursor_val FROM ingest_state WHERE source = ?",
        (source,),
    ).fetchall()
    return {str(row["cursor_key"]): str(row["cursor_val"]) for row in rows}


def _group_cursor_values(
    values_by_key: dict[str, str],
    target_key: Callable[[str], str],
) -> _CursorGroups:
    grouped: _CursorGroups = {}
    for old_key, value in values_by_key.items():
        grouped.setdefault(target_key(old_key), []).append((old_key, value))
    return grouped


def _validate_cursor_groups(grouped: _CursorGroups) -> None:
    for new_key, group in grouped.items():
        legacy_keys = [old_key for old_key, _value in group if old_key != new_key]
        if len(legacy_keys) > 1:
            raise RuntimeError("ingest cursor identity collision")


def _legacy_value(new_key: str, group: list[_CursorMember]) -> str | None:
    return next((value for old_key, value in group if old_key != new_key), None)


def _merge_cursor_group(
    new_key: str,
    group: list[_CursorMember],
    values_by_key: dict[str, str],
    merge_values: Callable[[str | None, str], str],
) -> str:
    merged = values_by_key.get(new_key)
    legacy = _legacy_value(new_key, group)
    if legacy is not None:
        merged = merge_values(merged, legacy)
    if merged is None:  # pragma: no cover - nonempty group invariant
        raise RuntimeError("ingest cursor migration produced no value")
    # Normalize current-only values too; this removes any raw prompt id written
    # by an earlier release.
    return merge_values(None, merged)


def _cursor_group_changed(
    new_key: str,
    group: list[_CursorMember],
    values_by_key: dict[str, str],
    merged: str,
) -> bool:
    return values_by_key.get(new_key) != merged or any(
        old_key != new_key for old_key, _value in group
    )


def _upsert_cursor(
    conn: sqlite3.Connection,
    source: str,
    new_key: str,
    merged: str,
    now: str,
) -> None:
    conn.execute(
        """
        INSERT INTO ingest_state (source, cursor_key, cursor_val, updated_at)
        VALUES (?,?,?,?)
        ON CONFLICT(source, cursor_key) DO UPDATE SET
            cursor_val=excluded.cursor_val,
            updated_at=excluded.updated_at
        """,
        (source, new_key, merged, now),
    )


def _delete_legacy_cursors(
    conn: sqlite3.Connection,
    source: str,
    new_key: str,
    group: list[_CursorMember],
) -> int:
    legacy_keys = [old_key for old_key, _value in group if old_key != new_key]
    for old_key in legacy_keys:
        conn.execute(
            "DELETE FROM ingest_state WHERE source = ? AND cursor_key = ?",
            (source, old_key),
        )
    return len(legacy_keys)


def _apply_cursor_group(
    conn: sqlite3.Connection,
    source: str,
    new_key: str,
    group: list[_CursorMember],
    values_by_key: dict[str, str],
    merge_values: Callable[[str | None, str], str],
    now: str,
) -> int:
    merged = _merge_cursor_group(new_key, group, values_by_key, merge_values)
    if _cursor_group_changed(new_key, group, values_by_key, merged):
        _upsert_cursor(conn, source, new_key, merged, now)
    return _delete_legacy_cursors(conn, source, new_key, group)


def _apply_cursor_groups(
    conn: sqlite3.Connection,
    source: str,
    grouped: _CursorGroups,
    values_by_key: dict[str, str],
    merge_values: Callable[[str | None, str], str],
    now: str,
) -> int:
    return sum(
        _apply_cursor_group(
            conn,
            source,
            new_key,
            group,
            values_by_key,
            merge_values,
            now,
        )
        for new_key, group in grouped.items()
    )


class LedgerIngestStateStore(IngestStateStore):
    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    def get(self, source: str, key: str) -> str | None:
        row = self._conn.execute(
            "SELECT cursor_val FROM ingest_state WHERE source = ? AND cursor_key = ?",
            (source, key),
        ).fetchone()
        return row["cursor_val"] if row else None

    def set(self, source: str, key: str, value: str) -> None:
        now = datetime.now(timezone.utc).isoformat()
        with ledger_write_lock:
            self._conn.execute(
                """
                INSERT INTO ingest_state (source, cursor_key, cursor_val, updated_at)
                VALUES (?,?,?,?)
                ON CONFLICT(source, cursor_key) DO UPDATE SET cursor_val=excluded.cursor_val,
                    updated_at=excluded.updated_at
                """,
                (source, key, value, now),
            )
            self._conn.commit()

    def migrate_legacy_keys(
        self,
        source: str,
        target_key: Callable[[str], str],
        merge_values: Callable[[str | None, str], str],
    ) -> int:
        """Atomically replace every legacy key for ``source`` with an opaque key.

        ``target_key`` must return the current key unchanged and map each legacy
        key to its deterministic replacement.  The complete mapping is built
        and collision-checked before any row changes.  A current+legacy pair may
        share a target (an interrupted/concurrent rollout); two distinct legacy
        keys may not, because silently combining separate transcript cursors
        could skip usage.

        Values are merged by the caller so cursor-specific logic can rewind to
        the least advanced safe offset.  Raw keys exist only in memory during
        this transaction and are never logged.
        """
        now = datetime.now(timezone.utc).isoformat()
        with ledger_write_lock, _migration_transaction(self._conn):
            values_by_key = _load_cursor_values(self._conn, source)
            grouped = _group_cursor_values(values_by_key, target_key)
            _validate_cursor_groups(grouped)
            moved = _apply_cursor_groups(
                self._conn,
                source,
                grouped,
                values_by_key,
                merge_values,
                now,
            )
        # Best-effort removal of obsolete WAL frames.  Logical deletion is the
        # invariant; same-user forensic recovery from storage remains a residual
        # risk on filesystems/SSDs and is documented by the product threat model.
        with suppress(sqlite3.Error):
            self._conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        return moved
