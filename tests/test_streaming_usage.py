"""Claude Code logs one API response as several records with growing usage (streaming).

Regression for the red-team finding that first-record-wins undercounted output tokens by ~73% on
real sessions: the early records carry zero/partial output tokens, a later record has the final.
"""

from __future__ import annotations

import itertools
import json
from pathlib import Path

import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from forecost.adapters.claude_code import ClaudeCodeAdapter
from forecost.ledger.sink import SyncLedgerSink
from forecost.ledger.state_store import LedgerIngestStateStore


def _record(request_id: str, block: int, usage: dict[str, int], model="claude-sonnet-4-5") -> dict:
    return {
        "type": "assistant",
        "requestId": request_id,
        "uuid": f"{request_id}-{block}",
        "sessionId": "s1",
        "cwd": "/x",
        "timestamp": "2026-10-01T00:00:00Z",
        "message": {"model": model, "usage": usage},
    }


def _usage(i=0, o=0, r=0, w=0) -> dict[str, int]:
    return {
        "input_tokens": i,
        "output_tokens": o,
        "cache_read_input_tokens": r,
        "cache_creation_input_tokens": w,
    }


def _write(path: Path, records: list[dict], *, append: bool = False) -> None:
    with path.open("a" if append else "w", encoding="utf-8") as handle:
        for rec in records:
            handle.write(json.dumps(rec) + "\n")


def _ingest(tmp_path, ledger_conn) -> None:
    sink = SyncLedgerSink(ledger_path=None)
    sink._conn = ledger_conn
    ClaudeCodeAdapter(claude_dir=tmp_path).poll(LedgerIngestStateStore(ledger_conn), sink)


def _tokens(conn) -> list[tuple[int, int, int, int]]:
    rows = conn.execute(
        "SELECT tokens_in, tokens_out, tokens_cache_read, tokens_cache_write FROM usage_events"
    ).fetchall()
    return [tuple(r) for r in rows]


def _priced(conn) -> float:
    return conn.execute(
        "SELECT COALESCE(SUM(amount),0) FROM postings WHERE basis='pricing_table'"
    ).fetchone()[0]


def test_partial_then_final_record_counts_the_final_usage(tmp_path, ledger_conn):
    project = tmp_path / "-p"
    project.mkdir()
    _write(
        project / "s.jsonl",
        [
            _record("r1", 0, _usage(2, 0, 946_031, 7_917)),  # streaming partial: no output yet
            _record("r1", 1, _usage(2, 5, 946_031, 7_917)),
            _record("r1", 2, _usage(2, 13_245, 946_031, 7_917)),  # final
        ],
    )
    _ingest(tmp_path, ledger_conn)
    assert _tokens(ledger_conn) == [(2, 13_245, 946_031, 7_917)]
    # Prompt (2 + 946,031 + 7,917 tokens) is over 200k, so Sonnet 4.5's long-context tier applies.
    expected = (2 * 6.0 + 13_245 * 22.5 + 946_031 * 0.6 + 7_917 * 7.5) / 1e6
    assert _priced(ledger_conn) == pytest.approx(expected)


def test_final_arriving_in_a_later_poll_upgrades_the_stored_event(tmp_path, ledger_conn):
    project = tmp_path / "-p"
    project.mkdir()
    session = project / "s.jsonl"
    _write(session, [_record("r1", 0, _usage(2, 0, 100, 10))])
    _ingest(tmp_path, ledger_conn)
    assert _tokens(ledger_conn) == [(2, 0, 100, 10)]
    before = _priced(ledger_conn)

    _write(session, [_record("r1", 1, _usage(2, 900, 100, 10))], append=True)
    _ingest(tmp_path, ledger_conn)
    assert _tokens(ledger_conn) == [(2, 900, 100, 10)]
    assert _priced(ledger_conn) > before
    assert ledger_conn.execute("SELECT COUNT(*) FROM usage_events").fetchone()[0] == 1
    assert ledger_conn.execute("SELECT COUNT(*) FROM postings").fetchone()[0] == 1  # replaced

    _ingest(tmp_path, ledger_conn)  # idempotent replay changes nothing
    assert _tokens(ledger_conn) == [(2, 900, 100, 10)]


def test_a_smaller_late_record_never_lowers_the_count(tmp_path, ledger_conn):
    project = tmp_path / "-p"
    project.mkdir()
    _write(
        project / "s.jsonl",
        [_record("r1", 0, _usage(2, 900, 100, 10)), _record("r1", 1, _usage(2, 3, 100, 10))],
    )
    _ingest(tmp_path, ledger_conn)
    assert _tokens(ledger_conn) == [(2, 900, 100, 10)]


@settings(
    max_examples=40, deadline=None, suppress_health_check=[HealthCheck.function_scoped_fixture]
)
@given(
    usages=st.lists(st.tuples(*[st.integers(0, 5000)] * 4), min_size=1, max_size=5),
    order=st.integers(0, 119),
)
def test_final_count_is_the_per_field_max_in_any_record_order(
    usages, order, tmp_path_factory, ledger_conn
):
    tmp_path = tmp_path_factory.mktemp("stream")
    project = tmp_path / "-p"
    project.mkdir()
    perms = list(itertools.permutations(range(len(usages))))
    chosen = perms[order % len(perms)]
    records = [_record("rq", i, _usage(*usages[j])) for i, j in enumerate(chosen)]
    _write(project / "s.jsonl", records)
    ledger_conn.execute("DELETE FROM postings")
    ledger_conn.execute("DELETE FROM usage_events")
    ledger_conn.commit()
    _ingest(tmp_path, ledger_conn)
    expected = tuple(max(u[k] for u in usages) for k in range(4))
    rows = _tokens(ledger_conn)
    if any(expected):
        assert rows == [expected]
    else:
        assert rows == [] or rows == [(0, 0, 0, 0)]


def test_causal_receipt_meters_use_the_final_streamed_usage(tmp_path, ledger_conn):
    from forecost.adapters.claude_code import ingest_causal_paths

    project = tmp_path / "-p"
    project.mkdir()
    session = project / "s.jsonl"
    _write(
        session,
        [
            _record("r1", 0, _usage(2, 0, 100, 10)),
            _record("r1", 1, _usage(2, 5, 100, 10)),
            _record("r1", 2, _usage(2, 900, 100, 10)),
        ],
    )
    inserted = ingest_causal_paths([session], LedgerIngestStateStore(ledger_conn), ledger_conn)
    assert inserted >= 5  # one span + four meters
    meters = {
        row[0]: row[1] // 1_000_000
        for row in ledger_conn.execute("SELECT meter_name, quantity_micros FROM meter_facts")
    }
    assert meters == {
        "tokens.input": 2,
        "tokens.output": 900,
        "tokens.cache_read": 100,
        "tokens.cache_write": 10,
    }
    spans = ledger_conn.execute("SELECT COUNT(*) FROM causal_spans").fetchone()[0]
    assert spans == 1


# ---- direct unit pins (mutation-testing driven) -----------------------------------------------


def test_tier_threshold_sums_all_three_prompt_token_classes():
    from forecost.pricing import calculate_cost

    # Only cache_write pushes the prompt over 100k; subtracting it instead would stay below.
    assert (
        calculate_cost("claude-haiku-5-5", 60_000, 0, 0, 40_001)
        > calculate_cost("claude-haiku-5-5", 60_000, 0, 0, 39_999) * 3
    )


def _event(uid="evt-1", **tokens):
    from datetime import datetime, timezone

    from forecost.adapters.base import UsageEvent, normalize_usage_event

    return normalize_usage_event(
        UsageEvent(
            event_uid=uid,
            ts=datetime(2026, 10, 1, tzinfo=timezone.utc),
            source="unit",
            model="claude-sonnet-4-5",
            **tokens,
        )
    )


def test_merge_cumulative_usage_return_contract(ledger_conn):
    from forecost.ledger.sink import SyncLedgerSink, _price_event
    from forecost.ledger.writer import merge_cumulative_usage

    sink = SyncLedgerSink(ledger_path=None)
    sink._conn = ledger_conn
    assert merge_cumulative_usage(ledger_conn, _event(tokens_in=1), _price_event) is None
    assert sink.emit(_event(tokens_in=10, tokens_out=5)) is True
    assert (
        merge_cumulative_usage(ledger_conn, _event(tokens_in=10, tokens_out=5), _price_event)
        is False
    )
    assert (
        merge_cumulative_usage(ledger_conn, _event(tokens_in=3, tokens_out=1), _price_event)
        is False
    )
    assert (
        merge_cumulative_usage(ledger_conn, _event(tokens_in=10, tokens_out=9), _price_event)
        is True
    )
    row = ledger_conn.execute("SELECT tokens_in, tokens_out FROM usage_events").fetchone()
    assert tuple(row) == (10, 9)


def test_merge_is_per_field_and_works_inside_an_open_transaction(ledger_conn):
    from forecost.ledger.sink import SyncLedgerSink, _price_event
    from forecost.ledger.writer import merge_cumulative_usage

    SyncLedgerSink(ledger_path=None)._conn = ledger_conn
    sink = SyncLedgerSink(ledger_path=None)
    sink._conn = ledger_conn
    sink.emit(_event(tokens_in=10, tokens_out=1, tokens_cache_read=7))
    ledger_conn.execute("BEGIN")
    assert ledger_conn.in_transaction
    changed = merge_cumulative_usage(
        ledger_conn, _event(tokens_in=2, tokens_out=50, tokens_cache_read=1), _price_event
    )
    assert changed is True
    ledger_conn.commit()
    row = ledger_conn.execute(
        "SELECT tokens_in, tokens_out, tokens_cache_read FROM usage_events"
    ).fetchone()
    assert tuple(row) == (10, 50, 7)  # each field keeps its own maximum


def test_merge_failure_rolls_back_tokens_and_postings(ledger_conn):
    from forecost.ledger.sink import SyncLedgerSink, _price_event
    from forecost.ledger.writer import merge_cumulative_usage

    sink = SyncLedgerSink(ledger_path=None)
    sink._conn = ledger_conn
    sink.emit(_event(tokens_in=10, tokens_out=1))

    def boom(_event):
        raise RuntimeError("pricing failed")

    with pytest.raises(RuntimeError):
        merge_cumulative_usage(ledger_conn, _event(tokens_in=10, tokens_out=99), boom)
    assert tuple(ledger_conn.execute("SELECT tokens_out FROM usage_events").fetchone()) == (1,)
    assert _price_event(_event(tokens_in=10, tokens_out=1))  # pricing itself still fine


def test_merge_usage_helper_edge_cases():
    from forecost.adapters.claude_code import _merge_usage

    base = {"message": {"model": "m", "usage": {"input_tokens": 1, "output_tokens": 0}}, "k": 1}
    later = {"message": {"usage": {"output_tokens": 9, "input_tokens": 0}}}
    merged = _merge_usage(base, later)
    assert merged["message"]["usage"] == {"input_tokens": 1, "output_tokens": 9}
    assert merged["k"] == 1
    assert merged["message"]["model"] == "m"

    # bool / non-int / missing counters are ignored; missing old counter is filled
    assert (
        _merge_usage(base, {"message": {"usage": {"output_tokens": True}}})["message"]["usage"][
            "output_tokens"
        ]
        == 0
    )
    assert (
        _merge_usage(base, {"message": {"usage": {"output_tokens": "9"}}})["message"]["usage"][
            "output_tokens"
        ]
        == 0
    )
    filled = _merge_usage(
        {"message": {"usage": {}}}, {"message": {"usage": {"cache_read_input_tokens": 4}}}
    )
    assert filled["message"]["usage"] == {"cache_read_input_tokens": 4}
    # a first record without usage takes the later one wholesale
    no_usage = _merge_usage(
        {"message": {"model": "m"}}, {"message": {"usage": {"input_tokens": 2}}}
    )
    assert no_usage["message"]["usage"] == {"input_tokens": 2}
    # model missing/invalid on first is taken from later (when later carries usage)
    usage = {"usage": {"input_tokens": 1}}
    late = {"message": {"model": "late", **usage}}
    assert _merge_usage({"message": {}}, late)["message"]["model"] == "late"
    assert _merge_usage({"message": {"model": 5}}, late)["message"]["model"] == "late"
    # wrong shapes return the first record untouched
    assert _merge_usage({"message": {}}, {"message": {"model": "late"}}) == {"message": {}}
    assert _merge_usage({"message": "x"}, {"message": {}}) == {"message": "x"}
    assert _merge_usage({"message": {}}, {"message": "x"}) == {"message": {}}


@pytest.mark.parametrize("nested", [False, True])
def test_merge_rolls_back_when_the_write_fails_midway(ledger_conn, monkeypatch, nested):
    import forecost.ledger.writer as writer
    from forecost.ledger.sink import SyncLedgerSink, _price_event

    sink = SyncLedgerSink(ledger_path=None)
    sink._conn = ledger_conn
    sink.emit(_event(tokens_in=10, tokens_out=1))

    def failing_write(conn, event_id, tokens, postings):
        conn.execute("UPDATE usage_events SET tokens_out = 12345 WHERE id = ?", (event_id,))
        raise RuntimeError("disk full")

    monkeypatch.setattr(writer, "_write_merge", failing_write)
    if nested:
        ledger_conn.execute("BEGIN")
    with pytest.raises(RuntimeError, match="disk full"):
        writer.merge_cumulative_usage(
            ledger_conn, _event(tokens_in=10, tokens_out=99), _price_event
        )
    if nested:
        ledger_conn.rollback()
    assert tuple(ledger_conn.execute("SELECT tokens_out FROM usage_events").fetchone()) == (1,)
    assert not ledger_conn.in_transaction


def test_causal_ingest_survives_an_unreadable_transcript(tmp_path, ledger_conn, monkeypatch):
    import forecost.adapters.claude_code as adapter

    session = tmp_path / "s.jsonl"
    session.write_text("{}\n")

    def unreadable(*_args, **_kwargs):
        raise OSError("permission denied")

    monkeypatch.setattr(adapter, "_ingest_causal_path", unreadable)
    inserted = adapter.ingest_causal_paths(
        [session], LedgerIngestStateStore(ledger_conn), ledger_conn
    )
    assert inserted == 0
