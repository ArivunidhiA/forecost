from __future__ import annotations

import json
from datetime import datetime, timezone

from click.testing import CliRunner

from forecost.commands.reconcile_cmd import reconcile
from forecost.lab import seed_demo
from forecost.ledger.contracts import CausalIdentity
from forecost.ledger.evidence import append_observation, observation
from forecost.reconciliation import import_bill_file, reconcile_run


def test_offline_provider_import_reconciles_against_local_receipt(ledger_conn, tmp_path):
    run_id = seed_demo(ledger_conn, seed=41)
    export = tmp_path / "openai-costs.json"
    export.write_text(
        json.dumps(
            {
                "data": [
                    {
                        "start_time": "2026-01-01T00:00:11+00:00",
                        "results": [
                            {
                                "amount": {"value": "0.121", "currency": "USD"},
                                "line_item": "model_inference",
                            }
                        ],
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    imported_run, imported = import_bill_file(ledger_conn, export, "openai", run_id=run_id)
    result = reconcile_run(ledger_conn, run_id, tolerance_micros=0)

    assert imported_run == run_id
    assert imported == 1
    assert result["state"] == "reconciled"
    assert result["local_total"] == result["provider_total"] == 121_000
    assert result["observed"] == 2


def test_imported_aggregate_is_not_falsely_called_reconciled(ledger_conn, tmp_path):
    export = tmp_path / "anthropic-usage.csv"
    export.write_text("timestamp,cost_usd,line_item\n2026-01-01T00:00:00+00:00,0.5,model_inference\n")
    run_id, _ = import_bill_file(ledger_conn, export, "anthropic")

    result = reconcile_run(ledger_conn, run_id)

    assert result["state"] == "incomplete"
    assert result["finality"] == "provisional"


def test_reconcile_group_import_and_run_subcommands(ledger_conn, tmp_path, monkeypatch):
    monkeypatch.setattr("forecost.commands.reconcile_cmd.get_ledger_db", lambda: ledger_conn)
    export = tmp_path / "gateway.json"
    export.write_text(
        json.dumps([{"timestamp": "2026-01-01T00:00:00+00:00", "amount_micros": 2}]),
        encoding="utf-8",
    )
    runner = CliRunner()
    imported = runner.invoke(reconcile, ["import", "--source", "gateway", "--file", str(export)])
    assert imported.exit_code == 0
    assert "Imported 1 gateway billing record" in imported.output
    run = imported.output.rsplit(" ", 1)[-1].strip(".\n")
    reconciled = runner.invoke(reconcile, ["run", "--run", run, "--json-output"])
    assert reconciled.exit_code == 0
    assert json.loads(reconciled.output)["state"] == "incomplete"


def test_reconciliation_batches_are_idempotent_and_late_evidence_supersedes(ledger_conn, tmp_path):
    run_id = seed_demo(ledger_conn, seed=43)
    first = reconcile_run(ledger_conn, run_id)
    repeated = reconcile_run(ledger_conn, run_id)

    assert repeated["batch_id"] == first["batch_id"]
    assert repeated["reused"] is True
    export = tmp_path / "late-provider.json"
    export.write_text(
        json.dumps(
            [{"timestamp": "2026-01-01T00:00:20+00:00", "amount_micros": 121_000}]
        ),
        encoding="utf-8",
    )
    import_bill_file(ledger_conn, export, "openai", run_id=run_id)
    late = reconcile_run(ledger_conn, run_id)

    assert late["batch_id"] != first["batch_id"]
    assert late["supersedes_batch_id"] == first["batch_id"]
    assert ledger_conn.execute("SELECT COUNT(*) FROM reconciliation_batches").fetchone()[0] == 2


def test_reconciliation_distinguishes_exact_identity_from_aggregate_constraint(
    ledger_conn, tmp_path
):
    run_id = seed_demo(ledger_conn, seed=44)
    fact_id = ledger_conn.execute(
        "SELECT fact_id FROM meter_facts ORDER BY fact_id LIMIT 1"
    ).fetchone()[0]
    export = tmp_path / "exact-provider.json"
    export.write_text(
        json.dumps(
            [
                {
                    "timestamp": "2026-01-01T00:00:20+00:00",
                    "amount_micros": 121_000,
                    "fact_id": fact_id,
                }
            ]
        ),
        encoding="utf-8",
    )
    import_bill_file(ledger_conn, export, "openai", run_id=run_id)
    result = reconcile_run(ledger_conn, run_id, tolerance_micros=0)

    assert result["exact_match_count"] == 1
    assert result["unmatched_local_count"] == 0
    assert result["unmatched_provider_count"] == 0
    states = {
        row[0]
        for row in ledger_conn.execute(
            "SELECT match_state FROM reconciliation_evidence WHERE batch_id = ?",
            (result["batch_id"],),
        )
    }
    assert states == {"exact_identity"}


def test_provisional_local_evidence_cannot_create_final_reconciliation(ledger_conn, tmp_path):
    run_id = seed_demo(ledger_conn, seed=45)
    row = ledger_conn.execute(
        "SELECT * FROM causal_spans WHERE run_id = ? ORDER BY source_order LIMIT 1", (run_id,)
    ).fetchone()
    causal = CausalIdentity(
        conversation_id=row["conversation_id"],
        trace_id=row["trace_id"],
        run_id=run_id,
        span_id=row["span_id"],
        source_sequence=99,
        idempotency_key="provisional-local",
    )
    append_observation(
        ledger_conn,
        observation(
            producer="local-test",
            event_kind="charge",
            causal=causal,
            payload={
                "amount_micros": 1,
                "currency": "USD",
                "authority": "provider_estimate",
                "line_item": "tool_call",
                "finality": "provisional",
            },
            occurred_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        ),
    )
    export = tmp_path / "provider.json"
    export.write_text(
        json.dumps(
            [{"timestamp": "2026-01-01T00:00:20+00:00", "amount_micros": 121_001}]
        ),
        encoding="utf-8",
    )
    import_bill_file(ledger_conn, export, "openai", run_id=run_id)

    result = reconcile_run(ledger_conn, run_id, tolerance_micros=0)
    assert result["state"] == "reconciled"
    assert result["finality"] == "provisional"
