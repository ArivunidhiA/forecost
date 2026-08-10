from __future__ import annotations

import json
from pathlib import Path

import pytest
from click.testing import CliRunner

from forecost.commands.mark_cmd import mark
from forecost.commands.receipt_cmd import receipt
from forecost.commands.runs_cmd import list_runs, show_run
from forecost.lab import seed_chaos, seed_demo
from forecost.ledger.contracts import CausalIdentity, Observation
from forecost.ledger.evidence import append_observation, observation
from forecost.ledger.receipts import build_receipt


def test_demo_receipt_is_deterministic_and_does_not_double_count_authorities(ledger_conn):
    run_id = seed_demo(ledger_conn, seed=11)
    first = build_receipt(ledger_conn, run_id)
    second = build_receipt(ledger_conn, run_id)

    assert json.dumps(first, sort_keys=True) == json.dumps(second, sort_keys=True)
    evidence = first["evidence"]
    graph = first["causal_graph"]
    assert isinstance(evidence, dict)
    assert isinstance(graph, list)
    assert evidence["state"] == "complete"
    assert first["economic_totals_micros"] == {"USD": {"gateway_estimate": 121_000}}
    assert len(graph) == 6


def test_chaos_seed_replays_to_same_receipt(tmp_path):
    from forecost.ledger.db import get_ledger_db

    left = get_ledger_db(Path(tmp_path / "left.db"))
    right = get_ledger_db(Path(tmp_path / "right.db"))
    left_run = seed_chaos(left, seed=19, branches=9)
    right_run = seed_chaos(right, seed=19, branches=9)

    assert build_receipt(left, left_run) == build_receipt(right, right_run)


def test_duplicate_observation_is_idempotent_but_mismatch_is_rejected(ledger_conn):
    causal = CausalIdentity("c", "1" * 32, "r", "2" * 16, idempotency_key="same")
    item = observation(
        producer="test",
        event_kind="span",
        causal=causal,
        payload={"operation_kind": "agent", "lifecycle": "running"},
    )
    assert append_observation(ledger_conn, item)
    assert not append_observation(ledger_conn, item)
    changed = Observation(
        producer="test",
        event_kind="span",
        causal=causal,
        occurred_at=item.occurred_at,
        observed_at=item.observed_at,
        payload={"operation_kind": "agent", "lifecycle": "failed"},
    )
    with pytest.raises(ValueError, match="idempotency"):
        append_observation(ledger_conn, changed)


def test_receipt_commands_render_and_mark_outcome(ledger_conn, monkeypatch):
    monkeypatch.setattr("forecost.commands.receipt_cmd.get_ledger_db", lambda: ledger_conn)
    monkeypatch.setattr("forecost.commands.mark_cmd.get_ledger_db", lambda: ledger_conn)
    monkeypatch.setattr("forecost.commands.runs_cmd.get_ledger_db", lambda: ledger_conn)
    run_id = seed_demo(ledger_conn, seed=31)
    runner = CliRunner()

    receipt_result = runner.invoke(receipt, [run_id, "--json-output"])
    assert receipt_result.exit_code == 0
    assert json.loads(receipt_result.output)["run_id"] == run_id

    mark_result = runner.invoke(mark, [run_id, "good", "--reason", "tests_passed"])
    assert mark_result.exit_code == 0
    outcome = build_receipt(ledger_conn, run_id)["outcome"]
    assert isinstance(outcome, dict)
    assert outcome["status"] == "good"

    listed = runner.invoke(list_runs, [])
    shown = runner.invoke(show_run, [run_id])
    assert listed.exit_code == 0
    assert "evidence=complete" in listed.output
    assert shown.exit_code == 0
    assert "Critical path:" in shown.output


def test_receipt_timing_does_not_double_count_enclosing_parent(ledger_conn):
    base = CausalIdentity("c", "1" * 32, "r", "2" * 16, idempotency_key="root")
    child = CausalIdentity(
        "c",
        "1" * 32,
        "r",
        "3" * 16,
        parent_span_id="2" * 16,
        source_sequence=1,
        idempotency_key="child",
    )
    from datetime import datetime, timedelta, timezone

    start = datetime(2026, 1, 1, tzinfo=timezone.utc)
    append_observation(
        ledger_conn,
        observation(
            producer="timing",
            event_kind="span",
            causal=base,
            payload={"operation_kind": "agent", "lifecycle": "completed"},
            occurred_at=start,
            observed_at=start + timedelta(seconds=10),
        ),
    )
    append_observation(
        ledger_conn,
        observation(
            producer="timing",
            event_kind="span",
            causal=child,
            payload={"operation_kind": "model", "lifecycle": "completed"},
            occurred_at=start + timedelta(seconds=2),
            observed_at=start + timedelta(seconds=8),
        ),
    )

    timing = build_receipt(ledger_conn, base.normalized().run_id)["timing_micros"]
    assert isinstance(timing, dict)
    assert timing["critical_path"] == 10_000_000
    assert timing["elapsed"] == 10_000_000


def test_receipt_surfaces_expected_source_gap_and_accepts_no_color(ledger_conn, monkeypatch):
    monkeypatch.setattr("forecost.commands.receipt_cmd.get_ledger_db", lambda: ledger_conn)
    run_id = seed_demo(ledger_conn, seed=32)
    ledger_conn.execute(
        "UPDATE causal_runs SET source_coverage_json = ? WHERE run_id = ?",
        ('{"sources_expected":["missing-source"]}', run_id),
    )
    result = build_receipt(ledger_conn, run_id)
    evidence = result["evidence"]
    assert isinstance(evidence, dict)
    assert evidence["state"] == "incomplete"
    assert "missing-source" in evidence["known_blind_spots"]

    rendered = CliRunner().invoke(receipt, [run_id, "--no-color"])
    assert rendered.exit_code == 0
    assert "\x1b[" not in rendered.output
