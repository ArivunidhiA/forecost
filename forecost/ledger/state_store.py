"""IngestStateStore backed by the ledger's ingest_state table."""

from __future__ import annotations

import sqlite3
from datetime import datetime, timezone

from forecost.adapters.base import IngestStateStore
from forecost.ledger.db import ledger_write_lock


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
