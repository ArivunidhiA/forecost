import asyncio

import pytest

from forecost.tracker import get_session_summary, log_call, track, track_cost


@pytest.fixture(autouse=True)
def reset_session():
    import forecost.tracker as mod

    mod._session_stats = {}
    yield
    mod._session_stats = {}


def test_log_call_adds_to_session(monkeypatch):
    monkeypatch.setattr("forecost.tracker._find_project", lambda: None)
    log_call("gpt-4o", 1000, 500, provider="openai")
    log_call("gpt-4o-mini", 500, 200, provider="openai")
    summary = get_session_summary()
    assert summary["calls"] == 2
    assert summary["total_cost"] > 0
    assert summary["total_tokens"] == 2200
    assert "gpt-4o" in summary["by_model"]
    assert "gpt-4o-mini" in summary["by_model"]


def test_get_session_summary_returns_correct_totals(monkeypatch):
    monkeypatch.setattr("forecost.tracker._find_project", lambda: None)
    log_call("gpt-4o-mini", 1_000_000, 500_000, provider="openai")
    summary = get_session_summary()
    assert summary["calls"] == 1
    assert summary["total_tokens"] == 1_500_000
    expected_cost = (1_000_000 / 1_000_000) * 0.15 + (500_000 / 1_000_000) * 0.60
    assert abs(summary["total_cost"] - expected_cost) < 0.001
    assert summary["by_model"]["gpt-4o-mini"]["calls"] == 1


def test_track_cost_decorator_sync(monkeypatch):
    monkeypatch.setattr("forecost.tracker._find_project", lambda: None)

    @track_cost(provider="openai")
    def fake_call():
        return {
            "model": "gpt-4o",
            "usage": {"prompt_tokens": 100, "completion_tokens": 50},
        }

    result = fake_call()
    assert result["model"] == "gpt-4o"
    summary = get_session_summary()
    assert summary["calls"] == 1
    assert summary["total_cost"] > 0


def test_track_cost_decorator_async(monkeypatch):
    monkeypatch.setattr("forecost.tracker._find_project", lambda: None)

    @track_cost(provider="openai")
    async def fake_async_call():
        return {
            "model": "gpt-4o-mini",
            "usage": {"prompt_tokens": 200, "completion_tokens": 100},
        }

    result = asyncio.run(fake_async_call())
    assert result["model"] == "gpt-4o-mini"
    summary = get_session_summary()
    assert summary["calls"] == 1


def test_track_context_manager(monkeypatch):
    monkeypatch.setattr("forecost.tracker._find_project", lambda: None)
    with track() as t:
        t.log_call("gpt-4o", 500, 200, provider="openai")
    summary = get_session_summary()
    assert summary["calls"] == 1
    assert summary["total_tokens"] == 700


def test_auto_track_no_project_does_not_install(monkeypatch, capsys):
    import forecost.interceptor as imod
    import forecost.tracker as mod

    mod._clear_project_cache()
    monkeypatch.setattr("forecost.tracker._find_project", lambda: None)
    imod.uninstall()
    original_send = None
    import httpx

    original_send = httpx.Client.send
    mod.auto_track()
    assert httpx.Client.send is original_send
    stderr = capsys.readouterr().err
    assert "forecost" in stderr
