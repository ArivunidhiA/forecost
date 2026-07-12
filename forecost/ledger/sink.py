"""Concrete LedgerSink: resolves workspace/session ids, prices events via
pricing.py, and hands (UsageEvent, postings) to the LedgerWriteQueue.
"""

from __future__ import annotations

import sqlite3
from datetime import datetime, timezone

from forecost.adapters.base import LedgerSink, PostingSpec, UsageEvent
from forecost.ledger.db import get_ledger_db
from forecost.ledger.writer import LedgerWriteQueue
from forecost.pricing import calculate_cost

PRICING_SNAPSHOT_VERSION = "bundled-2026-07"


def _get_or_create_workspace(conn: sqlite3.Connection, root_path: str) -> int:
    row = conn.execute("SELECT id FROM workspaces WHERE root_path = ?", (root_path,)).fetchone()
    if row:
        return row["id"]
    now = datetime.now(timezone.utc).isoformat()
    name = root_path.rstrip("/").rsplit("/", 1)[-1] or root_path
    cur = conn.execute(
        "INSERT INTO workspaces (name, root_path, created_at) VALUES (?,?,?)",
        (name, root_path, now),
    )
    conn.commit()
    if cur.lastrowid is None:  # pragma: no cover - unreachable after a successful INSERT
        raise RuntimeError("INSERT into workspaces did not yield a rowid")
    return cur.lastrowid


def _get_or_create_session(
    conn: sqlite3.Connection, session_uid: str, workspace_id: int | None, agent: str, ts: str
) -> int:
    row = conn.execute("SELECT id FROM sessions WHERE session_uid = ?", (session_uid,)).fetchone()
    if row:
        return row["id"]
    cur = conn.execute(
        "INSERT INTO sessions (session_uid, workspace_id, agent, started_at) VALUES (?,?,?,?)",
        (session_uid, workspace_id, agent, ts),
    )
    conn.commit()
    if cur.lastrowid is None:  # pragma: no cover - unreachable after a successful INSERT
        raise RuntimeError("INSERT into sessions did not yield a rowid")
    return cur.lastrowid


def _resolve_and_price(
    conn: sqlite3.Connection, event: UsageEvent
) -> tuple[UsageEvent, list[PostingSpec]]:
    workspace_id = None
    if event.workspace_path:
        workspace_id = _get_or_create_workspace(conn, event.workspace_path)
    session_id = None
    if event.session_uid:
        session_id = _get_or_create_session(
            conn, event.session_uid, workspace_id, event.agent or event.source, event.ts.isoformat()
        )

    resolved = UsageEvent(
        event_uid=event.event_uid,
        ts=event.ts,
        source=event.source,
        model=event.model,
        provider=event.provider,
        session_uid=event.session_uid,
        run_id=event.run_id,
        agent=event.agent,
        workspace_path=event.workspace_path,
        tokens_in=event.tokens_in,
        tokens_out=event.tokens_out,
        tokens_cache_read=event.tokens_cache_read,
        tokens_cache_write=event.tokens_cache_write,
        reported_cost=event.reported_cost,
        metadata=event.metadata,
        session_db_id=session_id,
        workspace_db_id=workspace_id,
    )

    postings: list[PostingSpec] = []
    usd_cost = calculate_cost(
        event.model,
        event.tokens_in,
        event.tokens_out,
        event.tokens_cache_read,
        event.tokens_cache_write,
    )
    postings.append(
        PostingSpec(
            currency="USD",
            amount=usd_cost,
            basis="pricing_table",
            pricing_version=PRICING_SNAPSHOT_VERSION,
        )
    )
    if event.reported_cost is not None:
        postings.append(
            PostingSpec(
                currency=event.reported_cost.currency,
                amount=event.reported_cost.amount,
                basis="source_reported",
            )
        )
    return resolved, postings


class SyncLedgerSink(LedgerSink):
    """Direct, synchronous writes — correct-by-default for CLI batch ingestion
    (e.g. `forecost ingest`, reading a few hundred JSONL turns in one pass).
    Uses INSERT OR IGNORE on event_uid for idempotent re-ingest, same as the
    async path. Not for the hook hot path — use DefaultLedgerSink there."""

    def __init__(self, ledger_path=None) -> None:
        self._conn = get_ledger_db(ledger_path)

    def emit(self, event: UsageEvent) -> None:
        resolved, postings = _resolve_and_price(self._conn, event)
        cur = self._conn.execute(
            """
            INSERT OR IGNORE INTO usage_events (
                event_uid, ts, source, session_id, workspace_id, run_id,
                provider, model, tokens_in, tokens_out, tokens_cache_read,
                tokens_cache_write, metadata
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)
            """,
            (
                resolved.event_uid,
                resolved.ts.isoformat(),
                resolved.source,
                resolved.session_db_id,
                resolved.workspace_db_id,
                resolved.run_id,
                resolved.provider,
                resolved.model,
                resolved.tokens_in,
                resolved.tokens_out,
                resolved.tokens_cache_read,
                resolved.tokens_cache_write,
                __import__("json").dumps(resolved.metadata) if resolved.metadata else None,
            ),
        )
        if cur.rowcount == 0:
            return  # duplicate event_uid
        event_db_id = cur.lastrowid
        now = datetime.now(timezone.utc).isoformat()
        for p in postings:
            self._conn.execute(
                "INSERT INTO postings "
                "(event_id, currency, amount, basis, pricing_version, created_at) "
                "VALUES (?,?,?,?,?,?)",
                (event_db_id, p.currency, p.amount, p.basis, p.pricing_version, now),
            )
        self._conn.commit()

    def flush(self, timeout: float = 2.0) -> None:
        self._conn.commit()


class DefaultLedgerSink(LedgerSink):
    """Resolves ids, computes a pricing_table posting for every event, and
    writes through the async queue. If the event carries a source-reported
    cost, that becomes an additional, higher-precedence posting."""

    def __init__(self, ledger_path=None) -> None:
        from forecost.ledger.db import LEDGER_PATH

        self._conn = get_ledger_db(ledger_path)
        self._queue = LedgerWriteQueue(ledger_path or LEDGER_PATH)

    def emit(self, event: UsageEvent) -> None:
        resolved, postings = _resolve_and_price(self._conn, event)
        self._queue.put(resolved, postings)

    def flush(self, timeout: float = 2.0) -> None:
        import time

        time.sleep(min(timeout, 2.5))
