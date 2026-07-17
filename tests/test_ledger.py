from datetime import datetime, timezone

from forecost.adapters.base import Money, UsageEvent
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
    assert sess["session_uid"] == "sess-1"
    assert sess["agent"] == "test"


def test_sync_sink_adds_source_reported_posting_when_present(ledger_conn):
    sink = SyncLedgerSink(ledger_path=None)
    sink._conn = ledger_conn
    quota_cost = Money(amount=1.23, currency="QUOTA:anthropic-max20x:week")
    sink.emit(_event(uid="e2", reported_cost=quota_cost))
    currencies = {r["currency"] for r in ledger_conn.execute("SELECT currency FROM postings")}
    assert currencies == {"USD", "QUOTA:anthropic-max20x:week"}


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
    recovery = tmp_path / "recovery.jsonl"

    q = LedgerWriteQueue(ledger_path=path)
    # Force _insert_batch to always fail so the retry-then-spill path runs.
    import forecost.ledger.writer as writer_mod

    monkeypatch.setattr(
        writer_mod, "_insert_batch", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("db down"))
    )
    q._flush([(_event(uid="spill1"), [PostingSpec("USD", 1.0, "pricing_table")])], None)
    assert recovery.exists()
    line = recovery.read_text().strip()
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
