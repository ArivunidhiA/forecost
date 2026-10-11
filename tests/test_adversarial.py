# pyright: reportArgumentType=false
"""Adversarial properties: fuzzed inputs must never crash, leak content, or corrupt totals."""

from __future__ import annotations

import io
import json
import math
import os
import sqlite3
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

CANARY = "ADVERSARIAL-CANARY-5c1e-DO-NOT-PERSIST"
FUZZ = settings(
    max_examples=int(os.environ.get("FORECOST_FUZZ_EXAMPLES", "60")),
    deadline=None,
    suppress_health_check=[HealthCheck.function_scoped_fixture, HealthCheck.too_slow],
)

_scalar = st.one_of(
    st.none(),
    st.booleans(),
    st.integers(min_value=-(10**12), max_value=10**12),
    st.floats(allow_nan=True, allow_infinity=True),
    st.text(max_size=40),
)
_json = st.recursive(
    _scalar,
    lambda c: st.one_of(
        st.lists(c, max_size=4), st.dictionaries(st.text(max_size=8), c, max_size=4)
    ),
    max_leaves=12,
)
_usage = st.fixed_dictionaries(
    {},
    optional={
        "input_tokens": _scalar,
        "output_tokens": _scalar,
        "cache_read_input_tokens": _scalar,
        "cache_creation_input_tokens": _scalar,
    },
)
_record = st.fixed_dictionaries(
    {"type": st.sampled_from(["user", "assistant", "system", "summary", "junk"])},
    optional={
        "requestId": st.one_of(st.text(max_size=24), st.none(), st.integers()),
        "uuid": st.text(max_size=24),
        "promptId": st.text(max_size=24),
        "sessionId": st.text(max_size=24),
        "cwd": st.one_of(st.text(max_size=60), st.none(), st.integers()),
        "timestamp": st.one_of(st.text(max_size=30), st.none(), st.just("2026-10-01T00:00:00Z")),
        "isMeta": st.booleans(),
        "message": st.one_of(
            _json,
            st.fixed_dictionaries(
                {"content": st.just(f"secret {CANARY}")},
                optional={
                    "model": st.one_of(
                        st.text(max_size=30), st.just("claude-sonnet-4-5"), st.none()
                    ),
                    "usage": st.one_of(_usage, _json),
                },
            ),
        ),
    },
)
_line = st.one_of(
    _record.map(json.dumps),
    st.text(max_size=80),
    st.binary(max_size=60).map(lambda b: b.decode("latin-1")),
)


def _all_text(db_path: Path, home: Path) -> str:
    chunks = []
    conn = sqlite3.connect(db_path)
    try:
        chunks.append("\n".join(conn.iterdump()))
    finally:
        conn.close()
    for path in home.rglob("*"):
        if path.is_file() and path.resolve() != db_path.resolve():
            chunks.append(path.read_bytes().decode("latin-1"))
    return "\n".join(chunks)


@FUZZ
@given(lines=st.lists(_line, min_size=1, max_size=12))
def test_fuzzed_transcripts_never_crash_or_leak_content(lines, monkeypatch):
    import forecost.ledger.db as ledger_db
    from forecost.adapters.claude_code import ClaudeCodeAdapter
    from forecost.ledger.sink import SyncLedgerSink
    from forecost.ledger.state_store import LedgerIngestStateStore

    with tempfile.TemporaryDirectory() as raw:
        home = Path(raw)
        monkeypatch.setenv("FORECOST_HOME", str(home))
        db_path = home / "ledger.db"
        monkeypatch.setattr(ledger_db, "LEDGER_PATH", db_path)
        monkeypatch.setattr(ledger_db, "_conn", None)
        conn = ledger_db.get_ledger_db()
        try:
            claude = Path(tempfile.mkdtemp(prefix="claude-"))
            project = claude / "projects" / "-p"
            project.mkdir(parents=True)
            (project / "s.jsonl").write_text(
                "\n".join(lines) + "\n", encoding="utf-8", errors="replace"
            )
            sink = SyncLedgerSink(ledger_path=None)
            sink._conn = conn
            adapter = ClaudeCodeAdapter(claude_dir=claude / "projects")
            adapter.poll(LedgerIngestStateStore(conn), sink)  # must not raise
            for (amount,) in conn.execute("SELECT amount FROM postings"):
                assert math.isfinite(amount)
                assert amount >= 0
            assert CANARY not in _all_text(db_path, home)
        finally:
            ledger_db.reset_connection_for_tests()


@FUZZ
@given(
    payload=_json, command=st.sampled_from(["session-start", "prompt-submit", "pre-tool", "stop"])
)
def test_hooks_fail_open_for_any_payload(payload, command, monkeypatch, tmp_path):
    from forecost.hooks import fastpath

    monkeypatch.setenv("FORECOST_HOME", str(tmp_path))
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(tmp_path / "claude"))
    monkeypatch.setattr(sys, "argv", ["forecost-hook", command])
    body = json.dumps(payload, allow_nan=True)
    monkeypatch.setattr(sys, "stdin", io.StringIO(body))
    with pytest.raises(SystemExit) as exit_info:
        fastpath.main()
    assert exit_info.value.code == 0


@FUZZ
@given(garbage=st.text(max_size=200), command=st.sampled_from(["session-start", "stop", "bogus"]))
def test_hooks_fail_open_for_non_json_stdin(garbage, command, monkeypatch, tmp_path):
    from forecost.hooks import fastpath

    monkeypatch.setenv("FORECOST_HOME", str(tmp_path))
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(tmp_path / "claude"))
    monkeypatch.setattr(sys, "argv", ["forecost-hook", command])
    monkeypatch.setattr(sys, "stdin", io.StringIO(garbage))
    with pytest.raises(SystemExit) as exit_info:
        fastpath.main()
    assert exit_info.value.code == 0


_MODELS = ["gpt-4o", "claude-opus-4-8", "o3", "gemini-2.5-flash", "unknown-model-xyz"]


@FUZZ
@given(
    model=st.sampled_from(_MODELS),
    a=st.integers(0, 50_000),
    b=st.integers(0, 50_000),
    c=st.integers(0, 50_000),
    d=st.integers(0, 50_000),
)
def test_cost_is_additive_across_calls_below_context_tiers(model, a, b, c, d):
    from forecost.pricing import calculate_cost

    whole = calculate_cost(model, a + b, c + d)
    parts = calculate_cost(model, a, c) + calculate_cost(model, b, d)
    assert math.isclose(whole, parts, rel_tol=1e-9, abs_tol=1e-12)


@FUZZ
@given(
    model=st.sampled_from([*_MODELS, "claude-haiku-5-5", "gemini-2.5-pro"]),
    tokens=st.integers(-(10**9), 10**12),
    out=st.integers(-(10**9), 10**12),
    read=st.integers(-(10**9), 10**12),
    write=st.integers(-(10**9), 10**12),
)
def test_cost_is_always_finite_and_non_negative(model, tokens, out, read, write):
    from forecost.pricing import calculate_cost

    cost = calculate_cost(model, tokens, out, read, write)
    assert math.isfinite(cost)
    assert cost >= 0


@FUZZ
@given(
    rows=st.lists(
        st.tuples(st.integers(0, 6), st.integers(0, 5000), st.integers(0, 5000)),
        min_size=1,
        max_size=14,
    ),
    seed=st.integers(0, 10_000),
)
def test_ledger_totals_are_order_and_duplicate_invariant(rows, seed, monkeypatch):
    import random

    import forecost.ledger.db as ledger_db
    from forecost.adapters.base import UsageEvent
    from forecost.ledger.sink import SyncLedgerSink

    base = datetime(2026, 10, 1, tzinfo=timezone.utc)
    events = [
        UsageEvent(
            event_uid=f"adv-{uid}",
            ts=base + timedelta(minutes=uid),
            source="fuzz",
            model="claude-sonnet-4-5",
            tokens_in=tin,
            tokens_out=tout,
        )
        for uid, tin, tout in rows
    ]

    def total(sequence) -> tuple[int, float]:
        with tempfile.TemporaryDirectory() as raw:
            path = Path(raw) / "ledger.db"
            monkeypatch.setattr(ledger_db, "LEDGER_PATH", path)
            monkeypatch.setattr(ledger_db, "_conn", None)
            conn = ledger_db.get_ledger_db()
            try:
                sink = SyncLedgerSink(ledger_path=None)
                sink._conn = conn
                for event in sequence:
                    sink.emit(event)
                count = conn.execute("SELECT COUNT(*) FROM usage_events").fetchone()[0]
                amount = conn.execute(
                    "SELECT COALESCE(SUM(amount),0) FROM postings WHERE basis='pricing_table'"
                ).fetchone()[0]
                return count, round(amount, 9)
            finally:
                ledger_db.reset_connection_for_tests()

    # Collapse same-uid events the way the ledger must: first write wins.
    first_by_uid = {}
    for event in events:
        first_by_uid.setdefault(event.event_uid, event)
    expected_count = len(first_by_uid)
    shuffled = list(events) + list(events)  # duplicates
    random.Random(seed).shuffle(shuffled)
    count, amount = total(shuffled)
    assert count == expected_count
    ordered = total(list(first_by_uid.values()))
    # Order/duplicates may change WHICH same-uid variant wins, never the number of events.
    assert ordered[0] == count
    assert math.isfinite(amount)


def test_stop_hook_without_transcript_path_is_bounded(tmp_path, monkeypatch):
    """A payload with no transcript_path must not trigger a lifetime scan (red-team finding)."""
    from forecost.hooks import handlers

    claude = tmp_path / "claude" / "projects" / "-p"
    claude.mkdir(parents=True)
    for index in range(handlers._MAX_FALLBACK_TRANSCRIPTS + 15):
        (claude / f"s{index}.jsonl").write_text("{}\n")
    chosen = handlers._most_recent_transcripts(tmp_path / "claude" / "projects")
    assert len(chosen) == handlers._MAX_FALLBACK_TRANSCRIPTS
    assert handlers._most_recent_transcripts(tmp_path / "does-not-exist") == []


def test_fallback_transcript_listing_tolerates_filesystem_errors(tmp_path, monkeypatch):
    from forecost.hooks import handlers

    root = tmp_path / "projects" / "-p"
    root.mkdir(parents=True)
    good = root / "good.jsonl"
    good.write_text("{}\n")
    (root / "vanishing.jsonl").write_text("{}\n")
    real_stat = Path.stat

    def flaky_stat(self, *args, **kwargs):
        if self.name == "vanishing.jsonl":
            raise OSError("raced away")
        return real_stat(self, *args, **kwargs)

    monkeypatch.setattr(Path, "stat", flaky_stat)
    assert handlers._most_recent_transcripts(tmp_path / "projects") == [good]

    def boom(self, pattern):
        raise PermissionError("denied")

    monkeypatch.setattr(Path, "rglob", boom)
    assert handlers._most_recent_transcripts(tmp_path / "projects") == []


def test_fallback_listing_is_newest_first_and_skips_symlinks_and_dirs(tmp_path):
    import os

    from forecost.hooks import handlers

    root = tmp_path / "projects" / "-p"
    root.mkdir(parents=True)
    paths = []
    for index in range(5):
        path = root / f"s{index}.jsonl"
        path.write_text("{}\\n")
        os.utime(path, (1_000 + index, 1_000 + index))
        paths.append(path)
    (root / "dir.jsonl").mkdir()
    (root / "link.jsonl").symlink_to(paths[0])
    chosen = handlers._most_recent_transcripts(tmp_path / "projects")
    assert chosen == list(reversed(paths))
    assert handlers._MAX_FALLBACK_TRANSCRIPTS == 20
