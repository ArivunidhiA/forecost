"""Async batch writer for the ledger, generalizing forecost/db.py's WriteQueue.

Same discipline as the original (own connection in the worker thread, batch
flush every 100 items or 2 seconds, never block the caller, atexit drain with
a timeout, recovery.jsonl dead-letter on repeated failure) — the payload is now
(UsageEvent, list[PostingSpec]) instead of a flat usage_logs tuple, and both
tables are written in one transaction per batch.
"""

from __future__ import annotations

import atexit
import json
import threading
import time
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from queue import Empty, Full, Queue

from forecost.adapters.base import PostingSpec, UsageEvent
from forecost.core.errlog import log_error
from forecost.ledger.db import LEDGER_PATH, _apply_pragmas, _ensure_dir

_BATCH_SIZE = 100
_FLUSH_INTERVAL = 2.0
_EXIT_TIMEOUT = 1.0

_WriteItem = tuple[UsageEvent, list[PostingSpec]]


class _Barrier:
    """A drain marker. FIFO ordering guarantees every item enqueued before this
    marker has been dequeued (and thus flushed) by the time the worker sets the
    event — so `drain()` is a real barrier, not a hopeful sleep."""

    __slots__ = ("event",)

    def __init__(self) -> None:
        self.event = threading.Event()


def _insert_batch(conn, items: list[_WriteItem]) -> int:
    inserted = 0
    for event, postings in items:
        cur = conn.execute(
            """
            INSERT OR IGNORE INTO usage_events (
                event_uid, ts, source, session_id, workspace_id, run_id,
                provider, model, tokens_in, tokens_out, tokens_cache_read,
                tokens_cache_write, metadata
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)
            """,
            (
                event.event_uid,
                event.ts.isoformat(),
                event.source,
                event.session_db_id,
                event.workspace_db_id,
                event.run_id,
                event.provider,
                event.model,
                event.tokens_in,
                event.tokens_out,
                event.tokens_cache_read,
                event.tokens_cache_write,
                json.dumps(event.metadata) if event.metadata else None,
            ),
        )
        if cur.rowcount == 0:
            continue  # duplicate event_uid — idempotent re-ingest, skip postings too
        event_db_id = cur.lastrowid
        inserted += 1
        now = datetime.now(timezone.utc).isoformat()
        for p in postings:
            conn.execute(
                """
                INSERT INTO postings
                    (event_id, currency, amount, basis, pricing_version, created_at)
                VALUES (?,?,?,?,?,?)
                """,
                (event_db_id, p.currency, p.amount, p.basis, p.pricing_version, now),
            )
    conn.commit()
    return inserted


class LedgerWriteQueue:
    """Async batch writer for usage_events + postings. Never blocks the caller."""

    def __init__(self, ledger_path: Path = LEDGER_PATH) -> None:
        self._ledger_path = ledger_path
        self._queue: Queue[_WriteItem | _Barrier | None] = Queue(maxsize=10_000)
        self._thread = threading.Thread(target=self._worker, daemon=True)
        self._thread.start()
        atexit.register(self._on_exit)

    def put(self, event: UsageEvent, postings: list[PostingSpec]) -> None:
        try:
            self._queue.put_nowait((event, postings))
        except Full:
            log_error(
                "ledger.writer",
                f"WriteQueue full (10,000 items) — dropping event for model={event.model}",
            )
        except Exception as exc:  # nosec B110 - never block the caller
            log_error("ledger.writer", f"put failed: {exc!r}")

    def drain(self, timeout: float = 5.0) -> bool:
        """Block until every item enqueued before this call has been flushed to
        the DB. Returns True if the drain completed within `timeout`, else False.

        This is the real barrier that replaces the old `time.sleep`-based flush:
        callers that must read their own writes back (the stop-hook calibration
        loop) can now do so deterministically instead of racing the flush timer.
        """
        if not self._thread.is_alive():
            return False
        barrier = _Barrier()
        try:
            self._queue.put(barrier, timeout=timeout)
        except Full:
            return False
        return barrier.event.wait(timeout)

    def _worker(self) -> None:
        import sqlite3

        from forecost.ledger.schema import apply_schema

        _ensure_dir(self._ledger_path)
        conn = sqlite3.connect(str(self._ledger_path), check_same_thread=False)
        _apply_pragmas(conn)
        apply_schema(conn)
        batch: list[_WriteItem] = []
        last_flush = time.monotonic()
        while True:
            try:
                item = self._queue.get(timeout=0.1)
            except Empty:
                now = time.monotonic()
                if batch and (now - last_flush) >= _FLUSH_INTERVAL:
                    self._flush(batch, conn)
                    batch = []
                    last_flush = now
                continue
            if item is None:
                self._flush(batch, conn)
                conn.close()
                break
            if isinstance(item, _Barrier):
                self._flush(batch, conn)  # everything before the barrier is now durable
                batch = []
                last_flush = time.monotonic()
                item.event.set()
                continue
            batch.append(item)
            now = time.monotonic()
            if len(batch) >= _BATCH_SIZE or (now - last_flush) >= _FLUSH_INTERVAL:
                self._flush(batch, conn)
                batch = []
                last_flush = now

    def _flush(self, batch: list[_WriteItem], conn) -> None:
        if not batch:
            return
        recovery_path = self._ledger_path.parent / "recovery.jsonl"
        try:
            _insert_batch(conn, batch)
        except Exception as e:
            log_error("ledger.writer", f"flush failed, retrying once: {e!r}")
            time.sleep(0.5)
            try:
                _insert_batch(conn, batch)
            except Exception as e2:
                log_error(
                    "ledger.writer", f"flush failed after retry, spilling to recovery: {e2!r}"
                )
                try:
                    with open(recovery_path, "a", encoding="utf-8") as f:
                        for event, postings in batch:
                            row = asdict(event)
                            row["ts"] = event.ts.isoformat()
                            row["postings"] = [asdict(p) for p in postings]
                            f.write(json.dumps(row, default=str) + "\n")
                    from forecost.core.paths import chmod_private

                    chmod_private(recovery_path)  # dead-letter holds event metadata
                except OSError as e3:
                    log_error("ledger.writer", f"recovery spill failed, batch lost: {e3!r}")

    def _on_exit(self) -> None:
        try:
            self._queue.put(None, timeout=_EXIT_TIMEOUT)
        except Exception:
            return
        self._thread.join(timeout=_EXIT_TIMEOUT)
