from __future__ import annotations

from click.testing import CliRunner

from forecost.commands.statusline_cmd import statusline
from forecost.hooks import handlers
from forecost.hooks.state import pending_settlements, read_heartbeat


def test_session_end_fsyncs_only_content_free_marker(tmp_path, monkeypatch):
    monkeypatch.setenv("FORECOST_HOME", str(tmp_path / "home"))
    handlers.handle_session_end(
        {
            "session_id": "raw-session",
            "transcript_path": "/private/raw/transcript.jsonl",
            "prompt": "NEVER-PERSIST",
        }
    )
    assert pending_settlements() == 1
    blob = "\n".join(
        path.read_text(encoding="utf-8")
        for path in (tmp_path / "home" / "hooks").iterdir()
        if path.is_file()
    )
    assert "raw-session" not in blob
    assert "transcript" not in blob
    assert "NEVER-PERSIST" not in blob


def test_statusline_exposes_never_ran_and_observed_states(tmp_path, monkeypatch):
    monkeypatch.setenv("FORECOST_HOME", str(tmp_path / "home"))
    import forecost.ledger.db as ledger_db

    monkeypatch.setattr(ledger_db, "LEDGER_PATH", tmp_path / "home" / "ledger.db")
    monkeypatch.setattr(ledger_db, "_conn", None)
    first = CliRunner().invoke(statusline)
    assert first.exit_code == 0
    assert "NOT OBSERVED" in first.output
    handlers.handle_session_end({"session_id": "s"})
    heartbeat = read_heartbeat()
    assert heartbeat is not None
    assert heartbeat["readiness"] == "OBSERVED"
    second = CliRunner().invoke(statusline)
    assert "OBSERVED" in second.output
