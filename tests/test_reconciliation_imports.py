from __future__ import annotations

import json

from click.testing import CliRunner

from forecost.commands.reconcile_cmd import reconcile
from forecost.lab import seed_demo
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
