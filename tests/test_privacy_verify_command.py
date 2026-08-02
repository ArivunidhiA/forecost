from __future__ import annotations

from click.testing import CliRunner

from forecost.commands.privacy_cmd import privacy
from forecost.commands.verify_cmd import verify
from forecost.lab import seed_demo
from forecost.ledger.receipts import build_receipt, save_receipt


def test_privacy_verify_detects_only_explicit_canary(tmp_path):
    root = tmp_path / "home"
    root.mkdir()
    clean = CliRunner().invoke(privacy, ["verify", "--home", str(root), "--canary", "SENTINEL"])
    assert clean.exit_code == 0
    (root / "state.txt").write_text("SENTINEL", encoding="utf-8")
    found = CliRunner().invoke(privacy, ["verify", "--home", str(root), "--canary", "SENTINEL"])
    assert found.exit_code != 0
    assert "privacy canary found" in found.output


def test_verify_detects_modified_receipt_snapshot(ledger_conn, monkeypatch):
    monkeypatch.setattr("forecost.commands.verify_cmd.get_ledger_db", lambda: ledger_conn)
    run_id = seed_demo(ledger_conn, seed=53)
    receipt = build_receipt(ledger_conn, run_id)
    save_receipt(ledger_conn, receipt)
    intact = CliRunner().invoke(verify, [])
    assert intact.exit_code == 0
    ledger_conn.execute("UPDATE receipt_snapshots SET payload_json = '{}' ")
    ledger_conn.commit()
    modified = CliRunner().invoke(verify, [])
    assert modified.exit_code != 0
    assert "rewritten or malformed" in modified.output
