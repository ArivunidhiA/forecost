from __future__ import annotations

import sys

from click.testing import CliRunner

from forecost.commands.capture_cmd import capture
from forecost.lab import seed_demo
from forecost.ledger.receipts import build_receipt


def test_capture_records_exit_and_does_not_replace_it_with_git_fact(ledger_conn, monkeypatch):
    monkeypatch.setattr("forecost.commands.capture_cmd.get_ledger_db", lambda: ledger_conn)
    monkeypatch.setattr("forecost.commands.capture_cmd._git_head", lambda: "a" * 40)
    run_id = seed_demo(ledger_conn, seed=61)

    result = CliRunner().invoke(
        capture,
        [run_id, "--kind", "test", sys.executable, "-c", "raise SystemExit(0)"],
    )

    assert result.exit_code == 0
    receipt = build_receipt(ledger_conn, run_id)
    assert receipt["outcome"]["status"] == "good"  # type: ignore[index]
    evidence = receipt["outcome_evidence"]
    assert isinstance(evidence, list)
    assert {item["evidence_type"] for item in evidence} >= {"test_exit", "git_fact"}


def test_capture_propagates_failure_exit_without_persisting_command(ledger_conn, monkeypatch):
    monkeypatch.setattr("forecost.commands.capture_cmd.get_ledger_db", lambda: ledger_conn)
    monkeypatch.setattr("forecost.commands.capture_cmd._git_head", lambda: None)
    run_id = seed_demo(ledger_conn, seed=62)
    sentinel = "DO-NOT-PERSIST-CAPTURE-COMMAND"

    result = CliRunner().invoke(
        capture,
        [run_id, "--kind", "build", sys.executable, "-c", "raise SystemExit(7)", sentinel],
    )

    assert result.exit_code == 7
    blob = "".join(
        row[0]
        for row in ledger_conn.execute(
            "SELECT causal_json || payload_json FROM journal_observations"
        ).fetchall()
    )
    assert sentinel not in blob
    assert build_receipt(ledger_conn, run_id)["outcome"]["status"] == "bad"  # type: ignore[index]
