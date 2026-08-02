import sqlite3
from datetime import datetime, timezone
from queue import Queue

import pytest

from forecost.adapters.base import Money, PostingSpec, UsageEvent, content_free_identifier
from forecost.ledger.sink import SyncLedgerSink


def _event(uid="e1", **overrides):
    defaults = {
        "event_uid": uid,
        "ts": datetime.now(timezone.utc),
        "source": "test",
        "model": "claude-sonnet-4-20250514",
        "session_uid": "sess-1",
        "workspace_path": "/tmp/proj",
        "tokens_in": 1_000_000,
        "tokens_out": 500_000,
    }
    defaults.update(overrides)
    return UsageEvent(**defaults)


def test_schema_creates_all_tables(ledger_conn):
    tables = {
        r[0]
        for r in ledger_conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
    }
    expected = {
        "workspaces",
        "sessions",
        "usage_events",
        "postings",
        "plans",
        "budgets",
        "estimates",
        "reconciliations",
        "policy_decisions",
        "ingest_state",
        "outcomes",
        "guard_flags",
    }
    assert expected.issubset(tables)


def test_sync_sink_writes_event_and_pricing_table_posting(ledger_conn):
    sink = SyncLedgerSink(ledger_path=None)
    sink._conn = ledger_conn  # use the isolated test connection directly
    sink.emit(_event())
    row = ledger_conn.execute("SELECT currency, amount, basis FROM postings").fetchone()
    assert row["currency"] == "USD"
    # 1M input @ $3/Mtok + 500k output @ $15/Mtok = 3.00 + 7.50
    assert row["amount"] == 10.50
    assert row["basis"] == "pricing_table"


def test_canonical_spend_does_not_double_count_dual_basis(ledger_conn):
    """An event with both a pricing_table and a source_reported USD posting must
    count once in every operational total — not as the sum of both valuations.
    This is the fix for the double-count bug (deep-audit P0-1)."""
    from forecost.ledger import queries as q

    sink = SyncLedgerSink(ledger_path=None)
    sink._conn = ledger_conn
    # pricing_table posting = 10.50 (see test above); source_reported = 9.00.
    sink.emit(_event(uid="dual", reported_cost=Money(amount=9.00, currency="USD")))

    n_postings = ledger_conn.execute(
        "SELECT COUNT(*) FROM postings WHERE currency='USD'"
    ).fetchone()[0]
    assert n_postings == 2, "both valuations should be stored"

    all_time = "1970-01-01T00:00:00+00:00"
    # Canonical prefers source_reported: 9.00, and never 19.50 (the buggy sum).
    canonical = q.scope_spend(ledger_conn, "USD", all_time)
    assert canonical.total == 9.00
    assert canonical.n_events == 1
    # Pinning a basis shows that single valuation.
    assert q.scope_spend(ledger_conn, "USD", all_time, basis="pricing_table").total == 10.50
    assert q.scope_spend(ledger_conn, "USD", all_time, basis="source_reported").total == 9.00
    # by-model and session views agree (no double-count).
    assert q.spend_by_model(ledger_conn, "USD")[0]["total"] == 9.00
    sess_id = ledger_conn.execute("SELECT id FROM sessions LIMIT 1").fetchone()[0]
    assert q.session_spend(ledger_conn, sess_id) == 9.00


def test_unknown_model_posting_is_flagged_unpriced(ledger_conn):
    """A model with no real rate is priced with DEFAULT_COST, and the posting is
    flagged so `forecost pricing-audit` can surface it (deep-audit P0-2)."""
    from forecost.ledger.sink import UNPRICED_SUFFIX
    from forecost.pricing import is_priced

    assert is_priced("claude-opus-4-8") is True
    assert is_priced("some-brand-new-model-2027") is False

    sink = SyncLedgerSink(ledger_path=None)
    sink._conn = ledger_conn
    sink.emit(_event(uid="unk", model="some-brand-new-model-2027"))
    row = ledger_conn.execute(
        "SELECT pricing_version, basis FROM postings WHERE currency='USD'"
    ).fetchone()
    assert row["basis"] == "pricing_table"  # basis unchanged: canonical selection still works
    assert row["pricing_version"].endswith(UNPRICED_SUFFIX)

    # A known model is NOT flagged.
    sink.emit(_event(uid="known"))  # default model is a real, priced one
    versions = [
        r["pricing_version"]
        for r in ledger_conn.execute("SELECT pricing_version FROM postings").fetchall()
    ]
    assert any(not v.endswith(UNPRICED_SUFFIX) for v in versions)


def test_sync_sink_is_idempotent_on_event_uid(ledger_conn):
    sink = SyncLedgerSink(ledger_path=None)
    sink._conn = ledger_conn
    sink.emit(_event(uid="dup"))
    sink.emit(_event(uid="dup"))
    n = ledger_conn.execute("SELECT COUNT(*) FROM usage_events").fetchone()[0]
    assert n == 1


def test_sync_sink_resolves_workspace_and_session(ledger_conn):
    sink = SyncLedgerSink(ledger_path=None)
    sink._conn = ledger_conn
    sink.emit(_event())
    ws = ledger_conn.execute("SELECT root_path FROM workspaces").fetchone()
    sess = ledger_conn.execute("SELECT session_uid, agent FROM sessions").fetchone()
    assert ws["root_path"] == "/tmp/proj"
    assert sess["session_uid"] == content_free_identifier("session", "sess-1")
    assert sess["agent"] == "test"


def test_sync_sink_adds_source_reported_posting_when_present(ledger_conn):
    sink = SyncLedgerSink(ledger_path=None)
    sink._conn = ledger_conn
    quota_cost = Money(amount=1.23, currency="QUOTA:anthropic-max20x:week")
    sink.emit(_event(uid="e2", reported_cost=quota_cost))
    currencies = {r["currency"] for r in ledger_conn.execute("SELECT currency FROM postings")}
    assert currencies == {
        "USD",
        content_free_identifier("currency", "QUOTA:anthropic-max20x:week"),
    }


def test_no_cache_token_underpricing(ledger_conn):
    """Regression test for the cache-token-priced-at-zero bug fixed this session."""
    sink = SyncLedgerSink(ledger_path=None)
    sink._conn = ledger_conn
    sink.emit(
        _event(
            uid="cache1",
            tokens_in=0,
            tokens_out=0,
            tokens_cache_read=1_000_000,
            tokens_cache_write=1_000_000,
        )
    )
    amount = ledger_conn.execute("SELECT amount FROM postings").fetchone()["amount"]
    assert amount > 0


def test_default_async_sink_flushes_to_disk(tmp_path):
    """The async DefaultLedgerSink (used by the hook hot path) writes through its
    own WriteQueue worker thread and is drained by flush()."""
    import forecost.ledger.db as ledger_db
    from forecost.ledger.sink import DefaultLedgerSink

    path = tmp_path / "async_ledger.db"
    orig_conn = ledger_db._conn
    orig_path = ledger_db.LEDGER_PATH
    ledger_db._conn = None
    ledger_db.LEDGER_PATH = path
    try:
        sink = DefaultLedgerSink(ledger_path=path)
        sink.emit(_event(uid="async1"))
        sink.flush(timeout=2.5)
        conn = ledger_db.get_ledger_db(path)
        n = conn.execute("SELECT COUNT(*) FROM usage_events").fetchone()[0]
        assert n == 1
    finally:
        ledger_db._conn = orig_conn
        ledger_db.LEDGER_PATH = orig_path


def test_writer_flush_spills_to_recovery_on_persistent_failure(tmp_path, monkeypatch):
    """When the batch insert fails twice, the flush spills the batch to
    recovery.jsonl instead of losing it or raising."""
    from forecost.adapters.base import PostingSpec
    from forecost.ledger.writer import LedgerWriteQueue

    path = tmp_path / "ledger.db"

    q = LedgerWriteQueue(ledger_path=path)
    # Force _insert_batch to always fail so the retry-then-spill path runs.
    import forecost.ledger.writer as writer_mod

    monkeypatch.setattr(
        writer_mod, "_insert_batch", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("db down"))
    )
    q._flush([(_event(uid="spill1"), [PostingSpec("USD", 1.0, "pricing_table")])], None)
    recovery_files = list(tmp_path.glob("recovery.*.jsonl"))
    assert len(recovery_files) == 1
    line = recovery_files[0].read_text().strip()
    assert "spill1" in line


def test_writer_flush_empty_batch_is_noop(tmp_path):
    from forecost.ledger.writer import LedgerWriteQueue

    q = LedgerWriteQueue(ledger_path=tmp_path / "ledger.db")
    q._flush([], None)  # must not raise


def test_writer_insert_batch_writes_events_and_postings(ledger_conn):
    """The batch insert (shared by the async worker) writes events + postings and
    is idempotent on event_uid."""
    from forecost.adapters.base import PostingSpec
    from forecost.ledger.writer import _insert_batch

    ev = _event(uid="batch1")
    postings = [PostingSpec(currency="USD", amount=1.5, basis="pricing_table")]
    # give the event resolved db ids (the sink normally does this)
    from dataclasses import replace

    resolved = replace(ev, session_db_id=None, workspace_db_id=None)
    inserted = _insert_batch(ledger_conn, [(resolved, postings)])
    assert inserted == 1
    # re-inserting the same event_uid is a no-op
    inserted_again = _insert_batch(ledger_conn, [(resolved, postings)])
    assert inserted_again == 0
    assert ledger_conn.execute("SELECT COUNT(*) FROM postings").fetchone()[0] == 1


def test_sync_sink_rolls_back_event_and_resolution_rows_when_posting_fails(ledger_conn):
    """No event may become a visible duplicate before all postings are durable."""
    ledger_conn.execute(
        """
        CREATE TRIGGER reject_posting BEFORE INSERT ON postings
        BEGIN SELECT RAISE(FAIL, 'fault-injected posting failure'); END
        """
    )
    ledger_conn.commit()
    sink = SyncLedgerSink(ledger_path=None)
    sink._conn = ledger_conn

    with pytest.raises(sqlite3.IntegrityError, match="fault-injected posting failure"):
        sink.emit(_event(uid="atomic-posting"))

    assert ledger_conn.execute("SELECT COUNT(*) FROM usage_events").fetchone()[0] == 0
    assert ledger_conn.execute("SELECT COUNT(*) FROM postings").fetchone()[0] == 0
    assert ledger_conn.execute("SELECT COUNT(*) FROM workspaces").fetchone()[0] == 0
    assert ledger_conn.execute("SELECT COUNT(*) FROM sessions").fetchone()[0] == 0


def test_sync_sink_rolls_back_when_commit_raises(ledger_conn):
    class _CommitFailure:
        def __init__(self, conn):
            self._conn = conn

        def execute(self, *args, **kwargs):
            return self._conn.execute(*args, **kwargs)

        def commit(self):
            raise RuntimeError("fault-injected commit failure")

        def rollback(self):
            self._conn.rollback()

    sink = SyncLedgerSink(ledger_path=None)
    sink._conn = _CommitFailure(ledger_conn)  # type: ignore[assignment]

    with pytest.raises(RuntimeError, match="commit failure"):
        sink.emit(_event(uid="atomic-commit"))

    assert ledger_conn.execute("SELECT COUNT(*) FROM usage_events").fetchone()[0] == 0
    assert ledger_conn.execute("SELECT COUNT(*) FROM postings").fetchone()[0] == 0


def test_sync_sink_uses_savepoint_inside_caller_transaction(ledger_conn):
    ledger_conn.execute("CREATE TABLE caller_work (value TEXT)")
    ledger_conn.execute("INSERT INTO caller_work VALUES ('keep-pending')")
    assert ledger_conn.in_transaction
    sink = SyncLedgerSink(ledger_path=None)
    sink._conn = ledger_conn

    assert sink.emit(_event(uid="nested-transaction"))
    assert ledger_conn.in_transaction
    assert ledger_conn.execute("SELECT COUNT(*) FROM usage_events").fetchone()[0] == 1

    ledger_conn.rollback()
    assert ledger_conn.execute("SELECT COUNT(*) FROM caller_work").fetchone()[0] == 0
    assert ledger_conn.execute("SELECT COUNT(*) FROM usage_events").fetchone()[0] == 0


def test_batch_savepoint_failure_preserves_callers_transaction(ledger_conn):
    """A nested batch rollback must not roll back work owned by the caller."""
    from forecost.adapters.base import PostingSpec
    from forecost.ledger.writer import _insert_batch

    ledger_conn.execute("CREATE TABLE caller_work (value TEXT)")
    ledger_conn.execute("INSERT INTO caller_work VALUES ('keep-pending')")
    ledger_conn.execute(
        """
        CREATE TRIGGER reject_nested_posting BEFORE INSERT ON postings
        BEGIN SELECT RAISE(FAIL, 'nested posting failure'); END
        """
    )

    with pytest.raises(sqlite3.IntegrityError, match="nested posting failure"):
        _insert_batch(
            ledger_conn,
            [(_event(uid="nested-failure"), [PostingSpec("USD", 1.0, "pricing_table")])],
        )

    assert ledger_conn.in_transaction
    assert ledger_conn.execute("SELECT value FROM caller_work").fetchone()[0] == "keep-pending"
    assert ledger_conn.execute("SELECT COUNT(*) FROM usage_events").fetchone()[0] == 0


def test_sync_sink_serializes_concurrent_shared_connection_writes(ledger_conn):
    from concurrent.futures import ThreadPoolExecutor

    sink = SyncLedgerSink(ledger_path=None)
    sink._conn = ledger_conn
    with ThreadPoolExecutor(max_workers=8) as executor:
        accepted = list(executor.map(lambda i: sink.emit(_event(uid=f"thread-{i}")), range(40)))

    assert all(accepted)
    assert ledger_conn.execute("SELECT COUNT(*) FROM usage_events").fetchone()[0] == 40
    assert ledger_conn.execute("SELECT COUNT(*) FROM postings").fetchone()[0] == 40


def test_state_commit_cannot_split_an_event_transaction(ledger_conn):
    """Every writer using the cached connection shares the transaction lock."""
    import threading

    from forecost.ledger.state_store import LedgerIngestStateStore

    state = LedgerIngestStateStore(ledger_conn)
    started = threading.Event()
    worker: list[threading.Thread] = []

    def interleave_state_write():
        def write_state():
            started.set()
            state.set("test", "cursor", "after-failure")

        thread = threading.Thread(target=write_state)
        worker.append(thread)
        thread.start()
        assert started.wait(1.0)
        return 0

    ledger_conn.create_function("interleave_state_write", 0, interleave_state_write)
    ledger_conn.execute(
        """
        CREATE TRIGGER interleave_before_posting BEFORE INSERT ON postings
        BEGIN
            SELECT interleave_state_write();
            SELECT RAISE(FAIL, 'posting failed after interleave');
        END
        """
    )
    ledger_conn.commit()
    sink = SyncLedgerSink(ledger_path=None)
    sink._conn = ledger_conn

    with pytest.raises(sqlite3.IntegrityError, match="posting failed after interleave"):
        sink.emit(_event(uid="locked-event"))

    worker[0].join(timeout=1.0)
    assert not worker[0].is_alive()
    assert ledger_conn.execute("SELECT COUNT(*) FROM usage_events").fetchone()[0] == 0
    assert (
        ledger_conn.execute(
            "SELECT cursor_val FROM ingest_state WHERE source='test' AND cursor_key='cursor'"
        ).fetchone()[0]
        == "after-failure"
    )


def test_writer_queue_reports_saturation_instead_of_acknowledging_drop():
    from forecost.adapters.base import PostingSpec
    from forecost.ledger.writer import LedgerWriteQueue

    class _AliveThread:
        @staticmethod
        def is_alive():
            return True

    queue = LedgerWriteQueue.__new__(LedgerWriteQueue)
    queue._queue = Queue(maxsize=1)
    queue._queue.put_nowait(None)
    queue._thread = _AliveThread()  # type: ignore[assignment]
    queue._worker_error = None
    queue._last_error = None

    accepted = queue.put(_event(uid="overflow"), [PostingSpec("USD", 1.0, "pricing_table")])

    assert accepted is False
    assert queue.last_error == "ledger write queue is full"


def test_writer_queue_refuses_when_worker_is_not_running(monkeypatch):
    from forecost.adapters.base import PostingSpec
    from forecost.ledger.writer import LedgerWriteQueue

    queue = LedgerWriteQueue.__new__(LedgerWriteQueue)
    queue._worker_error = "startup failed"
    queue._last_error = None
    queue._thread = type("DeadThread", (), {"is_alive": lambda self: False})()  # type: ignore[assignment]

    assert queue.put(_event(uid="dead"), [PostingSpec("USD", 1.0, "pricing_table")]) is False
    assert queue.last_error == "startup failed"


def test_writer_queue_reports_unexpected_enqueue_error():
    from forecost.adapters.base import PostingSpec
    from forecost.ledger.writer import LedgerWriteQueue

    class _BrokenQueue:
        @staticmethod
        def put_nowait(item):
            raise RuntimeError("queue broken")

    queue = LedgerWriteQueue.__new__(LedgerWriteQueue)
    queue._queue = _BrokenQueue()  # type: ignore[assignment]
    queue._thread = type("AliveThread", (), {"is_alive": lambda self: True})()  # type: ignore[assignment]
    queue._worker_error = None
    queue._last_error = None

    assert queue.put(_event(uid="broken"), [PostingSpec("USD", 1.0, "pricing_table")]) is False
    assert "queue broken" in (queue.last_error or "")


def test_writer_drain_reports_dead_worker():
    from forecost.ledger.writer import LedgerWriteQueue

    queue = LedgerWriteQueue.__new__(LedgerWriteQueue)
    queue._worker_error = None
    queue._last_error = None
    queue._thread = type("DeadThread", (), {"is_alive": lambda self: False})()  # type: ignore[assignment]

    assert queue.drain(timeout=0.01) is False
    assert queue.last_error == "ledger writer is not running"


def test_writer_drain_reports_barrier_enqueue_timeout():
    from queue import Full

    from forecost.ledger.writer import LedgerWriteQueue

    class _FullQueue:
        @staticmethod
        def put(item, timeout):
            raise Full

    queue = LedgerWriteQueue.__new__(LedgerWriteQueue)
    queue._queue = _FullQueue()  # type: ignore[assignment]
    queue._thread = type("AliveThread", (), {"is_alive": lambda self: True})()  # type: ignore[assignment]
    queue._worker_error = None
    queue._last_error = None

    assert queue.drain(timeout=0.01) is False
    assert queue.last_error == "timed out enqueueing ledger drain barrier"


def test_writer_drain_reports_barrier_wait_timeout():
    from forecost.ledger.writer import LedgerWriteQueue

    class _IdleQueue:
        @staticmethod
        def put(item, timeout):
            return None

    queue = LedgerWriteQueue.__new__(LedgerWriteQueue)
    queue._queue = _IdleQueue()  # type: ignore[assignment]
    queue._thread = type("AliveThread", (), {"is_alive": lambda self: True})()  # type: ignore[assignment]
    queue._worker_error = None
    queue._last_error = None

    assert queue.drain(timeout=0.0) is False
    assert queue.last_error == "timed out waiting for ledger drain"


def test_writer_worker_exposes_startup_failure(tmp_path, monkeypatch):
    import threading

    from forecost.ledger.writer import LedgerWriteQueue

    queue = LedgerWriteQueue.__new__(LedgerWriteQueue)
    queue._ledger_path = tmp_path / "unopenable.db"
    queue._worker_error = None
    queue._last_error = None
    queue._ready = threading.Event()
    monkeypatch.setattr(queue, "_open_connection", lambda: (_ for _ in ()).throw(OSError("no db")))

    queue._worker()

    assert queue._ready.is_set()
    assert "no db" in (queue._worker_error or "")


def test_writer_worker_loop_closes_connection_on_sentinel():
    from forecost.ledger.writer import LedgerWriteQueue

    class _Connection:
        closed = False

        def close(self):
            self.closed = True

    connection = _Connection()
    queue = LedgerWriteQueue.__new__(LedgerWriteQueue)
    queue._queue = Queue()
    queue._queue.put_nowait(None)
    queue._worker_loop(connection)

    assert connection.closed is True


def test_writer_flushes_when_batch_reaches_limit(monkeypatch):
    import forecost.ledger.writer as writer_mod
    from forecost.adapters.base import PostingSpec
    from forecost.ledger.writer import LedgerWriteQueue, _WorkerState

    queue = LedgerWriteQueue.__new__(LedgerWriteQueue)
    state = _WorkerState(
        batch=[(_event(uid=f"queued-{index}"), []) for index in range(writer_mod._BATCH_SIZE - 1)]
    )
    flushed: list[int] = []
    monkeypatch.setattr(
        queue, "_flush_state", lambda worker_state, conn: flushed.append(len(worker_state.batch))
    )

    queue._handle_item(
        (_event(uid="threshold"), [PostingSpec("USD", 1.0, "pricing_table")]), state, object()
    )

    assert flushed == [writer_mod._BATCH_SIZE]


def test_writer_flush_retries_once_then_succeeds(tmp_path, monkeypatch):
    import forecost.ledger.writer as writer_mod
    from forecost.ledger.writer import LedgerWriteQueue

    attempts = 0

    def flaky_insert(conn, batch):
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise sqlite3.OperationalError("busy")
        return len(batch)

    queue = LedgerWriteQueue.__new__(LedgerWriteQueue)
    queue._ledger_path = tmp_path / "retry.db"
    queue._last_error = None
    monkeypatch.setattr(writer_mod, "_insert_batch", flaky_insert)
    monkeypatch.setattr(writer_mod.time, "sleep", lambda _seconds: None)

    assert queue._flush([(_event(uid="retry"), [])], object()) is True
    assert attempts == 2


def test_writer_close_durably_drains_every_accepted_event(tmp_path):
    from forecost.adapters.base import PostingSpec
    from forecost.ledger.writer import LedgerWriteQueue

    path = tmp_path / "close-drain.db"
    queue = LedgerWriteQueue(path)
    for index in range(250):
        assert queue.put(
            _event(uid=f"close-{index}"),
            [PostingSpec("USD", 1.0, "pricing_table", "test-v1")],
        )

    queue.close()

    with sqlite3.connect(path) as conn:
        assert conn.execute("SELECT COUNT(*) FROM usage_events").fetchone()[0] == 250
        assert conn.execute("SELECT COUNT(*) FROM postings").fetchone()[0] == 250
    assert queue.put(_event(uid="too-late"), []) is False
    assert queue.last_error == "ledger writer is closed"


def test_default_sink_raises_when_queue_refuses_event():
    from forecost.ledger.sink import DefaultLedgerSink
    from forecost.ledger.writer import LedgerWriteError

    class _RefusingQueue:
        last_error = "saturated"

        @staticmethod
        def put(event, postings):
            return False

    sink = DefaultLedgerSink.__new__(DefaultLedgerSink)
    sink._queue = _RefusingQueue()  # type: ignore[assignment]

    with pytest.raises(LedgerWriteError, match="saturated"):
        sink.emit(_event(uid="refused"))


def test_writer_drain_reports_database_and_recovery_failure(tmp_path, monkeypatch):
    import forecost.ledger.writer as writer_mod
    from forecost.adapters.base import PostingSpec
    from forecost.ledger.writer import LedgerWriteQueue

    queue = LedgerWriteQueue(ledger_path=tmp_path / "failure.db")
    monkeypatch.setattr(
        writer_mod,
        "_insert_batch",
        lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("db down")),
    )
    monkeypatch.setattr(
        writer_mod,
        "_spill_batch",
        lambda *args, **kwargs: (_ for _ in ()).throw(OSError("disk full")),
    )

    assert queue.put(_event(uid="lost"), [PostingSpec("USD", 1.0, "pricing_table")])
    assert queue.drain(timeout=2.0) is False
    assert "recovery spill failed" in (queue.last_error or "")


def test_default_sink_flush_surfaces_failed_drain():
    from forecost.ledger.sink import DefaultLedgerSink
    from forecost.ledger.writer import LedgerWriteError

    class _FailedDrainQueue:
        last_error = "recovery spill failed"

        @staticmethod
        def drain(timeout):
            return False

    sink = DefaultLedgerSink.__new__(DefaultLedgerSink)
    sink._queue = _FailedDrainQueue()  # type: ignore[assignment]

    with pytest.raises(LedgerWriteError, match="recovery spill failed"):
        sink.flush()


@pytest.mark.parametrize(
    "metadata",
    [
        {"prompt": "private user prompt"},
        {"entrypoint": {"nested": "payload"}},
        {"entrypoint": "x" * 257},
    ],
)
def test_sync_sink_rejects_unbounded_or_content_metadata(ledger_conn, metadata):
    sink = SyncLedgerSink(ledger_path=None)
    sink._conn = ledger_conn

    with pytest.raises(ValueError, match="metadata"):
        sink.emit(_event(uid="private-sync", metadata=metadata))

    assert ledger_conn.execute("SELECT COUNT(*) FROM usage_events").fetchone()[0] == 0


@pytest.mark.parametrize(
    "overrides",
    [
        {"model": "prompt-shaped model name with spaces"},
        {"tokens_in": -1},
        {"tokens_out": 1_000_000_000_001},
        {"reported_cost": Money(amount=float("nan"), currency="USD")},
        {"reported_cost": Money(amount=1.0, currency="secret currency text")},
        {"metadata": {"call_type": "prompt-shaped metadata value"}},
    ],
)
def test_sync_sink_rejects_invalid_or_content_shaped_event_fields(ledger_conn, overrides):
    sink = SyncLedgerSink(ledger_path=None)
    sink._conn = ledger_conn

    with pytest.raises(ValueError, match=r"model|tokens|reported cost|currency|metadata"):
        sink.emit(_event(uid="invalid-field", **overrides))

    assert ledger_conn.execute("SELECT COUNT(*) FROM usage_events").fetchone()[0] == 0


def test_async_sink_rejects_content_metadata_before_enqueue(tmp_path):
    from forecost.ledger.sink import DefaultLedgerSink

    sink = DefaultLedgerSink(ledger_path=tmp_path / "private-async.db")
    with pytest.raises(ValueError, match="metadata"):
        sink.emit(_event(uid="private-async", metadata={"completion": "secret"}))
    sink.flush(timeout=2.0)

    with sqlite3.connect(str(sink._queue._ledger_path)) as db:
        assert db.execute("SELECT COUNT(*) FROM usage_events").fetchone()[0] == 0


def test_sink_hashes_identifier_shaped_content_and_validates_postings(ledger_conn):
    """Identifier syntax is not a privacy boundary: opaque-looking caller text
    must never reach SQLite verbatim, including through recovery postings."""
    canary = "CANARY-9f2e-DO-NOT-PERSIST"
    sink = SyncLedgerSink(ledger_path=None)
    sink._conn = ledger_conn
    event = _event(
        uid=canary,
        source=canary,
        model=canary,
        provider=canary,
        session_uid=canary,
        run_id=canary,
        agent=canary,
        workspace_path=None,
        reported_cost=Money(amount=1.0, currency=canary),
        metadata={"call_type": canary},
    )

    assert sink.emit_with_postings(
        event,
        [PostingSpec(canary, 1.0, "pricing_table", canary)],
    )

    persisted = repr(
        {
            "sessions": [tuple(row) for row in ledger_conn.execute("SELECT * FROM sessions")],
            "usage_events": [
                tuple(row) for row in ledger_conn.execute("SELECT * FROM usage_events")
            ],
            "postings": [tuple(row) for row in ledger_conn.execute("SELECT * FROM postings")],
        }
    )
    assert canary not in persisted
    assert content_free_identifier("event", canary) in persisted
    assert content_free_identifier("session", canary) in persisted

    with pytest.raises(ValueError, match="posting amount"):
        sink.emit_with_postings(
            _event(uid="infinite-posting"),
            [PostingSpec("USD", float("inf"), "pricing_table", "bundled-2026-08")],
        )
    with pytest.raises(ValueError, match="posting basis"):
        sink.emit_with_postings(
            _event(uid="invalid-basis"),
            [PostingSpec("USD", 1.0, canary, "bundled-2026-08")],
        )
