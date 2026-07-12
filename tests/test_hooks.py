"""End-to-end hook tests invoking the actual forecost-hook subprocess, exactly
as Claude Code would (stdin JSON in, stdout JSON / exit 0 out), plus direct
handler tests for granular coverage the subprocess path can't provide."""

import json
import subprocess
import sys

import pytest

import forecost.ledger.db as ledger_db
from forecost.hooks import handlers


@pytest.fixture
def hook_ledger(tmp_path, monkeypatch):
    path = tmp_path / "ledger.db"
    monkeypatch.setattr(ledger_db, "LEDGER_PATH", path)
    monkeypatch.setattr(ledger_db, "_conn", None)
    conn = ledger_db.get_ledger_db()
    yield conn
    ledger_db.reset_connection_for_tests()


def test_handler_session_start(hook_ledger):
    out = handlers.handle_session_start({"session_id": "s1", "cwd": "/tmp/p"})
    assert out == {}
    assert hook_ledger.execute("SELECT COUNT(*) FROM sessions").fetchone()[0] == 1


def test_handler_preflight_silent_on_cheap_turn(hook_ledger):
    out = handlers.handle_preflight(
        {"session_id": "s1", "cwd": "/tmp/p", "prompt_id": "p1", "prompt": "fix a typo"}
    )
    assert out == {}


def test_handler_preflight_speaks_on_scope_maximizer(hook_ledger):
    out = handlers.handle_preflight(
        {
            "session_id": "s1",
            "cwd": "/tmp/p",
            "prompt_id": "p1",
            "prompt": "refactor the entire auth module",
        }
    )
    assert "auth" in out["hookSpecificOutput"]["additionalContext"]
    # a shadow estimate row was written for calibration
    assert hook_ledger.execute("SELECT COUNT(*) FROM estimates").fetchone()[0] == 1


def test_handler_gate_allows_by_default(hook_ledger):
    out = handlers.handle_gate({"session_id": "s1", "cwd": "/tmp/p", "tool_name": "Bash"})
    assert out == {}


def test_handler_reconcile_ingests_from_transcript_path(hook_ledger, tmp_path):
    projects = tmp_path / "projects"
    proj = projects / "-tmp-p"
    proj.mkdir(parents=True)
    (proj / "s.jsonl").write_text(
        json.dumps(
            {
                "type": "assistant",
                "requestId": "r1",
                "uuid": "u1",
                "sessionId": "s",
                "cwd": "/tmp/p",
                "timestamp": "2026-07-01T00:00:00Z",
                "message": {
                    "model": "claude-sonnet-4-20250514",
                    "usage": {"input_tokens": 10, "output_tokens": 5},
                },
            }
        )
        + "\n"
    )
    # transcript_path -> parent.parent is the projects dir the adapter scans
    out = handlers.handle_reconcile({"transcript_path": str(proj / "s.jsonl")})
    assert out["ingested"] >= 1


def _run_hook(command, payload, env):
    proc = subprocess.run(  # noqa: S603 - fixed interpreter + module path, not user input
        [sys.executable, "-m", "forecost.hooks.fastpath", command],
        input=json.dumps(payload),
        capture_output=True,
        text=True,
        env=env,
        timeout=10,
    )
    return proc


def test_prompt_submit_silent_on_cheap_turn(tmp_path, monkeypatch):
    env = {**__import__("os").environ, "HOME": str(tmp_path)}
    proc = _run_hook(
        "prompt-submit",
        {"session_id": "s1", "cwd": str(tmp_path), "prompt_id": "p1", "prompt": "fix a typo"},
        env,
    )
    assert proc.returncode == 0
    assert proc.stdout.strip() == ""


def test_prompt_submit_speaks_on_fanout(tmp_path):
    env = {**__import__("os").environ, "HOME": str(tmp_path)}
    proc = _run_hook(
        "prompt-submit",
        {
            "session_id": "s1",
            "cwd": str(tmp_path),
            "prompt_id": "p1",
            "prompt": "spawn parallel subagents to review everything",
        },
        env,
    )
    assert proc.returncode == 0
    out = json.loads(proc.stdout)
    assert "fanout-batch" in out["hookSpecificOutput"]["additionalContext"]


def test_malformed_stdin_fails_open(tmp_path):
    env = {**__import__("os").environ, "HOME": str(tmp_path)}
    proc = subprocess.run(
        [sys.executable, "-m", "forecost.hooks.fastpath", "prompt-submit"],
        input="not json {{{",
        capture_output=True,
        text=True,
        env=env,
        timeout=10,
    )
    assert proc.returncode == 0


def test_unknown_command_fails_open(tmp_path):
    env = {**__import__("os").environ, "HOME": str(tmp_path)}
    proc = _run_hook("bogus-command", {}, env)
    assert proc.returncode == 0


def test_gate_denies_over_hard_limit(tmp_path):
    forecost_home = tmp_path / "home"
    forecost_home.mkdir()
    (forecost_home / ".forecost").mkdir()
    (forecost_home / ".forecost" / "policy.toml").write_text(
        '[[policy.rules]]\nid="cap"\nscope="session"\ncurrency="USD"\n'
        'soft_limit=0.001\nhard_limit=0.002\naction="deny"\n'
    )
    env = {**__import__("os").environ, "HOME": str(forecost_home)}
    cwd = str(tmp_path / "proj")

    # Establish the session, then inject spend directly via the ledger.
    _run_hook("session-start", {"session_id": "sd1", "cwd": cwd}, env)

    sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parents[1]))
    import importlib
    import os as _os

    old_home = _os.environ.get("HOME")
    _os.environ["HOME"] = str(forecost_home)
    try:
        import forecost.ledger.db as ledger_db

        importlib.reload(ledger_db)
        from datetime import datetime, timezone

        from forecost.adapters.base import UsageEvent
        from forecost.ledger.sink import SyncLedgerSink

        sink = SyncLedgerSink()
        sink.emit(
            UsageEvent(
                event_uid="deny-test",
                ts=datetime.now(timezone.utc),
                source="test",
                model="claude-opus-4-8",
                session_uid="sd1",
                tokens_in=1_000_000,
                tokens_out=100_000,
            )
        )
    finally:
        if old_home is not None:
            _os.environ["HOME"] = old_home

    proc = _run_hook("pre-tool", {"session_id": "sd1", "cwd": cwd, "tool_name": "Bash"}, env)
    assert proc.returncode == 0
    out = json.loads(proc.stdout)
    assert out["hookSpecificOutput"]["permissionDecision"] == "deny"
