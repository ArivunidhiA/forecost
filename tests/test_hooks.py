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
    # A stop hook must ingest only this session, not every historical sibling.
    (proj / "unrelated.jsonl").write_text(
        json.dumps(
            {
                "type": "assistant",
                "requestId": "unrelated",
                "timestamp": "2026-07-01T00:00:00Z",
                "message": {
                    "model": "claude-sonnet-4-20250514",
                    "usage": {"input_tokens": 99, "output_tokens": 9},
                },
            }
        )
        + "\n"
    )
    out = handlers.handle_reconcile({"transcript_path": str(proj / "s.jsonl")})
    assert out["ingested"] == 1
    assert hook_ledger.execute("SELECT COUNT(*) FROM usage_events").fetchone()[0] == 1


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


def _fc_env(fc_home) -> dict:
    """A subprocess env with FORECOST_HOME set — relocates the ledger + policy to a
    tmp dir on every platform (unlike HOME, which Path.home() ignores on Windows)."""
    return {**__import__("os").environ, "FORECOST_HOME": str(fc_home)}


def test_prompt_submit_silent_on_cheap_turn(tmp_path):
    proc = _run_hook(
        "prompt-submit",
        {"session_id": "s1", "cwd": str(tmp_path), "prompt_id": "p1", "prompt": "fix a typo"},
        _fc_env(tmp_path / "fc"),
    )
    assert proc.returncode == 0
    assert proc.stdout.strip() == ""


def test_prompt_submit_speaks_on_fanout(tmp_path):
    proc = _run_hook(
        "prompt-submit",
        {
            "session_id": "s1",
            "cwd": str(tmp_path),
            "prompt_id": "p1",
            "prompt": "spawn parallel subagents to review everything",
        },
        _fc_env(tmp_path / "fc"),
    )
    assert proc.returncode == 0
    out = json.loads(proc.stdout)
    assert "fanout-batch" in out["hookSpecificOutput"]["additionalContext"]


def test_malformed_stdin_fails_open(tmp_path):
    proc = subprocess.run(
        [sys.executable, "-m", "forecost.hooks.fastpath", "prompt-submit"],
        input="not json {{{",
        capture_output=True,
        text=True,
        env=_fc_env(tmp_path / "fc"),
        timeout=10,
    )
    assert proc.returncode == 0


def test_unknown_command_fails_open(tmp_path):
    proc = _run_hook("bogus-command", {}, _fc_env(tmp_path / "fc"))
    assert proc.returncode == 0


def test_gate_denies_over_hard_limit(tmp_path):
    fc_home = tmp_path / "fc"
    fc_home.mkdir()
    (fc_home / "policy.toml").write_text(
        '[[policy.rules]]\nid="cap"\nscope="session"\ncurrency="USD"\n'
        'soft_limit=0.001\nhard_limit=0.002\naction="deny"\n'
    )
    env = _fc_env(fc_home)
    cwd = str(tmp_path / "proj")

    # Establish the session (subprocess writes to fc_home/ledger.db via FORECOST_HOME).
    _run_hook("session-start", {"session_id": "sd1", "cwd": cwd}, env)

    # Inject spend into the SAME ledger file by pointing the sink at it explicitly —
    # no Path.home() dependence, so this works identically on every OS.
    from datetime import datetime, timezone

    from forecost.adapters.base import UsageEvent
    from forecost.ledger.sink import SyncLedgerSink

    sink = SyncLedgerSink(ledger_path=fc_home / "ledger.db")
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
    sink.flush()

    proc = _run_hook("pre-tool", {"session_id": "sd1", "cwd": cwd, "tool_name": "Bash"}, env)
    assert proc.returncode == 0
    out = json.loads(proc.stdout)
    assert out["hookSpecificOutput"]["permissionDecision"] == "deny"
