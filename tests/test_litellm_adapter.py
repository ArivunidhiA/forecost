"""Tests for the LiteLLM adapter, run against the REAL litellm CustomLogger base
class (skipped automatically when litellm isn't installed)."""

import asyncio
from types import SimpleNamespace

import pytest

litellm = pytest.importorskip("litellm")

from forecost.adapters.litellm_hook import ForecostLogger  # noqa: E402


def _run(coro):
    return asyncio.run(coro)


def test_pre_call_allows_when_no_policy(tmp_path, ledger_conn, monkeypatch):
    import forecost.adapters.litellm_hook as hook_mod

    monkeypatch.setattr(hook_mod, "get_ledger_db", lambda _path=None: ledger_conn)
    logger = ForecostLogger(policy_path=tmp_path / "nonexistent.toml")

    data = {"model": "gpt-4o", "messages": []}
    result = _run(logger.async_pre_call_hook(None, None, data, "acompletion"))
    assert result == data  # allowed, data passed through unchanged


def test_pre_call_denies_over_budget(tmp_path, ledger_conn, monkeypatch):
    import forecost.adapters.litellm_hook as hook_mod

    monkeypatch.setattr(hook_mod, "get_ledger_db", lambda _path=None: ledger_conn)

    # Put spend in the ledger, then a policy that denies above it.
    from datetime import datetime, timezone

    from forecost.adapters.base import UsageEvent
    from forecost.ledger.sink import SyncLedgerSink

    sink = SyncLedgerSink(ledger_path=None)
    sink._conn = ledger_conn
    sink.emit(
        UsageEvent(
            event_uid="pre",
            ts=datetime.now(timezone.utc),
            source="test",
            model="claude-opus-4-8",
            tokens_in=0,
            tokens_out=1_000_000,
        )
    )

    policy_file = tmp_path / "policy.toml"
    policy_file.write_text(
        '[[policy.rules]]\nid="day-cap"\nscope="day"\ncurrency="USD"\n'
        'hard_limit=1.0\naction="deny"\n'
    )
    logger = ForecostLogger(policy_path=policy_file)
    result = _run(logger.async_pre_call_hook(None, None, {"model": "x"}, "acompletion"))
    assert isinstance(result, str)
    assert "forecost budget gate" in result


def test_pre_call_fails_open_on_internal_error(tmp_path, monkeypatch):
    import forecost.adapters.litellm_hook as hook_mod

    def _boom(_path=None):
        raise RuntimeError("ledger unavailable")

    monkeypatch.setattr(hook_mod, "get_ledger_db", _boom)
    logger = ForecostLogger(policy_path=tmp_path / "policy.toml")
    data = {"model": "x"}
    result = _run(logger.async_pre_call_hook(None, None, data, "acompletion"))
    assert result == data  # fail-open: gateway keeps working


def test_success_event_lands_in_ledger_with_source_reported_cost(ledger_conn, monkeypatch):
    import forecost.adapters.litellm_hook as hook_mod

    monkeypatch.setattr(hook_mod, "get_ledger_db", lambda _path=None: ledger_conn)
    logger = ForecostLogger()
    logger._sink = __import__("forecost.ledger.sink", fromlist=["SyncLedgerSink"]).SyncLedgerSink(
        ledger_path=None
    )
    logger._sink._conn = ledger_conn

    kwargs = {
        "model": "gpt-4o",
        "litellm_call_id": "call-123",
        "response_cost": 0.0042,
        "custom_llm_provider": "openai",
        "call_type": "acompletion",
        "litellm_params": {"metadata": {}},
    }
    response_obj = SimpleNamespace(usage=SimpleNamespace(prompt_tokens=100, completion_tokens=50))
    _run(logger.async_log_success_event(kwargs, response_obj, None, None))

    ev = ledger_conn.execute("SELECT * FROM usage_events WHERE source='litellm'").fetchone()
    assert ev is not None
    assert ev["model"] == "gpt-4o"
    assert ev["tokens_in"] == 100
    currencies = {
        (r["currency"], r["basis"])
        for r in ledger_conn.execute(
            "SELECT p.currency, p.basis FROM postings p "
            "JOIN usage_events e ON e.id=p.event_id WHERE e.source='litellm'"
        )
    }
    assert ("USD", "pricing_table") in currencies
    assert ("USD", "source_reported") in currencies


def test_success_event_never_raises(ledger_conn, monkeypatch):

    def _boom(_path=None):
        raise RuntimeError("boom")

    logger = ForecostLogger()
    monkeypatch.setattr(logger, "_get_sink", _boom)
    # Malformed everything; must not raise (gateway safety)
    _run(logger.async_log_success_event({}, None, None, None))
