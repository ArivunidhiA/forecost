from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import cast

import pytest
from click.testing import CliRunner

from forecost.commands.mark_cmd import mark
from forecost.commands.receipt_cmd import receipt
from forecost.commands.runs_cmd import _timing_line, list_runs, show_run
from forecost.lab import seed_chaos, seed_demo
from forecost.ledger.contracts import (
    CausalIdentity,
    Observation,
    opaque_id,
    trace_scoped_span_key,
)
from forecost.ledger.evidence import append_observation, observation, rebuild_projections
from forecost.ledger.receipts import (
    _load_receipt_rows,
    _structural_signals,
    build_receipt,
    receipt_text,
)


def _append_timed_span(
    ledger_conn,
    *,
    index: int,
    start: datetime,
    start_seconds: int,
    end_seconds: int,
    run_id: str = "timing-adversarial",
    parent_index: int | None = None,
    link_indexes: tuple[int, ...] = (),
    operation_kind: str = "model",
    attempt_of_index: int | None = None,
) -> CausalIdentity:
    span_id = f"{index:016x}"
    causal = CausalIdentity(
        "timing-conversation",
        "a" * 32,
        run_id,
        span_id,
        parent_span_id=f"{parent_index:016x}" if parent_index is not None else None,
        links=tuple(f"{link:016x}" for link in link_indexes),
        source_sequence=index,
        idempotency_key=f"timed-{index}",
    )
    payload: dict[str, object] = {
        "operation_kind": operation_kind,
        "lifecycle": "completed",
        "started_at": (start + timedelta(seconds=start_seconds)).isoformat(),
        "ended_at": (start + timedelta(seconds=end_seconds)).isoformat(),
        "timing_source": "explicit_interval",
    }
    if attempt_of_index is not None:
        payload["attempt_of_span_id"] = f"{attempt_of_index:016x}"
    append_observation(
        ledger_conn,
        observation(
            producer="otel",
            event_kind="span",
            causal=causal,
            payload=payload,
            occurred_at=start + timedelta(seconds=end_seconds),
            observed_at=start + timedelta(seconds=end_seconds + 1),
        ),
    )
    return causal.normalized()


def _mapping(value: object) -> dict[str, object]:
    assert isinstance(value, dict)
    return cast(dict[str, object], value)


def _timing_section(receipt_value: dict[str, object]) -> dict[str, object]:
    return _mapping(receipt_value["timing_micros"])


def _profile_section(receipt_value: dict[str, object], profile_id: str) -> dict[str, object]:
    evidence = _mapping(receipt_value["evidence"])
    profiles = _mapping(evidence["claim_profiles"])
    return _mapping(profiles[profile_id])


def test_runs_timing_line_names_withheld_critical_path_without_none_units():
    rendered = _timing_line(
        {
            "state": "partial",
            "basis": (
                "explicit_interval_unions_and_elapsed_envelope;"
                "critical_path_withheld_untyped_execution_edges"
            ),
            "critical_path": None,
            "service": 3_000_000,
            "wait": 0,
            "elapsed": 4_000_000,
        }
    )

    assert "service 3000000us" in rendered
    assert "wait 0us" in rendered
    assert "elapsed 4000000us" in rendered
    assert "critical path withheld (untyped scheduling dependencies)" in rendered
    assert "Noneus" not in rendered


def test_runs_timing_line_labels_trivial_single_span_critical_path():
    rendered = _timing_line(
        {
            "state": "complete",
            "basis": (
                "explicit_interval_unions_and_elapsed_envelope;critical_path_trivial_single_span"
            ),
            "critical_path": 4_000_000,
            "service": 4_000_000,
            "wait": 0,
            "elapsed": 4_000_000,
        }
    )

    assert "critical path 4000000us (trivial one-span case)" in rendered


def _mapping_list(value: object) -> list[dict[str, object]]:
    assert isinstance(value, list)
    assert all(isinstance(item, dict) for item in value)
    return cast(list[dict[str, object]], value)


def _profile_obligations(profile: dict[str, object]) -> list[dict[str, object]]:
    return _mapping_list(profile["obligations"])


def _string_list(value: object) -> list[str]:
    assert isinstance(value, list)
    assert all(isinstance(item, str) for item in value)
    return cast(list[str], value)


def _seed_charge_context(ledger_conn, *, seed: int) -> tuple[str, CausalIdentity, str, int]:
    run_id = seed_demo(ledger_conn, seed=seed)
    row = ledger_conn.execute(
        "SELECT * FROM causal_spans WHERE run_id = ? ORDER BY source_order LIMIT 1",
        (run_id,),
    ).fetchone()
    fact_id = str(ledger_conn.execute("SELECT fact_id FROM meter_facts LIMIT 1").fetchone()[0])
    amount = int(
        ledger_conn.execute(
            "SELECT amount_micros FROM charges WHERE authority = 'list_rate' LIMIT 1"
        ).fetchone()[0]
    )
    causal = CausalIdentity(
        row["conversation_id"],
        row["trace_id"],
        run_id,
        row["span_id"],
    )
    return run_id, causal, fact_id, amount


def _charge_observation(
    *,
    causal: CausalIdentity,
    fact_id: str,
    amount: int,
    sequence: int,
    idempotency_key: str,
    when: datetime,
    line_item: str = "model_inference",
    supersedes_charge_id: str | None = None,
) -> Observation:
    return observation(
        producer="charge-supersession-test",
        event_kind="charge",
        causal=CausalIdentity(
            causal.conversation_id,
            causal.trace_id,
            causal.run_id,
            causal.span_id,
            source_sequence=sequence,
            idempotency_key=idempotency_key,
        ),
        payload={
            "fact_id": fact_id,
            "amount_micros": amount,
            "currency": "USD",
            "authority": "list_rate",
            "line_item": line_item,
            "finality": "final",
            "supersedes_charge_id": supersedes_charge_id,
        },
        occurred_at=when + timedelta(seconds=sequence),
        observed_at=when + timedelta(seconds=sequence),
    )


def _valuation_rows(receipt_value: dict[str, object]) -> list[dict[str, object]]:
    return [
        valuation
        for group in _mapping_list(receipt_value["valuation_groups"])
        for valuation in _mapping_list(group["valuations"])
    ]


def test_demo_receipt_is_deterministic_and_does_not_double_count_authorities(ledger_conn):
    run_id = seed_demo(ledger_conn, seed=11)
    first = build_receipt(ledger_conn, run_id)
    second = build_receipt(ledger_conn, run_id)

    assert json.dumps(first, sort_keys=True) == json.dumps(second, sort_keys=True)
    evidence = first["evidence"]
    graph = first["causal_graph"]
    assert isinstance(evidence, dict)
    assert isinstance(graph, list)
    assert evidence["legacy_projection_state"] == "complete"
    assert first["economic_totals_micros"] == {"USD": {"gateway_estimate": 121_000}}
    assert len(graph) == 6
    meters = _mapping_list(first["meter_facts"])
    assert meters[0]["dimensions"] != {}
    assert str(meters[0]["source"]).startswith("producer:")
    assert meters[0]["observed_at"] == "2026-01-01T00:00:11+00:00"
    groups = first["valuation_groups"]
    assert isinstance(groups, list)
    assert len(groups) == 1
    group = groups[0]
    assert group["aggregation_rule"] == "alternatives_not_additive"
    assert [item["authority"] for item in group["valuations"]] == [  # type: ignore[index]
        "gateway_estimate",
        "list_rate",
    ]
    assert sum(bool(item["selected"]) for item in group["valuations"]) == 1  # type: ignore[index]
    selected = next(item for item in group["valuations"] if item["selected"])  # type: ignore[index]
    assert selected["tariff"] != {}
    assert selected["account_scope"] is None
    assert selected["billing_period"] is None
    assert str(selected["source"]).startswith("producer:")
    assert selected["observed_at"] == "2026-01-01T00:00:13+00:00"
    outcome = _mapping(first["outcome"])
    outcome_evidence = _mapping_list(first["outcome_evidence"])
    assert outcome["source"] == outcome_evidence[0]["source"]
    assert str(outcome["source"]).startswith("producer:")
    profiles = evidence["claim_profiles"]
    assert profiles["structural"]["completeness"] == "complete"
    assert profiles["provider-billed"]["completeness"] == "partial"
    assert profiles["provider-billed"]["denominator"] == 2
    rendered = receipt_text(first)
    assert "no global completeness claim" in rendered
    assert "provider-billed: completeness=partial" in rendered
    assert "satisfied=0/2" in rendered
    assert "Evidence: complete" not in rendered


def test_user_imported_claim_is_preserved_but_not_added_to_competing_valuation(
    ledger_conn,
):
    run_id = seed_demo(ledger_conn, seed=12)
    row = ledger_conn.execute(
        "SELECT * FROM causal_spans WHERE run_id = ? ORDER BY source_order LIMIT 1", (run_id,)
    ).fetchone()
    fact_id = ledger_conn.execute("SELECT fact_id FROM meter_facts LIMIT 1").fetchone()[0]
    causal = CausalIdentity(
        conversation_id=row["conversation_id"],
        trace_id=row["trace_id"],
        run_id=run_id,
        span_id=row["span_id"],
        source_sequence=99,
        idempotency_key="competing-user-import",
    )
    append_observation(
        ledger_conn,
        observation(
            producer="test-import",
            event_kind="charge",
            causal=causal,
            payload={
                "fact_id": fact_id,
                "amount_micros": 999_000,
                "currency": "USD",
                "authority": "user_imported_claim",
                "line_item": "model_inference",
                "finality": "final",
            },
        ),
    )

    receipt = build_receipt(ledger_conn, run_id)

    assert ledger_conn.execute("SELECT COUNT(*) FROM charges").fetchone()[0] == 3
    assert receipt["economic_totals_micros"] == {"USD": {"gateway_estimate": 121_000}}


def test_forward_charge_supersession_cannot_hide_future_charge(ledger_conn):
    run_id = seed_demo(ledger_conn, seed=13)
    row = ledger_conn.execute(
        "SELECT * FROM causal_spans WHERE run_id = ? ORDER BY source_order LIMIT 1",
        (run_id,),
    ).fetchone()
    fact_id = ledger_conn.execute("SELECT fact_id FROM meter_facts LIMIT 1").fetchone()[0]
    amount = ledger_conn.execute(
        "SELECT amount_micros FROM charges WHERE authority = 'list_rate' LIMIT 1"
    ).fetchone()[0]
    when = datetime(2026, 1, 1, tzinfo=timezone.utc)

    def charge_observation(
        *, sequence: int, idempotency_key: str, supersedes_charge_id: str | None = None
    ) -> Observation:
        return observation(
            producer="forward-charge-test",
            event_kind="charge",
            causal=CausalIdentity(
                row["conversation_id"],
                row["trace_id"],
                run_id,
                row["span_id"],
                source_sequence=sequence,
                idempotency_key=idempotency_key,
            ),
            payload={
                "fact_id": fact_id,
                "amount_micros": amount,
                "currency": "USD",
                "authority": "list_rate",
                "line_item": "model_inference",
                "finality": "final",
                "supersedes_charge_id": supersedes_charge_id,
            },
            occurred_at=when + timedelta(seconds=sequence),
            observed_at=when + timedelta(seconds=sequence),
        )

    future = charge_observation(sequence=102, idempotency_key="future-charge")
    future_charge_id = opaque_id("charge", future.observation_id)
    earlier = charge_observation(
        sequence=101,
        idempotency_key="earlier-forward-reference",
        supersedes_charge_id=future_charge_id,
    )
    append_observation(ledger_conn, earlier)
    append_observation(ledger_conn, future)

    receipt_value = build_receipt(ledger_conn, run_id)
    evidence = _mapping(receipt_value["evidence"])
    economic = _profile_section(receipt_value, "economic-estimate")
    valuations = _valuation_rows(receipt_value)
    valuation_ids = {valuation["charge_id"] for valuation in valuations}
    earlier_charge_id = opaque_id("charge", earlier.observation_id)

    assert earlier_charge_id in valuation_ids
    assert future_charge_id in valuation_ids
    assert (
        next(valuation for valuation in valuations if valuation["charge_id"] == earlier_charge_id)[
            "supersession_valid"
        ]
        is False
    )
    assert evidence["legacy_projection_state"] == "conflicted"
    assert economic["contradiction"] == "contradictory"


def test_missing_charge_supersession_target_cannot_hide_the_invalid_source(ledger_conn):
    run_id, causal, fact_id, amount = _seed_charge_context(ledger_conn, seed=14)
    item = _charge_observation(
        causal=causal,
        fact_id=fact_id,
        amount=amount,
        sequence=201,
        idempotency_key="missing-charge-reference",
        when=datetime(2026, 1, 1, tzinfo=timezone.utc),
        supersedes_charge_id=opaque_id("charge", "absent-charge"),
    )
    append_observation(ledger_conn, item)

    receipt_value = build_receipt(ledger_conn, run_id)
    evidence = _mapping(receipt_value["evidence"])
    economic = _profile_section(receipt_value, "economic-estimate")
    charge_id = opaque_id("charge", item.observation_id)
    valuation = next(row for row in _valuation_rows(receipt_value) if row["charge_id"] == charge_id)

    assert valuation["supersession_valid"] is False
    assert evidence["legacy_projection_state"] == "conflicted"
    assert economic["contradiction"] == "contradictory"


def test_charge_supersession_cannot_cross_an_economic_line_scope(ledger_conn):
    run_id, causal, fact_id, amount = _seed_charge_context(ledger_conn, seed=15)
    target_id = str(
        ledger_conn.execute(
            "SELECT charge_id FROM charges WHERE authority = 'list_rate' LIMIT 1"
        ).fetchone()[0]
    )
    item = _charge_observation(
        causal=causal,
        fact_id=fact_id,
        amount=amount,
        sequence=202,
        idempotency_key="cross-line-charge-reference",
        when=datetime(2026, 1, 1, tzinfo=timezone.utc),
        line_item="tool_call",
        supersedes_charge_id=target_id,
    )
    append_observation(ledger_conn, item)

    receipt_value = build_receipt(ledger_conn, run_id)
    economic = _profile_section(receipt_value, "economic-estimate")
    valuations = _valuation_rows(receipt_value)
    source_id = opaque_id("charge", item.observation_id)
    source = next(row for row in valuations if row["charge_id"] == source_id)

    assert target_id in {row["charge_id"] for row in valuations}
    assert source["supersession_valid"] is False
    assert economic["contradiction"] == "contradictory"


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


def test_same_span_id_in_two_traces_remains_isolated_and_rebuild_idempotent(ledger_conn):
    shared_span_id = "a" * 16
    first = CausalIdentity("c1", "1" * 32, "r1", shared_span_id, idempotency_key="one")
    second = CausalIdentity(
        "c2",
        "2" * 32,
        "r2",
        shared_span_id,
        source_sequence=1,
        idempotency_key="two",
    )
    when = datetime(2026, 1, 1, tzinfo=timezone.utc)
    for causal, meter_quantity in ((first, 1_000_000), (second, 2_000_000)):
        span = observation(
            producer="collision",
            event_kind="span",
            causal=causal,
            payload={"operation_kind": "model", "lifecycle": "completed"},
            occurred_at=when,
            observed_at=when,
        )
        meter = observation(
            producer="collision",
            event_kind="meter",
            causal=CausalIdentity(
                causal.conversation_id,
                causal.trace_id,
                causal.run_id,
                causal.span_id,
                source_sequence=causal.source_sequence + 10,
                idempotency_key=f"{causal.idempotency_key}-meter",
            ),
            payload={
                "meter_name": "tokens.output",
                "unit": "token",
                "quantity_micros": meter_quantity,
                "aggregation": "delta",
                "finality": "final",
            },
            occurred_at=when,
            observed_at=when,
        )
        assert append_observation(ledger_conn, span)
        assert append_observation(ledger_conn, meter)
        assert not append_observation(ledger_conn, meter)

    first_receipt = build_receipt(ledger_conn, first.normalized().run_id)
    second_receipt = build_receipt(ledger_conn, second.normalized().run_id)
    assert first_receipt["meter_facts"][0]["quantity_micros"] == 1_000_000  # type: ignore[index]
    assert second_receipt["meter_facts"][0]["quantity_micros"] == 2_000_000  # type: ignore[index]
    keys = {
        row[0]
        for row in ledger_conn.execute(
            "SELECT span_key FROM causal_spans WHERE span_id=?", (shared_span_id,)
        )
    }
    assert keys == {
        trace_scoped_span_key("1" * 32, shared_span_id),
        trace_scoped_span_key("2" * 32, shared_span_id),
    }

    before = (first_receipt, second_receipt)
    rebuild_projections(ledger_conn)
    assert before == (
        build_receipt(ledger_conn, first.normalized().run_id),
        build_receipt(ledger_conn, second.normalized().run_id),
    )


def test_trace_scoped_span_cannot_change_run_owner(ledger_conn):
    when = datetime(2026, 1, 1, tzinfo=timezone.utc)
    first = CausalIdentity("c", "1" * 32, "r1", "2" * 16, idempotency_key="one")
    conflicting = CausalIdentity(
        "c", "1" * 32, "r2", "2" * 16, source_sequence=1, idempotency_key="two"
    )
    for causal in (first, conflicting):
        item = observation(
            producer="owner",
            event_kind="span",
            causal=causal,
            payload={"operation_kind": "agent", "lifecycle": "completed"},
            occurred_at=when,
            observed_at=when,
        )
        if causal is first:
            assert append_observation(ledger_conn, item)
        else:
            with pytest.raises(ValueError, match="different run"):
                append_observation(ledger_conn, item)


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
    assert "structural:unknown" in listed.output
    assert "provider-billed:partial" in listed.output
    assert "evidence=complete" not in listed.output
    assert shown.exit_code == 0
    assert "Timing: unknown" in shown.output
    assert "critical path/service/wait/elapsed are not claimed" in shown.output


def test_receipt_does_not_treat_observation_latency_as_span_timing(ledger_conn):
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
    assert timing == {
        "state": "unknown",
        "basis": "explicit_span_timing_required",
        "critical_path": None,
        "service": None,
        "wait": None,
        "elapsed": None,
        "spans_total": 2,
        "spans_with_duration": 0,
    }


def test_enclosing_parent_and_child_are_union_counted_and_nontrivial_path_is_withheld(
    ledger_conn, monkeypatch
):
    start = datetime(2026, 1, 1, tzinfo=timezone.utc)
    base = CausalIdentity("c", "1" * 32, "timed", "2" * 16, idempotency_key="root")
    child = CausalIdentity(
        "c",
        "1" * 32,
        "timed",
        "3" * 16,
        parent_span_id="2" * 16,
        source_sequence=1,
        idempotency_key="child",
    )
    for causal, kind, offset_start, offset_end in (
        (base, "agent", 0, 10),
        (child, "model", 2, 8),
    ):
        append_observation(
            ledger_conn,
            observation(
                producer="timing",
                event_kind="span",
                causal=causal,
                payload={
                    "operation_kind": kind,
                    "lifecycle": "completed",
                    "started_at": (start + timedelta(seconds=offset_start)).isoformat(),
                    "ended_at": (start + timedelta(seconds=offset_end)).isoformat(),
                    "timing_source": "explicit_interval",
                },
                # These are event/ingest times and intentionally differ from the interval.
                occurred_at=start + timedelta(seconds=20 + offset_start),
                observed_at=start + timedelta(seconds=40 + offset_end),
            ),
        )

    timing = build_receipt(ledger_conn, base.normalized().run_id)["timing_micros"]
    assert isinstance(timing, dict)
    assert timing["state"] == "partial"
    assert timing["basis"] == (
        "explicit_interval_unions_and_elapsed_envelope;"
        "critical_path_withheld_untyped_execution_edges"
    )
    assert timing["critical_path"] is None
    assert timing["service"] == 10_000_000
    assert timing["wait"] == 0
    assert timing["elapsed"] == 10_000_000

    monkeypatch.setattr("forecost.commands.runs_cmd.get_ledger_db", lambda: ledger_conn)
    shown = CliRunner().invoke(show_run, [base.normalized().run_id])
    assert shown.exit_code == 0, shown.output
    assert "service 10000000us" in shown.output
    assert "elapsed 10000000us" in shown.output
    assert "critical path withheld (untyped scheduling dependencies)" in shown.output
    assert "Noneus" not in shown.output


def test_single_span_has_the_only_currently_justified_critical_path(ledger_conn):
    start = datetime(2026, 1, 1, tzinfo=timezone.utc)
    causal = _append_timed_span(
        ledger_conn,
        index=1,
        start=start,
        start_seconds=0,
        end_seconds=4,
    )

    timing = build_receipt(ledger_conn, causal.run_id)["timing_micros"]

    assert timing == {
        "state": "complete",
        "basis": (
            "explicit_interval_unions_and_elapsed_envelope;critical_path_trivial_single_span"
        ),
        "critical_path": 4_000_000,
        "service": 4_000_000,
        "wait": 0,
        "elapsed": 4_000_000,
        "spans_total": 1,
        "spans_with_duration": 1,
    }


def test_sequential_siblings_do_not_produce_an_undercounted_critical_path(ledger_conn):
    start = datetime(2026, 1, 1, tzinfo=timezone.utc)
    root = _append_timed_span(
        ledger_conn,
        index=1,
        start=start,
        start_seconds=0,
        end_seconds=12,
    )
    _append_timed_span(
        ledger_conn,
        index=2,
        start=start,
        start_seconds=1,
        end_seconds=4,
        parent_index=1,
    )
    _append_timed_span(
        ledger_conn,
        index=3,
        start=start,
        start_seconds=6,
        end_seconds=10,
        parent_index=1,
    )

    timing = _timing_section(build_receipt(ledger_conn, root.run_id))

    assert timing["critical_path"] is None
    assert timing["service"] == 12_000_000
    assert timing["elapsed"] == 12_000_000


def test_disjoint_intervals_union_service_but_elapsed_envelope_includes_gap(ledger_conn):
    start = datetime(2026, 1, 1, tzinfo=timezone.utc)
    first = _append_timed_span(
        ledger_conn,
        index=1,
        start=start,
        start_seconds=0,
        end_seconds=2,
    )
    _append_timed_span(
        ledger_conn,
        index=2,
        start=start,
        start_seconds=5,
        end_seconds=7,
    )

    timing = _timing_section(build_receipt(ledger_conn, first.run_id))

    assert timing["service"] == 4_000_000
    assert timing["elapsed"] == 7_000_000
    assert timing["critical_path"] is None


def test_adjacent_intervals_form_one_continuous_service_union(ledger_conn):
    start = datetime(2026, 1, 1, tzinfo=timezone.utc)
    first = _append_timed_span(
        ledger_conn,
        index=1,
        start=start,
        start_seconds=0,
        end_seconds=2,
    )
    _append_timed_span(
        ledger_conn,
        index=2,
        start=start,
        start_seconds=2,
        end_seconds=5,
    )

    timing = _timing_section(build_receipt(ledger_conn, first.run_id))

    assert timing["service"] == 5_000_000
    assert timing["elapsed"] == 5_000_000


def test_parallel_intervals_do_not_double_count_service_wall_coverage(ledger_conn):
    start = datetime(2026, 1, 1, tzinfo=timezone.utc)
    first = _append_timed_span(
        ledger_conn,
        index=1,
        start=start,
        start_seconds=0,
        end_seconds=10,
    )
    _append_timed_span(
        ledger_conn,
        index=2,
        start=start,
        start_seconds=2,
        end_seconds=8,
    )

    timing = _timing_section(build_receipt(ledger_conn, first.run_id))

    assert timing["service"] == 10_000_000
    assert timing["elapsed"] == 10_000_000
    assert timing["critical_path"] is None


def test_wait_and_service_are_independent_unions_and_are_not_additive(ledger_conn):
    start = datetime(2026, 1, 1, tzinfo=timezone.utc)
    root = _append_timed_span(
        ledger_conn,
        index=1,
        start=start,
        start_seconds=0,
        end_seconds=10,
        operation_kind="agent",
    )
    _append_timed_span(
        ledger_conn,
        index=2,
        start=start,
        start_seconds=2,
        end_seconds=8,
        parent_index=1,
        operation_kind="queue_wait",
    )
    _append_timed_span(
        ledger_conn,
        index=3,
        start=start,
        start_seconds=4,
        end_seconds=7,
        parent_index=1,
        operation_kind="queue_wait",
    )

    timing = _timing_section(build_receipt(ledger_conn, root.run_id))

    assert timing["service"] == 10_000_000
    assert timing["wait"] == 6_000_000
    assert timing["elapsed"] == 10_000_000
    assert "service/wait not additive" in receipt_text(build_receipt(ledger_conn, root.run_id))


def test_fan_in_does_not_add_overlapping_predecessor_intervals(ledger_conn):
    start = datetime(2026, 1, 1, tzinfo=timezone.utc)
    first = _append_timed_span(
        ledger_conn,
        index=1,
        start=start,
        start_seconds=0,
        end_seconds=4,
    )
    _append_timed_span(
        ledger_conn,
        index=2,
        start=start,
        start_seconds=0,
        end_seconds=6,
    )
    _append_timed_span(
        ledger_conn,
        index=3,
        start=start,
        start_seconds=6,
        end_seconds=8,
        link_indexes=(1, 2),
    )

    receipt_value = build_receipt(ledger_conn, first.run_id)
    timing = _timing_section(receipt_value)
    evidence = _mapping(receipt_value["evidence"])

    assert timing["service"] == 8_000_000
    assert timing["elapsed"] == 8_000_000
    assert timing["critical_path"] is None
    assert "causal_cycle" not in _string_list(evidence["known_blind_spots"])


def test_causal_cycle_invalidates_path_but_not_observed_interval_unions(ledger_conn):
    start = datetime(2026, 1, 1, tzinfo=timezone.utc)
    first = _append_timed_span(
        ledger_conn,
        index=1,
        start=start,
        start_seconds=0,
        end_seconds=3,
        parent_index=2,
    )
    _append_timed_span(
        ledger_conn,
        index=2,
        start=start,
        start_seconds=1,
        end_seconds=4,
        parent_index=1,
    )

    receipt_value = build_receipt(ledger_conn, first.run_id)
    timing = _timing_section(receipt_value)
    evidence = _mapping(receipt_value["evidence"])

    assert timing["state"] == "invalid"
    assert timing["critical_path"] is None
    assert timing["service"] == 4_000_000
    assert timing["elapsed"] == 4_000_000
    assert "causal_cycle" in _string_list(evidence["known_blind_spots"])


def test_completed_graph_with_parent_cycle_cannot_claim_clear_structural_closure(ledger_conn):
    start = datetime(2026, 1, 1, tzinfo=timezone.utc)
    root = _append_timed_span(
        ledger_conn,
        index=1,
        start=start,
        start_seconds=0,
        end_seconds=5,
    )
    _append_timed_span(
        ledger_conn,
        index=2,
        start=start,
        start_seconds=1,
        end_seconds=3,
        parent_index=3,
    )
    _append_timed_span(
        ledger_conn,
        index=3,
        start=start,
        start_seconds=2,
        end_seconds=4,
        parent_index=2,
    )

    receipt_value = build_receipt(ledger_conn, root.run_id)
    evidence = _mapping(receipt_value["evidence"])
    structural = _profile_section(receipt_value, "structural")

    assert "causal_cycle" in _string_list(evidence["known_blind_spots"])
    assert structural["completeness"] == "partial"
    assert structural["contradiction"] == "contradictory"
    assert structural["state"] == "contradictory"
    closure = next(
        item for item in _profile_obligations(structural) if item["key"] == "branch_closure"
    )
    assert closure["contradictory"] is True
    assert closure["satisfied"] is False


def test_completed_orphan_span_cannot_satisfy_structural_closure(ledger_conn):
    start = datetime(2026, 1, 1, tzinfo=timezone.utc)
    root = _append_timed_span(
        ledger_conn,
        index=1,
        start=start,
        start_seconds=0,
        end_seconds=5,
    )
    _append_timed_span(
        ledger_conn,
        index=2,
        start=start,
        start_seconds=1,
        end_seconds=3,
        parent_index=99,
    )

    receipt_value = build_receipt(ledger_conn, root.run_id)
    evidence = _mapping(receipt_value["evidence"])
    structural = _profile_section(receipt_value, "structural")

    assert "missing_parent" in _string_list(evidence["known_blind_spots"])
    assert structural["completeness"] == "partial"
    assert structural["contradiction"] == "unknown"
    assert "branch_closure" in _string_list(structural["unmet_obligations"])


def test_completed_graph_with_missing_fan_in_target_cannot_satisfy_structural_closure(
    ledger_conn,
):
    start = datetime(2026, 1, 1, tzinfo=timezone.utc)
    root = _append_timed_span(
        ledger_conn,
        index=1,
        start=start,
        start_seconds=0,
        end_seconds=5,
        link_indexes=(99,),
    )

    receipt_value = build_receipt(ledger_conn, root.run_id)
    evidence = _mapping(receipt_value["evidence"])
    structural = _profile_section(receipt_value, "structural")

    assert "missing_link_target" in _string_list(evidence["known_blind_spots"])
    assert structural["completeness"] == "partial"
    assert structural["contradiction"] == "unknown"
    assert "branch_closure" in _string_list(structural["unmet_obligations"])


def test_completed_graph_with_missing_retry_target_cannot_satisfy_structural_closure(
    ledger_conn,
):
    start = datetime(2026, 1, 1, tzinfo=timezone.utc)
    root = _append_timed_span(
        ledger_conn,
        index=1,
        start=start,
        start_seconds=0,
        end_seconds=5,
        attempt_of_index=99,
    )

    receipt_value = build_receipt(ledger_conn, root.run_id)
    evidence = _mapping(receipt_value["evidence"])
    structural = _profile_section(receipt_value, "structural")

    assert "missing_attempt_target" in _string_list(evidence["known_blind_spots"])
    assert structural["completeness"] == "partial"
    assert structural["contradiction"] == "unknown"
    assert "branch_closure" in _string_list(structural["unmet_obligations"])


def test_completed_retry_lineage_cycle_is_structurally_contradictory(ledger_conn):
    start = datetime(2026, 1, 1, tzinfo=timezone.utc)
    first = _append_timed_span(
        ledger_conn,
        index=1,
        start=start,
        start_seconds=0,
        end_seconds=3,
        attempt_of_index=2,
    )
    _append_timed_span(
        ledger_conn,
        index=2,
        start=start,
        start_seconds=1,
        end_seconds=4,
        attempt_of_index=1,
    )

    receipt_value = build_receipt(ledger_conn, first.run_id)
    evidence = _mapping(receipt_value["evidence"])
    structural = _profile_section(receipt_value, "structural")

    assert "retry_lineage_cycle" in _string_list(evidence["known_blind_spots"])
    assert structural["completeness"] == "partial"
    assert structural["contradiction"] == "contradictory"
    assert structural["state"] == "contradictory"


def test_missing_end_time_keeps_aggregate_timing_unknown(ledger_conn):
    start = datetime(2026, 1, 1, tzinfo=timezone.utc)
    causal = CausalIdentity("c", "4" * 32, "missing-end", "5" * 16)
    append_observation(
        ledger_conn,
        observation(
            producer="timing",
            event_kind="span",
            causal=causal,
            payload={
                "operation_kind": "model",
                "lifecycle": "running",
                "started_at": start.isoformat(),
                "timing_source": "explicit_interval",
            },
            occurred_at=start,
            observed_at=start + timedelta(seconds=30),
        ),
    )

    timing = build_receipt(ledger_conn, causal.normalized().run_id)["timing_micros"]
    assert isinstance(timing, dict)
    assert timing["state"] == "unknown"
    assert timing["critical_path"] is None
    assert timing["service"] is None
    assert timing["spans_with_duration"] == 0


def test_incomplete_lifecycle_does_not_satisfy_structural_branch_closure(ledger_conn):
    when = datetime(2026, 1, 1, tzinfo=timezone.utc)
    causal = CausalIdentity("c", "6" * 32, "unfinished", "7" * 16)
    append_observation(
        ledger_conn,
        observation(
            producer="otel",
            event_kind="span",
            causal=causal,
            payload={"operation_kind": "agent", "lifecycle": "incomplete"},
            occurred_at=when,
            observed_at=when,
        ),
    )

    receipt_value = build_receipt(ledger_conn, causal.normalized().run_id)
    structural = receipt_value["evidence"]["claim_profiles"]["structural"]  # type: ignore[index]
    assert structural["completeness"] == "partial"
    assert "branch_closure" in structural["unmet_obligations"]


def test_structural_profile_uses_source_observation_time_and_abstains_without_freshness_sla(
    ledger_conn,
):
    observed = datetime(2026, 1, 1, 2, tzinfo=timezone.utc)
    causal = CausalIdentity("c", "7" * 32, "structural-time", "8" * 16)
    append_observation(
        ledger_conn,
        observation(
            producer="otel",
            event_kind="span",
            causal=causal,
            payload={"operation_kind": "agent", "lifecycle": "completed"},
            occurred_at=observed - timedelta(hours=1),
            observed_at=observed,
        ),
    )
    run_id = causal.normalized().run_id

    signals = _structural_signals(_load_receipt_rows(ledger_conn, run_id))
    receipt_value = build_receipt(ledger_conn, run_id)
    structural = receipt_value["evidence"]["claim_profiles"]["structural"]  # type: ignore[index]

    assert {signal.observed_at for signal in signals} == {observed}
    assert structural["completeness"] == "complete"
    assert structural["freshness"] == "unknown"
    assert structural["state"] == "unknown"
    assert structural["profile_version"] == 1
    assert set(structural["reason_codes"]) == {"satisfied_freshness_not_declared"}
    assert all(item["fresh"] is None for item in structural["obligations"])


def test_later_lifecycle_regression_is_contradictory_and_advances_receipt_assessment_time(
    ledger_conn,
):
    first_time = datetime(2026, 1, 1, tzinfo=timezone.utc)
    later_time = first_time + timedelta(seconds=10)
    completed = CausalIdentity(
        "c",
        "8" * 32,
        "lifecycle-conflict",
        "9" * 16,
        source_sequence=1,
        idempotency_key="completed",
    )
    running = CausalIdentity(
        "c",
        "8" * 32,
        "lifecycle-conflict",
        "9" * 16,
        source_sequence=2,
        idempotency_key="running-again",
    )
    append_observation(
        ledger_conn,
        observation(
            producer="otel",
            event_kind="span",
            causal=completed,
            payload={"operation_kind": "agent", "lifecycle": "completed"},
            occurred_at=first_time,
            observed_at=first_time,
        ),
    )
    append_observation(
        ledger_conn,
        observation(
            producer="offline_lab",
            event_kind="span",
            causal=running,
            payload={"operation_kind": "agent", "lifecycle": "running"},
            occurred_at=later_time,
            observed_at=later_time,
        ),
    )

    receipt_value = build_receipt(ledger_conn, completed.normalized().run_id)
    structural = receipt_value["evidence"]["claim_profiles"]["structural"]  # type: ignore[index]

    assert receipt_value["as_of"] == later_time.isoformat()
    assert structural["as_of"] == later_time.isoformat()
    assert structural["contradiction"] == "contradictory"
    assert structural["completeness"] == "partial"
    assert structural["state"] == "contradictory"
    assert "required_evidence_contradictory" in structural["reason_codes"]
    closure = next(item for item in structural["obligations"] if item["key"] == "branch_closure")
    assert closure["contradictory"] is True
    assert closure["satisfied"] is False


def test_incompatible_active_outcomes_make_outcome_profile_contradictory(ledger_conn):
    start = datetime(2026, 1, 1, tzinfo=timezone.utc)
    causal = _append_timed_span(
        ledger_conn,
        index=1,
        start=start,
        start_seconds=0,
        end_seconds=1,
        run_id="outcome-conflict",
    )
    for sequence, status in ((2, "good"), (3, "bad")):
        append_observation(
            ledger_conn,
            observation(
                producer="manual_mark",
                event_kind="outcome",
                causal=CausalIdentity(
                    causal.conversation_id,
                    causal.trace_id,
                    causal.run_id,
                    causal.span_id,
                    source_sequence=sequence,
                    idempotency_key=f"outcome-{status}",
                ),
                payload={
                    "outcome_status": status,
                    "evidence_type": "explicit_mark",
                    "confidence": "explicit",
                },
                occurred_at=start + timedelta(seconds=sequence),
                observed_at=start + timedelta(seconds=sequence),
            ),
        )

    receipt_value = build_receipt(ledger_conn, causal.run_id)
    profile = _profile_section(receipt_value, "outcome")
    outcome_evidence = receipt_value["outcome_evidence"]
    assert isinstance(outcome_evidence, list)

    assert len(outcome_evidence) == 2
    assert _mapping(receipt_value["outcome"])["status"] == "unknown"
    assert all(_mapping(item)["active"] is True for item in outcome_evidence)
    assert profile["completeness"] == "partial"
    assert profile["contradiction"] == "contradictory"
    assert profile["state"] == "contradictory"
    unmet = profile["unmet_obligations"]
    reasons = profile["reason_codes"]
    assert isinstance(unmet, list)
    assert isinstance(reasons, list)
    assert set(unmet) == {"outcome_identity", "outcome_result"}
    assert "required_evidence_contradictory" in reasons


def test_active_test_failure_and_human_success_are_contradictory(ledger_conn):
    start = datetime(2026, 1, 1, tzinfo=timezone.utc)
    causal = _append_timed_span(
        ledger_conn,
        index=1,
        start=start,
        start_seconds=0,
        end_seconds=1,
        run_id="cross-role-outcome-conflict",
    )
    for sequence, status, evidence_type in (
        (2, "bad", "test_exit"),
        (3, "good", "explicit_mark"),
    ):
        append_observation(
            ledger_conn,
            observation(
                producer="outcome-source-conflict",
                event_kind="outcome",
                causal=CausalIdentity(
                    causal.conversation_id,
                    causal.trace_id,
                    causal.run_id,
                    causal.span_id,
                    source_sequence=sequence,
                    idempotency_key=f"{evidence_type}-{status}",
                ),
                payload={
                    "outcome_status": status,
                    "evidence_type": evidence_type,
                    "confidence": "explicit" if evidence_type == "explicit_mark" else "observed",
                },
                occurred_at=start + timedelta(seconds=sequence),
                observed_at=start + timedelta(seconds=sequence),
            ),
        )

    receipt_value = build_receipt(ledger_conn, causal.run_id)
    profile = _profile_section(receipt_value, "outcome")

    assert _mapping(receipt_value["outcome"])["status"] == "unknown"
    assert profile["contradiction"] == "contradictory"
    assert profile["state"] == "contradictory"


def test_human_outcome_cannot_supersede_independent_test_evidence(ledger_conn):
    start = datetime(2026, 1, 1, tzinfo=timezone.utc)
    causal = _append_timed_span(
        ledger_conn,
        index=1,
        start=start,
        start_seconds=0,
        end_seconds=1,
        run_id="cross-role-outcome-supersession",
    )
    test_outcome = observation(
        producer="outcome-source-conflict",
        event_kind="outcome",
        causal=CausalIdentity(
            causal.conversation_id,
            causal.trace_id,
            causal.run_id,
            causal.span_id,
            source_sequence=2,
            idempotency_key="test-bad",
        ),
        payload={
            "outcome_status": "bad",
            "evidence_type": "test_exit",
            "confidence": "observed",
        },
        occurred_at=start + timedelta(seconds=2),
        observed_at=start + timedelta(seconds=2),
    )
    append_observation(ledger_conn, test_outcome)
    test_evidence_id = opaque_id("outcome", test_outcome.observation_id)
    append_observation(
        ledger_conn,
        observation(
            producer="manual_mark",
            event_kind="outcome",
            causal=CausalIdentity(
                causal.conversation_id,
                causal.trace_id,
                causal.run_id,
                causal.span_id,
                source_sequence=3,
                idempotency_key="human-bad-invalid-supersession",
            ),
            payload={
                "outcome_status": "bad",
                "evidence_type": "explicit_mark",
                "confidence": "explicit",
                "supersedes_evidence_id": test_evidence_id,
            },
            occurred_at=start + timedelta(seconds=3),
            observed_at=start + timedelta(seconds=3),
        ),
    )

    receipt_value = build_receipt(ledger_conn, causal.run_id)
    profile = _profile_section(receipt_value, "outcome")
    outcome_evidence = _mapping_list(receipt_value["outcome_evidence"])

    assert all(item["active"] is True for item in outcome_evidence)
    human = next(item for item in outcome_evidence if item["evidence_type"] == "explicit_mark")
    assert human["supersession_valid"] is False
    assert profile["contradiction"] == "contradictory"
    assert _mapping(receipt_value["outcome"])["status"] == "unknown"


def test_explicit_outcome_supersession_retires_only_referenced_outcome_for_assessment(
    ledger_conn,
):
    start = datetime(2026, 1, 1, tzinfo=timezone.utc)
    causal = _append_timed_span(
        ledger_conn,
        index=1,
        start=start,
        start_seconds=0,
        end_seconds=1,
        run_id="outcome-supersession",
    )
    first = CausalIdentity(
        causal.conversation_id,
        causal.trace_id,
        causal.run_id,
        causal.span_id,
        source_sequence=2,
        idempotency_key="outcome-good",
    )
    append_observation(
        ledger_conn,
        observation(
            producer="manual_mark",
            event_kind="outcome",
            causal=first,
            payload={
                "outcome_status": "good",
                "evidence_type": "explicit_mark",
                "confidence": "explicit",
            },
            occurred_at=start + timedelta(seconds=2),
            observed_at=start + timedelta(seconds=2),
        ),
    )
    first_evidence_id = ledger_conn.execute(
        "SELECT evidence_id FROM outcome_evidence WHERE run_id = ?",
        (causal.run_id,),
    ).fetchone()[0]
    append_observation(
        ledger_conn,
        observation(
            producer="manual_mark",
            event_kind="outcome",
            causal=CausalIdentity(
                causal.conversation_id,
                causal.trace_id,
                causal.run_id,
                causal.span_id,
                source_sequence=3,
                idempotency_key="outcome-bad-correction",
            ),
            payload={
                "outcome_status": "bad",
                "evidence_type": "explicit_mark",
                "confidence": "explicit",
                "supersedes_evidence_id": first_evidence_id,
            },
            occurred_at=start + timedelta(seconds=3),
            observed_at=start + timedelta(seconds=3),
        ),
    )

    receipt_value = build_receipt(ledger_conn, causal.run_id)
    profile = _profile_section(receipt_value, "outcome")
    outcome_evidence = receipt_value["outcome_evidence"]
    outcome = _mapping(receipt_value["outcome"])
    assert isinstance(outcome_evidence, list)

    assert len(outcome_evidence) == 2
    assert outcome["status"] == "bad"
    assert [(_mapping(item)["status"], _mapping(item)["active"]) for item in outcome_evidence] == [
        ("good", False),
        ("bad", True),
    ]
    assert [
        _mapping(item)["supersession_valid"]
        for item in outcome_evidence
        if _mapping(item)["supersedes_evidence_id"] is not None
    ] == [True]
    assert profile["completeness"] == "complete"
    assert profile["freshness"] == "unknown"
    assert profile["contradiction"] == "clear"
    assert profile["state"] == "unknown"


def test_forward_outcome_supersession_stays_active_and_is_contradictory(ledger_conn):
    start = datetime(2026, 1, 1, tzinfo=timezone.utc)
    causal = _append_timed_span(
        ledger_conn,
        index=1,
        start=start,
        start_seconds=0,
        end_seconds=1,
        run_id="outcome-forward-supersession",
    )
    future = observation(
        producer="manual_mark",
        event_kind="outcome",
        causal=CausalIdentity(
            causal.conversation_id,
            causal.trace_id,
            causal.run_id,
            causal.span_id,
            source_sequence=3,
            idempotency_key="future-bad",
        ),
        payload={
            "outcome_status": "bad",
            "evidence_type": "explicit_mark",
            "confidence": "explicit",
        },
        occurred_at=start + timedelta(seconds=3),
        observed_at=start + timedelta(seconds=3),
    )
    future_evidence_id = opaque_id("outcome", future.observation_id)
    earlier = observation(
        producer="manual_mark",
        event_kind="outcome",
        causal=CausalIdentity(
            causal.conversation_id,
            causal.trace_id,
            causal.run_id,
            causal.span_id,
            source_sequence=2,
            idempotency_key="earlier-good-forward-reference",
        ),
        payload={
            "outcome_status": "good",
            "evidence_type": "explicit_mark",
            "confidence": "explicit",
            "supersedes_evidence_id": future_evidence_id,
        },
        occurred_at=start + timedelta(seconds=2),
        observed_at=start + timedelta(seconds=2),
    )
    append_observation(ledger_conn, earlier)
    append_observation(ledger_conn, future)

    receipt_value = build_receipt(ledger_conn, causal.run_id)
    profile = _profile_section(receipt_value, "outcome")
    outcome_evidence = receipt_value["outcome_evidence"]
    assert isinstance(outcome_evidence, list)

    assert _mapping(receipt_value["outcome"])["status"] == "unknown"
    assert profile["contradiction"] == "contradictory"
    assert profile["state"] == "contradictory"
    assert all(_mapping(item)["active"] is True for item in outcome_evidence)
    forward = next(
        _mapping(item)
        for item in outcome_evidence
        if _mapping(item)["supersedes_evidence_id"] is not None
    )
    assert forward["supersession_valid"] is False


def test_missing_outcome_supersession_target_stays_active_and_is_contradictory(ledger_conn):
    start = datetime(2026, 1, 1, tzinfo=timezone.utc)
    causal = _append_timed_span(
        ledger_conn,
        index=1,
        start=start,
        start_seconds=0,
        end_seconds=1,
        run_id="outcome-missing-supersession",
    )
    append_observation(
        ledger_conn,
        observation(
            producer="manual_mark",
            event_kind="outcome",
            causal=CausalIdentity(
                causal.conversation_id,
                causal.trace_id,
                causal.run_id,
                causal.span_id,
                source_sequence=2,
                idempotency_key="missing-outcome-reference",
            ),
            payload={
                "outcome_status": "good",
                "evidence_type": "explicit_mark",
                "confidence": "explicit",
                "supersedes_evidence_id": opaque_id("outcome", "absent-target"),
            },
            occurred_at=start + timedelta(seconds=2),
            observed_at=start + timedelta(seconds=2),
        ),
    )

    receipt_value = build_receipt(ledger_conn, causal.run_id)
    profile = _profile_section(receipt_value, "outcome")
    outcome_evidence = _mapping_list(receipt_value["outcome_evidence"])

    assert outcome_evidence[0]["active"] is True
    assert outcome_evidence[0]["supersession_valid"] is False
    assert profile["contradiction"] == "contradictory"
    assert _mapping(receipt_value["outcome"])["status"] == "unknown"


def test_cross_run_outcome_supersession_is_contradictory(ledger_conn):
    start = datetime(2026, 1, 1, tzinfo=timezone.utc)
    first = _append_timed_span(
        ledger_conn,
        index=1,
        start=start,
        start_seconds=0,
        end_seconds=1,
        run_id="outcome-source-run",
    )
    source_outcome = observation(
        producer="manual_mark",
        event_kind="outcome",
        causal=CausalIdentity(
            first.conversation_id,
            first.trace_id,
            first.run_id,
            first.span_id,
            source_sequence=2,
            idempotency_key="source-good",
        ),
        payload={
            "outcome_status": "good",
            "evidence_type": "explicit_mark",
            "confidence": "explicit",
        },
        occurred_at=start + timedelta(seconds=2),
        observed_at=start + timedelta(seconds=2),
    )
    append_observation(ledger_conn, source_outcome)
    source_id = opaque_id("outcome", source_outcome.observation_id)
    second = _append_timed_span(
        ledger_conn,
        index=3,
        start=start,
        start_seconds=0,
        end_seconds=1,
        run_id="outcome-target-run",
    )
    append_observation(
        ledger_conn,
        observation(
            producer="manual_mark",
            event_kind="outcome",
            causal=CausalIdentity(
                second.conversation_id,
                second.trace_id,
                second.run_id,
                second.span_id,
                source_sequence=4,
                idempotency_key="cross-run-reference",
            ),
            payload={
                "outcome_status": "good",
                "evidence_type": "explicit_mark",
                "confidence": "explicit",
                "supersedes_evidence_id": source_id,
            },
            occurred_at=start + timedelta(seconds=4),
            observed_at=start + timedelta(seconds=4),
        ),
    )

    receipt_value = build_receipt(ledger_conn, second.run_id)
    profile = _profile_section(receipt_value, "outcome")
    outcome_evidence = receipt_value["outcome_evidence"]
    assert isinstance(outcome_evidence, list)

    assert profile["contradiction"] == "contradictory"
    assert _mapping(receipt_value["outcome"])["status"] == "unknown"
    assert _mapping(outcome_evidence[0])["supersession_valid"] is False


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
    assert evidence["legacy_projection_state"] == "incomplete"
    assert "missing-source" in evidence["known_blind_spots"]
    structural = evidence["claim_profiles"]["structural"]
    assert structural["completeness"] == "partial"
    assert structural["contradiction"] == "unknown"
    assert "branch_closure" in structural["unmet_obligations"]

    rendered = CliRunner().invoke(receipt, [run_id, "--no-color"])
    assert rendered.exit_code == 0
    assert "\x1b[" not in rendered.output
