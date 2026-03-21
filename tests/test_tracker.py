import pytest

from llmcast.tracker import get_session_summary, log_call


@pytest.fixture(autouse=True)
def reset_session():
    import llmcast.tracker as mod

    mod._session_stats = {}
    yield
    mod._session_stats = {}


def test_log_call_adds_to_session(monkeypatch):
    monkeypatch.setattr("llmcast.tracker._find_project", lambda: None)
    log_call("gpt-4o", 1000, 500, provider="openai")
    log_call("gpt-4o-mini", 500, 200, provider="openai")
    summary = get_session_summary()
    assert summary["calls"] == 2
    assert summary["total_cost"] > 0
    assert summary["total_tokens"] == 2200
    assert "gpt-4o" in summary["by_model"]
    assert "gpt-4o-mini" in summary["by_model"]


def test_get_session_summary_returns_correct_totals(monkeypatch):
    monkeypatch.setattr("llmcast.tracker._find_project", lambda: None)
    log_call("gpt-4o-mini", 1_000_000, 500_000, provider="openai")
    summary = get_session_summary()
    assert summary["calls"] == 1
    assert summary["total_tokens"] == 1_500_000
    expected_cost = (1_000_000 / 1_000_000) * 0.15 + (500_000 / 1_000_000) * 0.60
    assert abs(summary["total_cost"] - expected_cost) < 0.001
    assert summary["by_model"]["gpt-4o-mini"]["calls"] == 1
