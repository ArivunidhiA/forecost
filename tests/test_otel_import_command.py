from __future__ import annotations

import json

from click.testing import CliRunner

from forecost.commands.import_cmd import import_data
from forecost.ledger.receipts import build_receipt


def test_otel_import_creates_a_content_free_run(ledger_conn, monkeypatch, tmp_path):
    import forecost.commands.import_cmd as import_module

    monkeypatch.setattr(import_module, "get_ledger_db", lambda: ledger_conn)
    fixture = tmp_path / "otel.json"
    fixture.write_text(
        json.dumps(
            [
                {
                    "conversation_id": "source-conversation",
                    "trace_id": "0123456789abcdef0123456789abcdef",
                    "run_id": "source-run",
                    "span_id": "0123456789abcdef",
                    "idempotency_key": "otel-1",
                    "source_sequence": 1,
                    "operation_kind": "agent",
                    "lifecycle": "completed",
                    "occurred_at": "2026-01-01T00:00:00Z",
                    "attributes": {"gen_ai.prompt": "DO-NOT-PERSIST"},
                }
            ]
        ),
        encoding="utf-8",
    )

    result = CliRunner().invoke(import_data, ["otel", "--file", str(fixture)])

    assert result.exit_code == 0
    run_id = ledger_conn.execute("SELECT run_id FROM causal_runs").fetchone()[0]
    assert build_receipt(ledger_conn, run_id)["lifecycle"] == "completed"
    stored = ledger_conn.execute(
        "SELECT causal_json || payload_json FROM journal_observations"
    ).fetchone()[0]
    assert "DO-NOT-PERSIST" not in stored
