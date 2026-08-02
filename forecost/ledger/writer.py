"""Async batch writer for the ledger, generalizing forecost/db.py's WriteQueue.

Same discipline as the original (own connection in the worker thread, batch
flush every 100 items or 2 seconds, never block the caller, durable normal-exit
drain, immutable recovery spools on repeated failure) — the payload is now
(UsageEvent, list[PostingSpec]) instead of a flat usage_logs tuple, and both
tables are written in one transaction per batch.
"""

from __future__ import annotations

import atexit
import json
import threading
import time
from dataclasses import asdict, dataclass, field, replace
from datetime import datetime, timezone
from pathlib import Path
from queue import Empty, Full, Queue

from forecost.adapters.base import PostingSpec, UsageEvent
from forecost.core.errlog import log_error
from forecost.core.spool import write_immutable_spool
from forecost.ledger.db import (
    LEDGER_PATH,
    _apply_pragmas,
    _ensure_dir,
    _lock_down_db_files,
    get_or_create_session,
    get_or_create_workspace,
)

_BATCH_SIZE = 100
_FLUSH_INTERVAL = 2.0

_WriteItem = tuple[UsageEvent, list[PostingSpec]]
_RECOVERY_LOCK = threading.Lock()


class LedgerWriteError(RuntimeError):
    """A transient async-ledger failure that requires the caller to retry."""


class _Barrier:
    """A drain marker. FIFO ordering guarantees every item enqueued before this
    marker has been dequeued (and thus flushed) by the time the worker sets the
    event — so `drain()` is a real barrier, not a hopeful sleep."""

    __slots__ = ("error", "event")

    def __init__(self) -> None:
        self.event = threading.Event()
        self.error: str | None = None

    @property
    def succeeded(self) -> bool:
        return self.event.is_set() and self.error is None


@dataclass
class _WorkerState:
    batch: list[_WriteItem] = field(default_factory=list)
    last_flush: float = field(default_factory=time.monotonic)
    pending_error: str | None = None


def _resolve_event(conn, event: UsageEvent) -> UsageEvent:
    workspace_id = event.workspace_db_id
    if workspace_id is None and event.workspace_path:
        workspace_id = get_or_create_workspace(conn, event.workspace_path, commit=False)
    session_id = event.session_db_id
    if session_id is None and event.session_uid:
        session_id = get_or_create_session(
            conn,
            event.session_uid,
            workspace_id,
            event.agent or event.source,
            event.ts.isoformat(),
            commit=False,
        )
    return replace(event, session_db_id=session_id, workspace_db_id=workspace_id)


def _insert_event(conn, event: UsageEvent, postings: list[PostingSpec]) -> None:
    cur = conn.execute(
        """
        INSERT INTO usage_events (
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
    event_db_id = cur.lastrowid
    if event_db_id is None:  # pragma: no cover - successful SQLite INSERT invariant
        raise RuntimeError("usage event insert did not yield an id")
    now = datetime.now(timezone.utc).isoformat()
    for posting in postings:
        conn.execute(
            """
            INSERT INTO postings
                (event_id, currency, amount, basis, pricing_version, created_at)
            VALUES (?,?,?,?,?,?)
            """,
            (
                event_db_id,
                posting.currency,
                posting.amount,
                posting.basis,
                posting.pricing_version,
                now,
            ),
        )


def _insert_batch(conn, items: list[_WriteItem]) -> int:
    """Insert a batch as one rollback-safe transaction.

    Resolution rows, usage events, and postings share the transaction.  A
    posting or commit failure therefore cannot strand an event row that a retry
    would mistake for a completed duplicate.
    """
    inserted = 0
    nested = bool(getattr(conn, "in_transaction", False))
    if nested:
        conn.execute("SAVEPOINT forecost_event_batch")
    else:
        conn.execute("BEGIN IMMEDIATE")
    try:
        for event, postings in items:
            duplicate = conn.execute(
                "SELECT 1 FROM usage_events WHERE event_uid = ?", (event.event_uid,)
            ).fetchone()
            if duplicate:
                continue
            _insert_event(conn, _resolve_event(conn, event), postings)
            inserted += 1
        if nested:
            conn.execute("RELEASE SAVEPOINT forecost_event_batch")
        else:
            conn.commit()
    except BaseException:
        if nested:
            conn.execute("ROLLBACK TO SAVEPOINT forecost_event_batch")
            conn.execute("RELEASE SAVEPOINT forecost_event_batch")
        else:
            conn.rollback()
        raise
    return inserted


def _spill_batch(recovery_path: Path, batch: list[_WriteItem]) -> None:
    """Publish a failed batch as its own immutable, owner-only recovery spool."""
    rows: list[dict[str, object]] = []
    for event, postings in batch:
        row = asdict(event)
        row["ts"] = event.ts.isoformat()
        row["postings"] = [asdict(posting) for posting in postings]
        rows.append(row)

    with _RECOVERY_LOCK:
        write_immutable_spool(recovery_path, rows)


class LedgerWriteQueue:
    """Async batch writer for usage_events + postings. Never blocks the caller."""

    def __init__(self, ledger_path: Path = LEDGER_PATH) -> None:
        self._ledger_path = ledger_path
        self._queue: Queue[_WriteItem | _Barrier | None] = Queue(maxsize=10_000)
        self._ready = threading.Event()
        self._worker_error: str | None = None
        self._last_error: str | None = None
        self._close_lock = threading.Lock()
        self._closed = False
        self._thread = threading.Thread(target=self._worker, daemon=True)
        self._thread.start()
        # Startup happens on the worker so it owns its SQLite connection.  Wait
        # for that handshake before accepting events; otherwise schema/open
        # failure could leave accepted items in an unserviced queue.
        if not self._ready.wait(timeout=5.0):
            self._worker_error = "ledger writer did not initialize within 5 seconds"
            self._last_error = self._worker_error
        atexit.register(self.close)

    @property
    def last_error(self) -> str | None:
        return self._last_error

    def put(self, event: UsageEvent, postings: list[PostingSpec]) -> bool:
        if getattr(self, "_closed", False):
            self._last_error = "ledger writer is closed"
            return False
        if self._worker_error is not None or not self._thread.is_alive():
            self._last_error = self._worker_error or "ledger writer is not running"
            log_error("ledger.writer", self._last_error)
            return False
        try:
            self._queue.put_nowait((event, postings))
            return True
        except Full:
            self._last_error = "ledger write queue is full"
            log_error(
                "ledger.writer",
                f"WriteQueue full (10,000 items) — refusing event for model={event.model}",
            )
            return False
        except Exception as exc:  # nosec B110 - never block the caller
            self._last_error = f"ledger enqueue failed: {exc!r}"
            log_error("ledger.writer", self._last_error)
            return False

    def drain(self, timeout: float = 5.0) -> bool:
        """Block until every item enqueued before this call has been flushed to
        the DB. Returns True if the drain completed within `timeout`, else False.

        This is the real barrier that replaces the old `time.sleep`-based flush:
        callers that must read their own writes back (the stop-hook calibration
        loop) can now do so deterministically instead of racing the flush timer.
        """
        deadline = time.monotonic() + max(timeout, 0.0)
        if self._worker_error is not None or not self._thread.is_alive():
            self._last_error = self._worker_error or "ledger writer is not running"
            return False
        barrier = _Barrier()
        try:
            self._queue.put(barrier, timeout=max(deadline - time.monotonic(), 0.0))
        except Full:
            self._last_error = "timed out enqueueing ledger drain barrier"
            return False
        if not barrier.event.wait(max(deadline - time.monotonic(), 0.0)):
            self._last_error = "timed out waiting for ledger drain"
            return False
        self._last_error = barrier.error
        return barrier.succeeded

    def _open_connection(self):
        import sqlite3

        from forecost.ledger.schema import apply_schema

        _ensure_dir(self._ledger_path)
        conn = sqlite3.connect(str(self._ledger_path), check_same_thread=False)
        conn.row_factory = sqlite3.Row
        _apply_pragmas(conn)
        apply_schema(conn)
        _lock_down_db_files(self._ledger_path)
        return conn

    def _worker(self) -> None:
        try:
            conn = self._open_connection()
        except Exception as exc:
            self._worker_error = f"ledger writer startup failed: {exc!r}"
            self._last_error = self._worker_error
            log_error("ledger.writer", self._worker_error)
            self._ready.set()
            return
        self._ready.set()
        self._worker_loop(conn)

    def _worker_loop(self, conn) -> None:
        state = _WorkerState()
        while True:
            try:
                item = self._queue.get(timeout=0.1)
            except Empty:
                self._flush_if_due(state, conn)
                continue
            if item is None:
                self._flush(state.batch, conn)
                conn.close()
                return
            self._handle_item(item, state, conn)

    def _flush_state(self, state: _WorkerState, conn) -> None:
        if not self._flush(state.batch, conn):
            state.pending_error = self._last_error or "ledger batch did not commit"
        state.batch = []
        state.last_flush = time.monotonic()

    def _flush_if_due(self, state: _WorkerState, conn) -> None:
        if state.batch and (time.monotonic() - state.last_flush) >= _FLUSH_INTERVAL:
            self._flush_state(state, conn)

    def _handle_item(self, item: _WriteItem | _Barrier, state: _WorkerState, conn) -> None:
        if isinstance(item, _Barrier):
            self._finish_barrier(item, state, conn)
            return
        state.batch.append(item)
        if len(state.batch) >= _BATCH_SIZE:
            self._flush_state(state, conn)
        else:
            self._flush_if_due(state, conn)

    def _finish_barrier(self, barrier: _Barrier, state: _WorkerState, conn) -> None:
        self._flush_state(state, conn)
        barrier.error = state.pending_error
        barrier.event.set()
        state.pending_error = None

    def _flush(self, batch: list[_WriteItem], conn) -> bool:
        if not batch:
            return True
        recovery_path = self._ledger_path.parent / "recovery.jsonl"
        try:
            _insert_batch(conn, batch)
            return True
        except Exception as e:
            log_error("ledger.writer", f"flush failed, retrying once: {e!r}")
            time.sleep(0.5)
            try:
                _insert_batch(conn, batch)
                return True
            except Exception as e2:
                log_error(
                    "ledger.writer", f"flush failed after retry, spilling to recovery: {e2!r}"
                )
                try:
                    _spill_batch(recovery_path, batch)
                    self._last_error = (
                        "ledger database write failed; batch was preserved in a recovery spool"
                    )
                except OSError as e3:
                    self._last_error = f"ledger database and recovery spill failed: {e3!r}"
                    log_error("ledger.writer", self._last_error)
                return False

    def close(self) -> None:
        """Durably finish every accepted item before a normal process exit."""
        with self._close_lock:
            if self._closed:
                return
            if self._thread.is_alive():
                # The sentinel is FIFO. A blocking put plus unbounded join is
                # intentional here: returning would let Python terminate the
                # daemon with already-acknowledged events still memory-only.
                self._queue.put(None)
                self._thread.join()
            self._closed = True

    def _on_exit(self) -> None:
        """Backward-compatible alias for callers/tests from the legacy API."""
        self.close()
