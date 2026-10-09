from __future__ import annotations

import copy
import hashlib
import json
import sqlite3
from collections.abc import Iterator, Mapping
from datetime import datetime, timezone
from typing import cast

import pytest

from forecost.comparison import (
    ComparisonConfigurationError,
    compare_manifests,
    compare_runs_diagnostic,
    comparison_exit_code,
    comparison_text,
)
from forecost.ledger.contracts import CausalIdentity, opaque_id
from forecost.ledger.db import get_ledger_db, get_readonly_ledger_db
from forecost.ledger.evidence import append_observation, observation
from forecost.ledger.integrity import initialize_journal_chain
from forecost.ledger.receipts import build_receipt
from forecost.ledger.schema import apply_schema

_WHEN = datetime(2026, 8, 13, tzinfo=timezone.utc)
_DATASET_DIGEST = hashlib.sha256(b"dataset-v1").hexdigest()
_TASK_SET_DIGEST = hashlib.sha256(b"task-set-v1").hexdigest()
_BASE_CONFIG = hashlib.sha256(b"baseline-config-v1").hexdigest()
_CANDIDATE_CONFIG = hashlib.sha256(b"candidate-config-v1").hexdigest()
_SOURCE_ID = opaque_id("producer", "offline_lab")


def _sha(value: object) -> str:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(encoded.encode()).hexdigest()


# amount = quantity_micros * rate // 10**12, so rate 10**12 makes quantity == amount.
_UNIT_RATE = 10**12


def _identity(name: str, sequence: int, suffix: str) -> CausalIdentity:
    digest = hashlib.sha256(name.encode()).hexdigest()
    return CausalIdentity(
        f"conversation-{name}",
        digest[:32],
        name,
        digest[32:48],
        source_sequence=sequence,
        idempotency_key=f"{name}-{suffix}",
    )


def _append_run(
    conn: sqlite3.Connection,
    name: str,
    amount_micros: int,
    outcome_status: str,
    *,
    tariff_name: str = "tariff-v1",
    authority: str = "list_rate",
    charge_finality: str = "final",
    lifecycle: str = "completed",
    outcome_type: str = "test_exit",
    outcome_confidence: str = "observed",
    tariff_payload: Mapping[str, object] | None = None,
    bind_charge_to_meter: bool = True,
) -> dict[str, str]:
    span_identity = _identity(name, 1, "span")
    append_observation(
        conn,
        observation(
            producer="offline_lab",
            event_kind="span",
            causal=span_identity,
            payload={"operation_kind": "agent", "lifecycle": lifecycle},
            occurred_at=_WHEN,
            observed_at=_WHEN,
        ),
    )
    meter = observation(
        producer="offline_lab",
        event_kind="meter",
        causal=_identity(name, 2, "meter"),
        payload={
            "meter_name": "tokens.output",
            "unit": "token",
            "quantity_micros": amount_micros,
            "aggregation": "delta",
            "finality": "final",
        },
        occurred_at=_WHEN,
        observed_at=_WHEN,
    )
    append_observation(conn, meter)
    append_observation(
        conn,
        observation(
            producer="offline_lab",
            event_kind="charge",
            causal=_identity(name, 3, "charge"),
            payload={
                "fact_id": (
                    opaque_id("fact", meter.observation_id)
                    if bind_charge_to_meter
                    else opaque_id("fact", f"unbound:{name}")
                ),
                "amount_micros": amount_micros,
                "currency": "USD",
                "authority": authority,
                "line_item": "model_inference",
                "tariff": (
                    dict(tariff_payload)
                    if tariff_payload is not None
                    else {"rate_snapshot": tariff_name, "output_rate_micros": _UNIT_RATE}
                ),
                "finality": charge_finality,
            },
            occurred_at=_WHEN,
            observed_at=_WHEN,
        ),
    )
    append_observation(
        conn,
        observation(
            producer="offline_lab",
            event_kind="outcome",
            causal=_identity(name, 4, "outcome"),
            payload={
                "outcome_status": outcome_status,
                "evidence_type": outcome_type,
                "confidence": outcome_confidence,
            },
            occurred_at=_WHEN,
            observed_at=_WHEN,
        ),
    )
    run_id = span_identity.normalized().run_id
    receipt = build_receipt(conn, run_id)
    receipt_integrity = cast(Mapping[str, object], receipt["integrity"])
    evidence_rows = cast(list[dict[str, object]], receipt["outcome_evidence"])
    tariff_json = conn.execute(
        "SELECT c.tariff_json FROM charges c JOIN causal_spans s "
        "ON s.span_key = c.span_key WHERE s.run_id = ?",
        (run_id,),
    ).fetchone()[0]
    return {
        "run_id": run_id,
        "receipt_digest": str(receipt_integrity["payload_digest"]),
        "outcome_evidence_id": str(evidence_rows[0]["evidence_id"]),
        "outcome_source_id": _SOURCE_ID,
        "tariff_digest": _sha(json.loads(str(tariff_json))),
    }


def _append_extra_meter(
    conn: sqlite3.Connection,
    name: str,
    *,
    aggregation: str = "delta",
    finality: str = "final",
    charge_amount_micros: int | None = None,
) -> None:
    meter = observation(
        producer="offline_lab",
        event_kind="meter",
        causal=_identity(name, 10, f"extra-meter-{aggregation}-{finality}"),
        payload={
            "meter_name": "tokens.output",
            "unit": "token",
            "quantity_micros": 999_000_000,
            "aggregation": aggregation,
            "finality": finality,
        },
        occurred_at=_WHEN,
        observed_at=_WHEN,
    )
    append_observation(conn, meter)
    if charge_amount_micros is not None:
        append_observation(
            conn,
            observation(
                producer="offline_lab",
                event_kind="charge",
                causal=_identity(name, 11, f"extra-charge-{aggregation}-{finality}"),
                payload={
                    "fact_id": opaque_id("fact", meter.observation_id),
                    "amount_micros": charge_amount_micros,
                    "currency": "USD",
                    "authority": "list_rate",
                    "line_item": "model_inference",
                    "tariff": {"rate_snapshot": "tariff-v1"},
                    "finality": "final",
                },
                occurred_at=_WHEN,
                observed_at=_WHEN,
            ),
        )


def _refresh_manifest_receipts(conn: sqlite3.Connection, manifest: dict[str, object]) -> None:
    for case in cast(list[dict[str, object]], manifest["cases"]):
        receipt = build_receipt(conn, str(case["run_id"]))
        case["receipt_digest"] = cast(Mapping[str, object], receipt["integrity"])["payload_digest"]
    _redigest(manifest)


def _case(
    index: int, arm: str, run: Mapping[str, str], configuration_digest: str
) -> dict[str, object]:
    return {
        "case_id": f"case-{index:04d}",
        "task_version": "task-v1",
        "attempt_id": f"attempt-{arm}-{index:04d}",
        "pair_id": f"pair-{index:04d}",
        "evaluator_id": "evaluator-v1",
        "verifier_id": "verifier-tests",
        "verifier_version": "verifier-v1",
        "outcome_source_id": run["outcome_source_id"],
        "outcome_evidence_id": run["outcome_evidence_id"],
        "run_id": run["run_id"],
        "receipt_digest": run["receipt_digest"],
        "tariff_digest": run["tariff_digest"],
        "configuration_digest": configuration_digest,
    }


def _manifest(arm: str, cases: list[dict[str, object]]) -> dict[str, object]:
    configuration = _BASE_CONFIG if arm == "baseline" else _CANDIDATE_CONFIG
    result: dict[str, object] = {
        "schema": "forecost.compare-arm/1",
        "arm": arm,
        "manifest_digest": "0" * 64,
        "dataset_digest": _DATASET_DIGEST,
        "task_set_digest": _TASK_SET_DIGEST,
        "configuration_digest": configuration,
        "privacy_profile": "metadata_minimized_v1",
        "source_ids": [_SOURCE_ID],
        "cases": cases,
    }
    _redigest(result)
    return result


def _redigest(manifest: dict[str, object]) -> None:
    manifest["manifest_digest"] = _sha(
        {key: value for key, value in manifest.items() if key != "manifest_digest"}
    )


def _policy(count: int = 30) -> dict[str, object]:
    return {
        "schema": "forecost.economic-outcome/1",
        "authority": "list_rate",
        "currency": "USD",
        "line_items": ["model_inference"],
        "expected_case_ids": [f"case-{index:04d}" for index in range(count)],
        "expected_source_ids": [_SOURCE_ID],
        "min_pairs": 30,
        "min_reduction_bps": 1_000,
        "max_outcome_regression_bps": 0,
        "confidence_bps": 9_500,
        "bootstrap_samples": 100,
        "baseline_configuration_digest": _BASE_CONFIG,
        "candidate_configuration_digest": _CANDIDATE_CONFIG,
        "dataset_digest": _DATASET_DIGEST,
        "task_set_digest": _TASK_SET_DIGEST,
        "freshness_contract": "frozen_receipt_snapshot",
        "claim_mode": "observational",
    }


def _cohort(
    *,
    count: int = 30,
    baseline_amount: int = 100_000,
    candidate_amount: int = 70_000,
    candidate_status: str = "good",
    candidate_tariff: str = "tariff-v1",
    candidate_amounts: tuple[int, ...] | None = None,
    baseline_tariff_payload: Mapping[str, object] | None = None,
    candidate_tariff_payload: Mapping[str, object] | None = None,
    candidate_outcome_type: str = "test_exit",
    candidate_outcome_confidence: str = "observed",
    candidate_bind_charge_to_meter: bool = True,
) -> tuple[sqlite3.Connection, dict[str, object], dict[str, object], dict[str, object]]:
    if candidate_amounts is not None and len(candidate_amounts) != count:
        raise ValueError("candidate_amounts must match count")
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    apply_schema(conn)
    baseline_cases: list[dict[str, object]] = []
    candidate_cases: list[dict[str, object]] = []
    for index in range(count):
        baseline_run = _append_run(
            conn,
            f"baseline-{index}",
            baseline_amount,
            "good",
            tariff_payload=baseline_tariff_payload,
        )
        candidate_run = _append_run(
            conn,
            f"candidate-{candidate_tariff}-{candidate_status}-{index}",
            candidate_amounts[index] if candidate_amounts is not None else candidate_amount,
            candidate_status,
            tariff_name=candidate_tariff,
            tariff_payload=candidate_tariff_payload,
            outcome_type=candidate_outcome_type,
            outcome_confidence=candidate_outcome_confidence,
            bind_charge_to_meter=candidate_bind_charge_to_meter,
        )
        baseline_cases.append(_case(index, "baseline", baseline_run, _BASE_CONFIG))
        candidate_cases.append(_case(index, "candidate", candidate_run, _CANDIDATE_CONFIG))
    return (
        conn,
        _manifest("baseline", baseline_cases),
        _manifest("candidate", candidate_cases),
        _policy(count),
    )


@pytest.fixture(scope="module")
def qualified_cohort() -> Iterator[
    tuple[sqlite3.Connection, dict[str, object], dict[str, object], dict[str, object]]
]:
    cohort = _cohort()
    yield cohort
    cohort[0].close()


def _decision(result: Mapping[str, object]) -> Mapping[str, object]:
    return cast(Mapping[str, object], result["decision"])


def _assert_no_floats(value: object) -> None:
    assert not isinstance(value, float)
    if isinstance(value, Mapping):
        for child in value.values():
            _assert_no_floats(child)
    elif isinstance(value, list):
        for child in value:
            _assert_no_floats(child)


def test_matched_cohort_pass_is_deterministic_and_integer_only(qualified_cohort):
    conn, baseline, candidate, policy = qualified_cohort

    first = compare_manifests(conn, baseline, candidate, policy)
    second = compare_manifests(conn, baseline, candidate, policy)

    assert first == second
    assert first["schema"] == "forecost.compare/1"
    assert _decision(first) == {"status": "pass", "reason_codes": []}
    assert comparison_exit_code(first) == 0
    scope = cast(Mapping[str, object], first["scope"])
    assert scope["claim_mode"] == "observational"
    economics = cast(Mapping[str, object], first["economics"])
    outcomes = cast(Mapping[str, object], first["outcomes"])
    basis = cast(Mapping[str, object], first["decision_basis"])
    assert basis["schema"] == "forecost.economic-outcome/1"
    assert basis["policy_digest"] == _sha(policy)
    assert basis["bootstrap_samples"] == 100
    assert basis["interval_method"] == "deterministic_sha256_counter_paired_bootstrap"
    bindings = cast(Mapping[str, object], first["input_bindings"])
    assert bindings["baseline_manifest_digest"] == baseline["manifest_digest"]
    assert bindings["candidate_configuration_digest"] == _CANDIDATE_CONFIG
    assert bindings["expected_source_ids"] == [_SOURCE_ID]
    assert bindings["baseline_privacy_profile"] == "metadata_minimized_v1"
    assert economics["observed_reduction_bps"] == 3_000
    assert economics["confidence_lower_bps"] == 3_000
    assert outcomes["observed_difference_bps"] == 0
    _assert_no_floats(first)


def test_threshold_failures_are_stable(qualified_cohort):
    conn, baseline, candidate, policy = qualified_cohort
    economic_policy = copy.deepcopy(policy)
    economic_policy["min_reduction_bps"] = 3_001
    economic = compare_manifests(conn, baseline, candidate, economic_policy)
    assert _decision(economic)["status"] == "fail"
    assert _decision(economic)["reason_codes"] == ["ECONOMIC_BOUND_NOT_MET"]
    assert comparison_exit_code(economic) == 2

    regression_conn, left, right, regression_policy = _cohort(candidate_status="bad")
    try:
        regression = compare_manifests(regression_conn, left, right, regression_policy)
    finally:
        regression_conn.close()
    assert _decision(regression)["status"] == "fail"
    assert _decision(regression)["reason_codes"] == ["OUTCOME_BOUND_NOT_MET"]


def test_bootstrap_decision_is_invariant_to_opaque_identifier_renames():
    candidate_amounts = (70_000,) * 20 + (130_000,) * 10
    conn, baseline, candidate, policy = _cohort(candidate_amounts=candidate_amounts)
    policy["min_reduction_bps"] = 100
    renamed = copy.deepcopy(candidate)
    for index, case in enumerate(cast(list[dict[str, object]], renamed["cases"])):
        case["attempt_id"] = f"renamed-attempt-{index:04d}"
    _redigest(renamed)
    try:
        original = compare_manifests(conn, baseline, candidate, policy)
        relabelled = compare_manifests(conn, baseline, renamed, policy)
    finally:
        conn.close()

    assert original["economics"] == relabelled["economics"]
    assert original["outcomes"] == relabelled["outcomes"]
    assert original["decision"] == relabelled["decision"]


def test_outcome_basis_and_confidence_must_qualify():
    basis_conn, basis_left, basis_right, basis_policy = _cohort(candidate_outcome_type="build_exit")
    try:
        basis_result = compare_manifests(basis_conn, basis_left, basis_right, basis_policy)
    finally:
        basis_conn.close()
    assert "OUTCOME_BASIS_MISMATCH" in cast(list[str], _decision(basis_result)["reason_codes"])

    confidence_conn, confidence_left, confidence_right, confidence_policy = _cohort(
        candidate_outcome_confidence="unknown"
    )
    try:
        confidence_result = compare_manifests(
            confidence_conn, confidence_left, confidence_right, confidence_policy
        )
    finally:
        confidence_conn.close()
    assert "OUTCOME_CONFIDENCE_UNQUALIFIED" in cast(
        list[str], _decision(confidence_result)["reason_codes"]
    )


@pytest.mark.parametrize(
    ("path", "value"),
    [
        (("schema",), "forecost.economic-outcome/2"),
        (("authority",), "billed"),
        (("currency",), "EUR"),
        (("freshness_contract",), "live"),
        (("claim_mode",), "experimental"),
        (("min_pairs",), 29),
        (("confidence_bps",), 10_000),
        (("bootstrap_samples",), 99),
        (("min_reduction_bps",), 1.5),
        (("min_pairs",), True),
    ],
)
def test_policy_configuration_matrix_rejected(qualified_cohort, path, value):
    conn, baseline, candidate, policy = qualified_cohort
    changed = copy.deepcopy(policy)
    changed[path[0]] = value
    with pytest.raises(ComparisonConfigurationError):
        compare_manifests(conn, baseline, candidate, changed)


def test_extra_fields_and_unbounded_identifiers_are_rejected(qualified_cohort):
    conn, baseline, candidate, policy = qualified_cohort
    extra = copy.deepcopy(baseline)
    extra["unexpected"] = "value"
    with pytest.raises(ComparisonConfigurationError):
        compare_manifests(conn, extra, candidate, policy)

    long_id = copy.deepcopy(baseline)
    cases = cast(list[dict[str, object]], long_id["cases"])
    cases[0]["case_id"] = "x" * 257
    _redigest(long_id)
    with pytest.raises(ComparisonConfigurationError):
        compare_manifests(conn, long_id, candidate, policy)


def test_bootstrap_work_is_bounded_before_evidence_reads(qualified_cohort):
    conn, baseline, candidate, policy = qualified_cohort
    hostile = copy.deepcopy(policy)
    hostile["expected_case_ids"] = [f"case-{index:04d}" for index in range(51)]
    hostile["bootstrap_samples"] = 100_000
    with pytest.raises(ComparisonConfigurationError, match="resource bound"):
        compare_manifests(conn, baseline, candidate, hostile)


@pytest.mark.parametrize(
    ("target", "field", "value", "reason"),
    [
        ("baseline", "dataset_digest", "1" * 64, "DATASET_BINDING_MISMATCH"),
        ("candidate", "task_set_digest", "2" * 64, "TASK_SET_BINDING_MISMATCH"),
        ("baseline", "configuration_digest", "3" * 64, "CONFIGURATION_BINDING_MISMATCH"),
        ("baseline", "privacy_profile", "metadata_minimized_v2", "PRIVACY_PROFILE_MISMATCH"),
        ("baseline", "source_ids", ["producer:" + "4" * 64], "SOURCE_DENOMINATOR_MISMATCH"),
    ],
)
def test_arm_binding_matrix_abstains_or_invalidates(qualified_cohort, target, field, value, reason):
    conn, baseline, candidate, policy = qualified_cohort
    left = copy.deepcopy(baseline)
    right = copy.deepcopy(candidate)
    changed = left if target == "baseline" else right
    changed[field] = value
    _redigest(changed)
    result = compare_manifests(conn, left, right, policy)
    assert reason in cast(list[str], _decision(result)["reason_codes"])
    if reason == "DATASET_BINDING_MISMATCH":
        bindings = cast(Mapping[str, object], result["input_bindings"])
        assert bindings["baseline_dataset_digest"] != bindings["policy_dataset_digest"]
    assert _decision(result)["status"] in {"abstain", "invalid"}


@pytest.mark.parametrize(
    ("field", "value", "reason"),
    [
        ("pair_id", "pair-changed", "PAIR_ROSTER_MISMATCH"),
        ("task_version", "task-v2", "TASK_VERSION_MISMATCH"),
        ("evaluator_id", "evaluator-v2", "EVALUATOR_ROSTER_MISMATCH"),
        ("verifier_version", "verifier-v2", "VERIFIER_ROSTER_MISMATCH"),
        ("outcome_source_id", "producer:" + "5" * 64, "OUTCOME_SOURCE_ROSTER_MISMATCH"),
    ],
)
def test_pair_roster_matrix_is_not_qualified(qualified_cohort, field, value, reason):
    conn, baseline, candidate, policy = qualified_cohort
    right = copy.deepcopy(candidate)
    cases = cast(list[dict[str, object]], right["cases"])
    cases[0][field] = value
    _redigest(right)
    result = compare_manifests(conn, baseline, right, policy)
    assert reason in cast(list[str], _decision(result)["reason_codes"])
    assert cast(Mapping[str, object], result["matching"])["qualified_pairs"] == 0


def test_manifest_and_receipt_digest_failures_are_invalid(qualified_cohort):
    conn, baseline, candidate, policy = qualified_cohort
    bad_manifest = copy.deepcopy(baseline)
    bad_manifest["manifest_digest"] = "f" * 64
    manifest_result = compare_manifests(conn, bad_manifest, candidate, policy)
    assert _decision(manifest_result)["status"] == "invalid"
    assert _decision(manifest_result)["reason_codes"] == ["MANIFEST_DIGEST_MISMATCH"]

    bad_receipt = copy.deepcopy(baseline)
    cases = cast(list[dict[str, object]], bad_receipt["cases"])
    cases[0]["receipt_digest"] = "e" * 64
    _redigest(bad_receipt)
    receipt_result = compare_manifests(conn, bad_receipt, candidate, policy)
    assert _decision(receipt_result)["status"] == "invalid"
    assert "RECEIPT_DIGEST_MISMATCH" in cast(list[str], _decision(receipt_result)["reason_codes"])


def test_outcome_evidence_and_source_bindings_are_verified(qualified_cohort):
    conn, baseline, candidate, policy = qualified_cohort
    wrong_evidence = copy.deepcopy(baseline)
    cases = cast(list[dict[str, object]], wrong_evidence["cases"])
    cases[0]["outcome_evidence_id"] = "outcome:" + "a" * 64
    _redigest(wrong_evidence)
    evidence_result = compare_manifests(conn, wrong_evidence, candidate, policy)
    assert "OUTCOME_EVIDENCE_BINDING_MISMATCH" in cast(
        list[str], _decision(evidence_result)["reason_codes"]
    )

    wrong_source_left = copy.deepcopy(baseline)
    wrong_source_right = copy.deepcopy(candidate)
    for manifest in (wrong_source_left, wrong_source_right):
        manifest_cases = cast(list[dict[str, object]], manifest["cases"])
        manifest_cases[0]["outcome_source_id"] = "producer:" + "b" * 64
        _redigest(manifest)
    source_result = compare_manifests(conn, wrong_source_left, wrong_source_right, policy)
    assert "OUTCOME_SOURCE_BINDING_MISMATCH" in cast(
        list[str], _decision(source_result)["reason_codes"]
    )


def test_extra_observed_source_breaks_the_predeclared_denominator():
    conn, baseline, candidate, policy = _cohort()
    changed = copy.deepcopy(candidate)
    cases = cast(list[dict[str, object]], changed["cases"])
    run_id = str(cases[0]["run_id"])
    append_observation(
        conn,
        observation(
            producer="unexpected_source",
            event_kind="span",
            causal=_identity("candidate-tariff-v1-good-0", 99, "unexpected-source-span"),
            payload={"operation_kind": "agent", "lifecycle": "completed"},
            occurred_at=_WHEN,
            observed_at=_WHEN,
        ),
    )
    try:
        receipt = build_receipt(conn, run_id)
        integrity = cast(Mapping[str, object], receipt["integrity"])
        cases[0]["receipt_digest"] = integrity["payload_digest"]
        _redigest(changed)
        result = compare_manifests(conn, baseline, changed, policy)
    finally:
        conn.close()
    assert _decision(result)["status"] == "abstain"
    assert "SOURCE_DENOMINATOR_MISMATCH" in cast(list[str], _decision(result)["reason_codes"])


def test_charge_without_its_meter_fact_cannot_qualify():
    conn, baseline, candidate, policy = _cohort(candidate_bind_charge_to_meter=False)
    try:
        result = compare_manifests(conn, baseline, candidate, policy)
    finally:
        conn.close()
    assert _decision(result)["status"] == "abstain"
    assert "VALUATION_NOT_FACT_BOUND" in cast(list[str], _decision(result)["reason_codes"])


def test_projection_only_charge_tampering_is_invalid_evidence():
    conn, baseline, candidate, policy = _cohort()
    conn.execute("UPDATE charges SET amount_micros = 1 WHERE amount_micros = 70000")
    conn.commit()
    try:
        result = compare_manifests(conn, baseline, candidate, policy)
    finally:
        conn.close()
    assert _decision(result)["status"] == "invalid"
    assert _decision(result)["reason_codes"] == ["PROJECTION_INTEGRITY_MISMATCH"]


@pytest.mark.parametrize("finality", ["final", "provisional"])
def test_unvalued_or_unsettled_meter_facts_block_qualification(finality):
    conn, baseline, candidate, policy = _cohort()
    changed = copy.deepcopy(candidate)
    _append_extra_meter(
        conn,
        "candidate-tariff-v1-good-0",
        finality=finality,
    )
    _refresh_manifest_receipts(conn, changed)
    try:
        result = compare_manifests(conn, baseline, changed, policy)
    finally:
        conn.close()
    assert _decision(result)["status"] == "abstain"
    assert "VALUATION_COVERAGE_INCOMPLETE" in cast(list[str], _decision(result)["reason_codes"])


def test_checkpoint_snapshots_cannot_create_a_false_reduction():
    conn, baseline, candidate, policy = _cohort()
    changed = copy.deepcopy(baseline)
    for index in range(30):
        _append_extra_meter(
            conn,
            f"baseline-{index}",
            aggregation="checkpoint",
            charge_amount_micros=100_000,
        )
    _refresh_manifest_receipts(conn, changed)
    try:
        result = compare_manifests(conn, changed, candidate, policy)
    finally:
        conn.close()
    assert _decision(result)["status"] == "abstain"
    assert "METER_AGGREGATION_UNSUPPORTED" in cast(list[str], _decision(result)["reason_codes"])


def test_attempt_and_run_reuse_are_rejected(qualified_cohort):
    conn, baseline, candidate, policy = qualified_cohort
    same_attempt = copy.deepcopy(candidate)
    left_cases = cast(list[dict[str, object]], baseline["cases"])
    right_cases = cast(list[dict[str, object]], same_attempt["cases"])
    right_cases[0]["attempt_id"] = left_cases[0]["attempt_id"]
    _redigest(same_attempt)
    attempt_result = compare_manifests(conn, baseline, same_attempt, policy)
    assert "ATTEMPT_ID_REUSED" in cast(list[str], _decision(attempt_result)["reason_codes"])

    same_run = copy.deepcopy(candidate)
    same_run_cases = cast(list[dict[str, object]], same_run["cases"])
    same_run_cases[0]["run_id"] = left_cases[0]["run_id"]
    _redigest(same_run)
    run_result = compare_manifests(conn, baseline, same_run, policy)
    assert _decision(run_result)["status"] == "invalid"
    assert "RUN_ID_REUSED" in cast(list[str], _decision(run_result)["reason_codes"])


def test_tariff_scope_mismatch_abstains():
    conn, baseline, candidate, policy = _cohort(candidate_tariff="tariff-v2")
    try:
        result = compare_manifests(conn, baseline, candidate, policy)
    finally:
        conn.close()
    assert _decision(result)["status"] == "abstain"
    assert "TARIFF_SCOPE_MISMATCH" in cast(list[str], _decision(result)["reason_codes"])


def test_empty_tariff_cannot_qualify():
    conn, baseline, candidate, policy = _cohort(
        baseline_tariff_payload={}, candidate_tariff_payload={}
    )
    try:
        result = compare_manifests(conn, baseline, candidate, policy)
    finally:
        conn.close()
    assert _decision(result)["status"] == "abstain"
    assert "VALUATION_GROUP_MALFORMED" in cast(list[str], _decision(result)["reason_codes"])


def test_tariff_without_rate_snapshot_cannot_qualify():
    weak_tariff = {"discount": False}
    conn, baseline, candidate, policy = _cohort(
        baseline_tariff_payload=weak_tariff,
        candidate_tariff_payload=weak_tariff,
    )
    try:
        result = compare_manifests(conn, baseline, candidate, policy)
    finally:
        conn.close()
    assert _decision(result)["status"] == "abstain"
    assert "VALUATION_GROUP_MALFORMED" in cast(list[str], _decision(result)["reason_codes"])


def test_non_journal_reconciliation_evidence_blocks_v1_decision(qualified_cohort):
    conn, baseline, candidate, policy = qualified_cohort
    candidate_copy = copy.deepcopy(candidate)
    cases = cast(list[dict[str, object]], candidate_copy["cases"])
    run_id = str(cases[0]["run_id"])
    conn.execute(
        "INSERT INTO reconciliation_batches VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (
            "batch-test-discrepant",
            1,
            run_id,
            "{}",
            None,
            "{}",
            _WHEN.isoformat(),
            _WHEN.isoformat(),
            "{}",
            1,
            1,
            0,
            0,
            100,
            90,
            10,
            0,
            "final",
            "discrepant",
            _WHEN.isoformat(),
            None,
        ),
    )
    conn.commit()
    try:
        receipt = build_receipt(conn, run_id)
        integrity = cast(Mapping[str, object], receipt["integrity"])
        cases[0]["receipt_digest"] = integrity["payload_digest"]
        _redigest(candidate_copy)
        result = compare_manifests(conn, baseline, candidate_copy, policy)
    finally:
        conn.execute(
            "DELETE FROM reconciliation_batches WHERE batch_id = ?", ("batch-test-discrepant",)
        )
        conn.commit()
    assert _decision(result)["status"] == "abstain"
    assert "RECONCILIATION_EVIDENCE_UNVERIFIED" in cast(
        list[str], _decision(result)["reason_codes"]
    )


def test_direct_run_mode_is_descriptive_and_always_abstains(qualified_cohort):
    conn, baseline, candidate, _ = qualified_cohort
    left = cast(list[dict[str, object]], baseline["cases"])[0]
    right = cast(list[dict[str, object]], candidate["cases"])[0]

    result = compare_runs_diagnostic(conn, str(left["run_id"]), str(right["run_id"]))

    assert _decision(result) == {
        "status": "abstain",
        "reason_codes": ["COMPARISON_MANIFEST_REQUIRED"],
    }
    assert comparison_exit_code(result) == 3
    economics = cast(Mapping[str, object], result["economics"])
    assert economics["observed_delta_micros"] == -30_000
    rendered = comparison_text(result)
    markdown = comparison_text(result, markdown=True)
    assert markdown.startswith("# Forecost comparison")
    assert all(term not in rendered.lower() for term in ("savings", "causal", "actual"))
    assert "unqualified diagnostic delta" in rendered
    assert "No cohort manifest" in rendered

    gateway = compare_runs_diagnostic(
        conn,
        str(left["run_id"]),
        str(right["run_id"]),
        authority="gateway_estimate",
    )
    gateway_text = comparison_text(gateway)
    assert "authority=gateway_estimate" in gateway_text
    assert "list-rate" not in gateway_text


def test_unknown_run_is_an_invalid_result_not_an_exception(qualified_cohort):
    conn, baseline, _, _ = qualified_cohort
    left = cast(list[dict[str, object]], baseline["cases"])[0]
    result = compare_runs_diagnostic(conn, str(left["run_id"]), "missing-run")
    assert _decision(result)["status"] == "invalid"
    assert _decision(result)["reason_codes"] == [
        "RUN_NOT_FOUND",
        "COMPARISON_MANIFEST_REQUIRED",
    ]
    assert comparison_exit_code(result) == 4
    assert comparison_exit_code({}) == 5


def test_projection_corruption_preempts_diagnostic_receipt_output(qualified_cohort):
    conn, baseline, _, _ = qualified_cohort
    left = cast(list[dict[str, object]], baseline["cases"])[0]
    run_id = str(left["run_id"])
    row = conn.execute(
        "SELECT c.charge_id, c.tariff_json FROM charges c JOIN causal_spans s "
        "ON s.span_key = c.span_key WHERE s.run_id = ?",
        (run_id,),
    ).fetchone()
    assert row is not None
    conn.execute(
        "UPDATE charges SET tariff_json = ? WHERE charge_id = ?",
        ("not-json", row[0]),
    )
    conn.commit()
    try:
        result = compare_runs_diagnostic(conn, run_id, "missing-run")
    finally:
        conn.execute(
            "UPDATE charges SET tariff_json = ? WHERE charge_id = ?",
            (row[1], row[0]),
        )
        conn.commit()
    assert _decision(result)["status"] == "invalid"
    assert _decision(result)["reason_codes"] == [
        "PROJECTION_INTEGRITY_MISMATCH",
        "COMPARISON_MANIFEST_REQUIRED",
    ]


def test_database_faults_propagate_for_boundary_exit_five():
    conn = sqlite3.connect(":memory:")
    try:
        with pytest.raises(sqlite3.OperationalError):
            compare_runs_diagnostic(conn, "baseline-run", "candidate-run")
    finally:
        conn.close()


def test_locally_detected_journal_rewrite_blocks_matched_decision():
    conn, baseline, candidate, policy = _cohort()
    row = conn.execute(
        "SELECT journal_sequence, payload_json FROM journal_observations "
        "ORDER BY journal_sequence LIMIT 1"
    ).fetchone()
    assert row is not None
    conn.execute(
        "UPDATE journal_observations SET payload_json = ? WHERE journal_sequence = ?",
        (str(row["payload_json"]) + " ", row["journal_sequence"]),
    )
    conn.commit()
    try:
        result = compare_manifests(conn, baseline, candidate, policy)
    finally:
        conn.close()
    assert _decision(result)["status"] == "invalid"
    assert "JOURNAL_INTEGRITY_NOT_INTACT" in cast(list[str], _decision(result)["reason_codes"])
    assert comparison_exit_code(result) == 4


def test_semantically_unrebuildable_anchored_journal_is_invalid():
    conn, baseline, candidate, policy = _cohort()
    row = conn.execute(
        "SELECT observation_id, payload_json FROM journal_observations "
        "WHERE event_kind = 'meter' ORDER BY journal_sequence LIMIT 1"
    ).fetchone()
    assert row is not None
    payload = json.loads(str(row["payload_json"]))
    del payload["meter_name"]
    conn.execute(
        "UPDATE journal_observations SET payload_json = ? WHERE observation_id = ?",
        (json.dumps(payload, sort_keys=True, separators=(",", ":")), row["observation_id"]),
    )
    conn.execute(
        "UPDATE journal_observations SET journal_sequence = NULL, "
        "previous_digest = NULL, entry_digest = NULL"
    )
    initialize_journal_chain(conn)
    conn.commit()
    try:
        result = compare_manifests(conn, baseline, candidate, policy)
    finally:
        conn.close()
    assert _decision(result)["status"] == "invalid"
    assert _decision(result)["reason_codes"] == ["PROJECTION_REBUILD_FAILED"]


def test_query_only_disk_connection_qualifies_without_source_mutation(tmp_path):
    source, baseline, candidate, policy = _cohort()
    path = tmp_path / "ledger.db"
    destination = sqlite3.connect(path)
    try:
        source.backup(destination)
    finally:
        destination.close()
        source.close()
    path.chmod(0o600)

    readonly = get_readonly_ledger_db(path)
    before_changes = readonly.total_changes
    before_version = readonly.execute("PRAGMA user_version").fetchone()[0]
    try:
        result = compare_manifests(readonly, baseline, candidate, policy)
        assert readonly.execute("PRAGMA query_only").fetchone()[0] == 1
        assert readonly.total_changes == before_changes
        assert readonly.execute("PRAGMA user_version").fetchone()[0] == before_version
    finally:
        readonly.close()
    assert _decision(result)["status"] == "pass"


def test_readonly_snapshot_includes_committed_wal_pages(tmp_path):
    path = tmp_path / "ledger.db"
    writer = get_ledger_db(path)
    writer.execute("PRAGMA wal_autocheckpoint=0")
    writer.execute("PRAGMA wal_checkpoint(TRUNCATE)")
    baseline = _append_run(writer, "wal-baseline", 100_000, "good")
    candidate = _append_run(writer, "wal-candidate", 70_000, "good")
    wal_path = path.with_name(path.name + "-wal")
    assert wal_path.exists()
    assert wal_path.stat().st_size > 0

    readonly = get_readonly_ledger_db(path)
    try:
        result = compare_runs_diagnostic(readonly, baseline["run_id"], candidate["run_id"])
    finally:
        readonly.close()
        writer.close()
    assert "RUN_NOT_FOUND" not in cast(list[str], _decision(result)["reason_codes"])
    assert result["economics"] is not None


def test_projection_validation_has_an_explicit_global_history_cap(monkeypatch):
    import forecost.comparison as comparison

    conn, baseline, candidate, policy = _cohort()
    monkeypatch.setattr(comparison, "_MAX_VALIDATION_JOURNAL_ROWS", 1)
    try:
        result = compare_manifests(conn, baseline, candidate, policy)
    finally:
        conn.close()
    assert _decision(result)["status"] == "abstain"
    assert _decision(result)["reason_codes"] == ["PROJECTION_VALIDATION_RESOURCE_LIMIT"]
