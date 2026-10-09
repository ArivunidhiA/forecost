from __future__ import annotations

import json
from dataclasses import replace
from datetime import datetime, timezone
from hashlib import sha256

from click.testing import CliRunner

from forecost.commands.reconcile_cmd import reconcile
from forecost.lab import seed_demo
from forecost.ledger.contracts import Authority, CausalIdentity
from forecost.ledger.evidence import append_observation, observation
from forecost.ledger.integrity import verify_journal_chain
from forecost.ledger.receipts import build_receipt
from forecost.ledger.schema import SCHEMA_VERSION, apply_schema
from forecost.reconciliation import import_bill_file, reconcile_run


def test_offline_user_claim_reconciles_against_local_receipt(ledger_conn, tmp_path):
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
    assert result["local_total"] == result["user_imported_claim_total"] == 121_000
    assert result["observed"] == 2
    authorities = {
        row[0] for row in ledger_conn.execute("SELECT authority FROM charges").fetchall()
    }
    assert "user_imported_claim" in authorities
    assert "billed" not in authorities
    source_set = ledger_conn.execute(
        "SELECT source_set_json FROM reconciliation_batches WHERE batch_id = ?",
        (result["batch_id"],),
    ).fetchone()[0]
    assert json.loads(source_set) == {"local": True, "user_imported_claim": True}
    roles = {
        row[0]
        for row in ledger_conn.execute(
            "SELECT source_role FROM reconciliation_evidence WHERE batch_id = ?",
            (result["batch_id"],),
        )
    }
    assert roles == {"local", "user_imported_claim"}


def test_imported_aggregate_is_not_falsely_called_reconciled(ledger_conn, tmp_path):
    export = tmp_path / "anthropic-usage.csv"
    export.write_text(
        "timestamp,cost_usd,line_item\n2026-01-01T00:00:00+00:00,0.5,model_inference\n"
    )
    run_id, _ = import_bill_file(ledger_conn, export, "anthropic")

    result = reconcile_run(ledger_conn, run_id)

    assert result["state"] == "incomplete"
    assert result["finality"] == "provisional"


def test_multiple_import_rows_without_source_fact_ids_remain_additive_and_replay_stable(
    ledger_conn, tmp_path
):
    export = tmp_path / "multi-row-aggregate.json"
    export.write_text(
        json.dumps(
            [
                {"timestamp": "2026-01-01T00:00:00+00:00", "amount_micros": 11},
                {"timestamp": "2026-01-01T00:00:01+00:00", "amount_micros": 13},
            ]
        ),
        encoding="utf-8",
    )

    run_id, imported = import_bill_file(ledger_conn, export, "openai")
    repeated_run, repeated = import_bill_file(ledger_conn, export, "openai")
    fact_ids = [
        row[0]
        for row in ledger_conn.execute(
            "SELECT fact_id FROM charges ORDER BY occurred_at, charge_id"
        ).fetchall()
    ]
    receipt = build_receipt(ledger_conn, run_id)

    assert imported == 2
    assert repeated == 0
    assert repeated_run == run_id
    assert len(fact_ids) == len(set(fact_ids)) == 2
    assert all(str(fact_id).startswith("fact:") for fact_id in fact_ids)
    assert receipt["economic_totals_micros"] == {"USD": {"user_imported_claim": 24}}
    assert len(receipt["valuation_groups"]) == 2  # type: ignore[arg-type]


def test_arbitrary_file_fields_cannot_elevate_import_to_billed(ledger_conn, tmp_path):
    export = tmp_path / "self-described-provider.json"
    export.write_text(
        json.dumps(
            [
                {
                    "timestamp": "2026-01-01T00:00:00+00:00",
                    "amount_micros": 42,
                    "authority": "billed",
                    "authenticated": True,
                    "provider_signature": "not-a-real-signature",
                }
            ]
        ),
        encoding="utf-8",
    )

    import_bill_file(ledger_conn, export, "openai")

    assert ledger_conn.execute("SELECT authority FROM charges").fetchone()[0] == (
        Authority.USER_IMPORTED_CLAIM.value
    )
    stored = ledger_conn.execute(
        "SELECT payload_json FROM journal_observations WHERE event_kind='charge'"
    ).fetchone()[0]
    assert '"authority":"billed"' not in stored


def test_v11_supersedes_pre_fix_billed_import_without_duplicating_replay(ledger_conn, tmp_path):
    export = tmp_path / "legacy-import.json"
    export.write_text(
        json.dumps([{"timestamp": "2026-01-01T00:00:00+00:00", "amount_micros": 77}]),
        encoding="utf-8",
    )
    digest = sha256(export.read_bytes()).hexdigest()
    occurred_at = datetime(2026, 1, 1, tzinfo=timezone.utc)
    root = CausalIdentity(
        conversation_id=f"import-conversation-{digest}",
        trace_id=digest[:32],
        run_id=f"import-openai-{digest}",
        span_id=digest[32:48],
        source_sequence=0,
        idempotency_key=f"import-root-{digest}",
    )
    append_observation(
        ledger_conn,
        observation(
            producer="billing-openai",
            event_kind="span",
            causal=root,
            payload={
                "operation_kind": "custom",
                "lifecycle": "completed",
                "branch_id": "billing",
            },
            occurred_at=occurred_at,
            observed_at=occurred_at,
        ),
    )
    append_observation(
        ledger_conn,
        replace(
            observation(
                producer="billing-openai",
                event_kind="charge",
                causal=replace(
                    root,
                    source_sequence=1,
                    idempotency_key=f"import-{digest}-1",
                ),
                payload={
                    "amount_micros": 77,
                    "currency": "USD",
                    "authority": "billed",
                    "line_item": "model_inference",
                    "finality": "final",
                },
                occurred_at=occurred_at,
                observed_at=occurred_at,
            ),
            schema_version=1,
        ),
    )
    ledger_conn.execute("PRAGMA user_version = 10")
    ledger_conn.commit()

    apply_schema(ledger_conn)
    repeated_run, repeated = import_bill_file(ledger_conn, export, "openai")

    run_id = root.normalized().run_id
    assert repeated_run == run_id
    assert repeated == 0
    assert ledger_conn.execute("PRAGMA user_version").fetchone()[0] == SCHEMA_VERSION
    assert ledger_conn.execute("SELECT COUNT(*) FROM charges").fetchone()[0] == 2
    active = ledger_conn.execute(
        "SELECT authority FROM charges c WHERE NOT EXISTS ("
        "SELECT 1 FROM charges newer WHERE newer.supersedes_charge_id = c.charge_id)"
    ).fetchall()
    assert [row[0] for row in active] == [Authority.USER_IMPORTED_CLAIM.value]
    assert verify_journal_chain(ledger_conn).state == "intact"
    observation_ids = ledger_conn.execute(
        "SELECT observation_id FROM journal_observations ORDER BY journal_sequence"
    ).fetchall()
    ledger_conn.execute("PRAGMA user_version = 10")
    ledger_conn.commit()
    apply_schema(ledger_conn)
    assert (
        ledger_conn.execute(
            "SELECT observation_id FROM journal_observations ORDER BY journal_sequence"
        ).fetchall()
        == observation_ids
    )
    assert verify_journal_chain(ledger_conn).state == "intact"
    result = reconcile_run(ledger_conn, run_id)
    assert result["state"] == "incomplete"
    assert result["user_imported_claim_count"] == 1
    receipt = build_receipt(ledger_conn, run_id)
    assert receipt["economic_totals_micros"] == {"USD": {"user_imported_claim": 77}}
    evidence = receipt["evidence"]
    assert isinstance(evidence, dict)
    claim_profiles = evidence["claim_profiles"]
    assert isinstance(claim_profiles, dict)
    provider_claim = claim_profiles["provider-billed"]
    assert isinstance(provider_claim, dict)
    assert provider_claim["completeness"] == "partial"
    assert provider_claim["denominator"] == 2
    assert "authenticated_settlement" in provider_claim["unmet_obligations"]


def test_v11_does_not_downgrade_unrelated_billed_producer(ledger_conn):
    causal = CausalIdentity(
        conversation_id="authenticated-conversation",
        trace_id="a" * 32,
        run_id="authenticated-run",
        span_id="b" * 16,
        idempotency_key="authenticated-root",
    )
    append_observation(
        ledger_conn,
        observation(
            producer="authenticated-provider-profile",
            event_kind="span",
            causal=causal,
            payload={"operation_kind": "custom", "lifecycle": "completed"},
        ),
    )
    append_observation(
        ledger_conn,
        observation(
            producer="authenticated-provider-profile",
            event_kind="charge",
            causal=replace(causal, source_sequence=1, idempotency_key="authenticated-charge"),
            payload={
                "amount_micros": 88,
                "currency": "USD",
                "authority": "billed",
                "line_item": "model_inference",
                "finality": "final",
            },
        ),
    )
    ledger_conn.execute("PRAGMA user_version = 10")
    ledger_conn.commit()

    apply_schema(ledger_conn)

    assert ledger_conn.execute("SELECT COUNT(*) FROM charges").fetchone()[0] == 1
    assert ledger_conn.execute("SELECT authority FROM charges").fetchone()[0] == "billed"
    assert verify_journal_chain(ledger_conn).state == "intact"


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
    assert "Imported 1 user-supplied gateway economic claim record" in imported.output
    assert "source origin is not authenticated" in imported.output
    run = imported.output.split("Run: ", 1)[1].strip()
    reconciled = runner.invoke(reconcile, ["run", "--run", run, "--json-output"])
    assert reconciled.exit_code == 0
    assert json.loads(reconciled.output)["state"] == "incomplete"
    human = runner.invoke(reconcile, ["run", "--run", run])
    assert human.exit_code == 0
    assert "user_imported_claim=" in human.output
    assert "provider=" not in human.output


def test_reconciliation_batches_are_idempotent_and_late_evidence_supersedes(ledger_conn, tmp_path):
    run_id = seed_demo(ledger_conn, seed=43)
    first = reconcile_run(ledger_conn, run_id)
    repeated = reconcile_run(ledger_conn, run_id)

    assert repeated["batch_id"] == first["batch_id"]
    assert repeated["reused"] is True
    export = tmp_path / "late-provider.json"
    export.write_text(
        json.dumps([{"timestamp": "2026-01-01T00:00:20+00:00", "amount_micros": 121_000}]),
        encoding="utf-8",
    )
    import_bill_file(ledger_conn, export, "openai", run_id=run_id)
    late = reconcile_run(ledger_conn, run_id)

    assert late["batch_id"] != first["batch_id"]
    assert late["supersedes_batch_id"] == first["batch_id"]
    assert ledger_conn.execute("SELECT COUNT(*) FROM reconciliation_batches").fetchone()[0] == 2
    receipt = build_receipt(ledger_conn, run_id)
    batches = receipt["reconciliation_batches"]
    assert isinstance(batches, list)
    assert [batch["active"] for batch in batches] == [False, True]
    active = batches[-1]
    assert active["source_set"] == {"local": True, "user_imported_claim": True}
    assert "provider_amount_micros" not in active
    assert "unmatched_provider_count" not in active
    assert active["user_imported_claim_amount_micros"] == 121_000
    assert active["unmatched_user_imported_claim_count"] == 1


def test_discrepant_reconciliation_contradicts_economic_scope(ledger_conn, tmp_path):
    run_id = seed_demo(ledger_conn, seed=46)
    export = tmp_path / "discrepant-claim.json"
    export.write_text(
        json.dumps([{"timestamp": "2026-01-01T00:00:20+00:00", "amount_micros": 999_000}]),
        encoding="utf-8",
    )
    import_bill_file(ledger_conn, export, "openai", run_id=run_id)
    result = reconcile_run(ledger_conn, run_id, tolerance_micros=0)

    receipt = build_receipt(ledger_conn, run_id)
    economic = receipt["evidence"]["claim_profiles"]["economic-estimate"]  # type: ignore[index]
    batches = receipt["reconciliation_batches"]

    assert result["state"] == "discrepant"
    assert economic["contradiction"] == "contradictory"
    assert economic["state"] == "contradictory"
    assert batches[-1]["state"] == "discrepant"  # type: ignore[index]
    assert batches[-1]["active"] is True  # type: ignore[index]


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
    assert result["unmatched_user_imported_claim_count"] == 0
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
        json.dumps([{"timestamp": "2026-01-01T00:00:20+00:00", "amount_micros": 121_001}]),
        encoding="utf-8",
    )
    import_bill_file(ledger_conn, export, "openai", run_id=run_id)

    result = reconcile_run(ledger_conn, run_id, tolerance_micros=0)
    assert result["state"] == "reconciled"
    assert result["finality"] == "provisional"
