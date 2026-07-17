"""Tests for `forecost recover` (recovery.jsonl replay)."""

import json
from datetime import datetime, timezone

from click.testing import CliRunner

from forecost.cli import main
from forecost.ledger.db import get_ledger_db


def _spill_line(event_uid, tokens_out=1_000_000):
    return json.dumps(
        {
            "event_uid": event_uid,
            "ts": datetime.now(timezone.utc).isoformat(),
            "source": "test",
            "model": "claude-opus-4-8",
            "session_uid": "s-rec",
            "workspace_path": "/tmp/p",
            "tokens_in": 0,
            "tokens_out": tokens_out,
            "reported_cost": None,
            "metadata": {},
        }
    )


def test_recover_replays_and_archives(tmp_path, monkeypatch):
    monkeypatch.setenv("FORECOST_HOME", str(tmp_path))
    # Prime the ledger connection at this home.
    from forecost.ledger import db as ledger_db

    monkeypatch.setattr(ledger_db, "LEDGER_PATH", tmp_path / "ledger.db")
    ledger_db.reset_connection_for_tests()

    (tmp_path / "recovery.jsonl").write_text(_spill_line("r1") + "\n" + _spill_line("r2") + "\n")

    result = CliRunner().invoke(main, ["recover"])
    assert result.exit_code == 0, result.output
    assert "Recovered 2 event(s)" in result.output
    # Events landed in the ledger.
    conn = get_ledger_db()
    n = conn.execute("SELECT COUNT(*) FROM usage_events").fetchone()[0]
    assert n == 2
    # File archived, so a second run is a no-op replay.
    assert not (tmp_path / "recovery.jsonl").exists()
    assert (tmp_path / "recovery.replayed.jsonl").exists()
    ledger_db.reset_connection_for_tests()


def test_recover_no_file(tmp_path, monkeypatch):
    monkeypatch.setenv("FORECOST_HOME", str(tmp_path))
    result = CliRunner().invoke(main, ["recover"])
    assert result.exit_code == 0
    assert "No recovery file" in result.output
