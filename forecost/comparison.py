"""Strict, read-only matched-cohort comparisons for receipt v2 evidence.

The v1 comparison profile is deliberately narrow.  It compares paired,
predeclared attempts using final USD list-rate valuations and predeclared
deterministic test/build outcomes.  The result describes an observed paired
difference; it does not widen the trust boundary of the underlying local receipts.
"""

from __future__ import annotations

import hashlib
import json
import re
import sqlite3
from collections.abc import Callable, Iterator, Mapping, Sequence
from contextlib import contextmanager
from dataclasses import dataclass
from typing import cast

from forecost.ledger.contracts import Authority
from forecost.ledger.integrity import verify_journal_chain
from forecost.ledger.receipts import build_receipt

_ARM_SCHEMA = "forecost.compare-arm/1"
_PROFILE_SCHEMA = "forecost.economic-outcome/1"
_OUTPUT_SCHEMA = "forecost.compare/1"
_SAFE_ATOM = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/@+\-]*$")
_HEX_DIGEST = re.compile(r"^[0-9a-f]{64}$")
_MAX_CASES = 10_000
_MAX_SOURCES = 64
_MAX_LINE_ITEMS = 16
_MAX_BOOTSTRAP_DRAWS = 5_000_000
_MAX_VALIDATION_JOURNAL_ROWS = 1_000_000
_DETERMINISTIC_OUTCOMES = frozenset({"test_exit", "build_exit"})
_TERMINAL_LIFECYCLES = frozenset({"completed", "failed", "cancelled"})

_ARM_KEYS = frozenset(
    {
        "schema",
        "arm",
        "manifest_digest",
        "dataset_digest",
        "task_set_digest",
        "configuration_digest",
        "privacy_profile",
        "source_ids",
        "cases",
    }
)
_CASE_KEYS = frozenset(
    {
        "case_id",
        "task_version",
        "attempt_id",
        "pair_id",
        "evaluator_id",
        "verifier_id",
        "verifier_version",
        "outcome_source_id",
        "outcome_evidence_id",
        "run_id",
        "receipt_digest",
        "tariff_digest",
        "configuration_digest",
    }
)
_POLICY_KEYS = frozenset(
    {
        "schema",
        "authority",
        "currency",
        "line_items",
        "expected_case_ids",
        "expected_source_ids",
        "min_pairs",
        "min_reduction_bps",
        "max_outcome_regression_bps",
        "confidence_bps",
        "bootstrap_samples",
        "baseline_configuration_digest",
        "candidate_configuration_digest",
        "dataset_digest",
        "task_set_digest",
        "freshness_contract",
        "claim_mode",
    }
)

_REASON_ORDER = (
    "MANIFEST_DIGEST_MISMATCH",
    "DATASET_BINDING_MISMATCH",
    "TASK_SET_BINDING_MISMATCH",
    "CONFIGURATION_BINDING_MISMATCH",
    "PRIVACY_PROFILE_MISMATCH",
    "CASE_ROSTER_MISMATCH",
    "PAIR_ROSTER_MISMATCH",
    "TASK_VERSION_MISMATCH",
    "EVALUATOR_ROSTER_MISMATCH",
    "VERIFIER_ROSTER_MISMATCH",
    "OUTCOME_SOURCE_ROSTER_MISMATCH",
    "ATTEMPT_ID_REUSED",
    "RUN_ID_REUSED",
    "SOURCE_DENOMINATOR_MISMATCH",
    "RUN_NOT_FOUND",
    "RECEIPT_MALFORMED",
    "RECEIPT_INTEGRITY_MISMATCH",
    "RECEIPT_DIGEST_MISMATCH",
    "RUN_ID_BINDING_MISMATCH",
    "ATTEMPT_NOT_SETTLED",
    "STRUCTURAL_EVIDENCE_UNQUALIFIED",
    "OUTCOME_EVIDENCE_UNQUALIFIED",
    "SOURCE_EVIDENCE_INCOMPLETE",
    "OUTCOME_EVIDENCE_BINDING_MISMATCH",
    "OUTCOME_SOURCE_BINDING_MISMATCH",
    "OUTCOME_NOT_DECISIVE",
    "OUTCOME_NOT_DETERMINISTIC",
    "OUTCOME_CONFIDENCE_UNQUALIFIED",
    "OUTCOME_BASIS_MISMATCH",
    "VALUATION_GROUP_MALFORMED",
    "DECLARED_AUTHORITY_MISSING",
    "DECLARED_AUTHORITY_AMBIGUOUS",
    "VALUATION_COVERAGE_INCOMPLETE",
    "METER_AGGREGATION_UNSUPPORTED",
    "METER_SCOPE_UNSUPPORTED",
    "VALUATION_NOT_FACT_BOUND",
    "VALUATION_NOT_FINAL",
    "LIST_RATE_RECOMPUTATION_MISMATCH",
    "TARIFF_BINDING_MISMATCH",
    "TARIFF_SCOPE_MISMATCH",
    "RECONCILIATION_EVIDENCE_UNVERIFIED",
    "RECONCILIATION_DISCREPANCY",
    "JOURNAL_INTEGRITY_NOT_INTACT",
    "PROJECTION_INTEGRITY_MISMATCH",
    "PROJECTION_REBUILD_FAILED",
    "PROJECTION_VALIDATION_RESOURCE_LIMIT",
    "ZERO_BASELINE_DENOMINATOR",
    "MINIMUM_PAIRS_NOT_MET",
    "ECONOMIC_BOUND_NOT_MET",
    "OUTCOME_BOUND_NOT_MET",
    "COMPARISON_MANIFEST_REQUIRED",
)
_INVALID_REASONS = frozenset(
    {
        "MANIFEST_DIGEST_MISMATCH",
        "DATASET_BINDING_MISMATCH",
        "TASK_SET_BINDING_MISMATCH",
        "CONFIGURATION_BINDING_MISMATCH",
        "RUN_ID_REUSED",
        "RUN_NOT_FOUND",
        "RECEIPT_MALFORMED",
        "RECEIPT_INTEGRITY_MISMATCH",
        "RECEIPT_DIGEST_MISMATCH",
        "RUN_ID_BINDING_MISMATCH",
        "OUTCOME_EVIDENCE_BINDING_MISMATCH",
        "OUTCOME_SOURCE_BINDING_MISMATCH",
        "JOURNAL_INTEGRITY_NOT_INTACT",
        "PROJECTION_INTEGRITY_MISMATCH",
        "PROJECTION_REBUILD_FAILED",
    }
)
_FAIL_REASONS = frozenset({"ECONOMIC_BOUND_NOT_MET", "OUTCOME_BOUND_NOT_MET"})
_LIMITATIONS = [
    "observed_paired_difference_only",
    "list_rate_equivalent_only",
    "external_evaluator_and_source_declarations_are_manifest_attested",
    "metadata_minimization_profile_is_declared_not_independently_verified",
    "minimum_pair_floor_is_not_power_analysis",
    "local_receipt_integrity_boundary",
    "reconciliation_evidence_is_outside_the_v1_qualified_boundary",
]


class ComparisonConfigurationError(ValueError):
    """The caller supplied a malformed or unsupported comparison contract."""


@dataclass(frozen=True)
class _Case:
    case_id: str
    task_version: str
    attempt_id: str
    pair_id: str
    evaluator_id: str
    verifier_id: str
    verifier_version: str
    outcome_source_id: str
    outcome_evidence_id: str
    run_id: str
    receipt_digest: str
    tariff_digest: str
    configuration_digest: str


@dataclass(frozen=True)
class _Arm:
    name: str
    manifest_digest: str
    dataset_digest: str
    task_set_digest: str
    configuration_digest: str
    privacy_profile: str
    source_ids: tuple[str, ...]
    cases: tuple[_Case, ...]


@dataclass(frozen=True)
class _Policy:
    authority: str
    currency: str
    line_items: tuple[str, ...]
    expected_case_ids: tuple[str, ...]
    expected_source_ids: tuple[str, ...]
    min_pairs: int
    min_reduction_bps: int
    max_outcome_regression_bps: int
    confidence_bps: int
    bootstrap_samples: int
    baseline_configuration_digest: str
    candidate_configuration_digest: str
    dataset_digest: str
    task_set_digest: str


@dataclass(frozen=True)
class _Measure:
    amount_micros: int
    outcome_score: int
    outcome_evidence_type: str
    receipt_digest: str
    tariff_digest: str


def _canonical_json(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def _sha256(value: object) -> str:
    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


def _reject_unbounded_json(value: object, *, depth: int = 0) -> None:
    if depth > 8:
        raise ComparisonConfigurationError("comparison input nesting is too deep")
    if isinstance(value, float):
        raise ComparisonConfigurationError("comparison inputs must not contain floats")
    if isinstance(value, Mapping):
        _reject_mapping(value, depth)
        return
    if isinstance(value, Sequence) and not isinstance(value, str | bytes | bytearray):
        _reject_sequence(value, depth)
        return
    _reject_scalar(value)


def _reject_mapping(value: Mapping[object, object], depth: int) -> None:
    if len(value) > 32:
        raise ComparisonConfigurationError("comparison object has too many fields")
    for key, item in value.items():
        if not isinstance(key, str) or len(key) > 64:
            raise ComparisonConfigurationError("comparison keys must be bounded strings")
        _reject_unbounded_json(item, depth=depth + 1)


def _reject_sequence(value: Sequence[object], depth: int) -> None:
    if len(value) > _MAX_CASES:
        raise ComparisonConfigurationError("comparison array is too large")
    for item in value:
        _reject_unbounded_json(item, depth=depth + 1)


def _reject_scalar(value: object) -> None:
    if value is None or isinstance(value, bool | int):
        return
    if isinstance(value, str) and len(value) <= 256:
        return
    raise ComparisonConfigurationError("comparison inputs must use JSON-compatible values")


def _mapping(value: object, name: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        raise ComparisonConfigurationError(f"{name} must be an object")
    return cast(Mapping[str, object], value)


def _exact_keys(value: Mapping[str, object], expected: frozenset[str], name: str) -> None:
    if set(value) != expected:
        raise ComparisonConfigurationError(f"{name} fields do not match its v1 schema")


def _atom(value: object, name: str) -> str:
    if not isinstance(value, str) or len(value) > 256 or _SAFE_ATOM.fullmatch(value) is None:
        raise ComparisonConfigurationError(f"{name} must be a bounded opaque identifier")
    return value


def _digest(value: object, name: str) -> str:
    if not isinstance(value, str) or _HEX_DIGEST.fullmatch(value) is None:
        raise ComparisonConfigurationError(f"{name} must be a lowercase SHA-256 digest")
    return value


def _integer(value: object, name: str, minimum: int, maximum: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or not minimum <= value <= maximum:
        raise ComparisonConfigurationError(f"{name} is outside the supported integer range")
    return value


def _atom_list(value: object, name: str, maximum: int) -> tuple[str, ...]:
    if not isinstance(value, list) or not 1 <= len(value) <= maximum:
        raise ComparisonConfigurationError(f"{name} must be a non-empty bounded array")
    result = tuple(_atom(item, name) for item in value)
    if tuple(sorted(set(result))) != result:
        raise ComparisonConfigurationError(f"{name} must be sorted and unique")
    return result


def _case(value: object, arm_name: str) -> _Case:
    raw = _mapping(value, f"{arm_name} case")
    _exact_keys(raw, _CASE_KEYS, f"{arm_name} case")
    return _Case(
        case_id=_atom(raw["case_id"], "case_id"),
        task_version=_atom(raw["task_version"], "task_version"),
        attempt_id=_atom(raw["attempt_id"], "attempt_id"),
        pair_id=_atom(raw["pair_id"], "pair_id"),
        evaluator_id=_atom(raw["evaluator_id"], "evaluator_id"),
        verifier_id=_atom(raw["verifier_id"], "verifier_id"),
        verifier_version=_atom(raw["verifier_version"], "verifier_version"),
        outcome_source_id=_atom(raw["outcome_source_id"], "outcome_source_id"),
        outcome_evidence_id=_atom(raw["outcome_evidence_id"], "outcome_evidence_id"),
        run_id=_atom(raw["run_id"], "run_id"),
        receipt_digest=_digest(raw["receipt_digest"], "receipt_digest"),
        tariff_digest=_digest(raw["tariff_digest"], "tariff_digest"),
        configuration_digest=_digest(raw["configuration_digest"], "configuration_digest"),
    )


def _cases(value: object, arm_name: str) -> tuple[_Case, ...]:
    if not isinstance(value, list) or not 1 <= len(value) <= _MAX_CASES:
        raise ComparisonConfigurationError(f"{arm_name} cases must be a bounded array")
    cases = tuple(_case(item, arm_name) for item in value)
    case_ids = tuple(item.case_id for item in cases)
    if case_ids != tuple(sorted(set(case_ids))):
        raise ComparisonConfigurationError(f"{arm_name} cases must have sorted unique case_id")
    if len({item.pair_id for item in cases}) != len(cases):
        raise ComparisonConfigurationError(f"{arm_name} pair_id values must be unique")
    if len({item.run_id for item in cases}) != len(cases):
        raise ComparisonConfigurationError(f"{arm_name} run_id values must be unique")
    return cases


def _manifest_payload(raw: Mapping[str, object]) -> dict[str, object]:
    return {key: value for key, value in raw.items() if key != "manifest_digest"}


def _arm(value: Mapping[str, object], expected_name: str) -> tuple[_Arm, bool]:
    _reject_unbounded_json(value)
    raw = _mapping(value, f"{expected_name} manifest")
    _exact_keys(raw, _ARM_KEYS, f"{expected_name} manifest")
    if raw["schema"] != _ARM_SCHEMA or raw["arm"] != expected_name:
        raise ComparisonConfigurationError(f"{expected_name} manifest schema or arm is unsupported")
    manifest_digest = _digest(raw["manifest_digest"], "manifest_digest")
    arm = _Arm(
        name=expected_name,
        manifest_digest=manifest_digest,
        dataset_digest=_digest(raw["dataset_digest"], "dataset_digest"),
        task_set_digest=_digest(raw["task_set_digest"], "task_set_digest"),
        configuration_digest=_digest(raw["configuration_digest"], "configuration_digest"),
        privacy_profile=_atom(raw["privacy_profile"], "privacy_profile"),
        source_ids=_atom_list(raw["source_ids"], "source_ids", _MAX_SOURCES),
        cases=_cases(raw["cases"], expected_name),
    )
    return arm, manifest_digest == _sha256(_manifest_payload(raw))


def _policy(value: Mapping[str, object]) -> _Policy:
    _reject_unbounded_json(value)
    raw = _mapping(value, "policy")
    _exact_keys(raw, _POLICY_KEYS, "policy")
    _validate_policy_literals(raw)
    expected_cases = _atom_list(raw["expected_case_ids"], "expected_case_ids", _MAX_CASES)
    minimum = _integer(raw["min_pairs"], "min_pairs", 30, _MAX_CASES)
    bootstrap_samples = _integer(raw["bootstrap_samples"], "bootstrap_samples", 100, 100_000)
    if minimum > len(expected_cases):
        raise ComparisonConfigurationError("min_pairs exceeds the predeclared case roster")
    if bootstrap_samples * len(expected_cases) > _MAX_BOOTSTRAP_DRAWS:
        raise ComparisonConfigurationError("bootstrap draw count exceeds the v1 resource bound")
    line_items = _atom_list(raw["line_items"], "line_items", _MAX_LINE_ITEMS)
    if line_items != ("model_inference",):
        raise ComparisonConfigurationError(
            "comparison v1 supports exactly the model_inference line item"
        )
    return _Policy(
        authority="list_rate",
        currency="USD",
        line_items=line_items,
        expected_case_ids=expected_cases,
        expected_source_ids=_atom_list(
            raw["expected_source_ids"], "expected_source_ids", _MAX_SOURCES
        ),
        min_pairs=minimum,
        min_reduction_bps=_integer(raw["min_reduction_bps"], "min_reduction_bps", 0, 10_000),
        max_outcome_regression_bps=_integer(
            raw["max_outcome_regression_bps"], "max_outcome_regression_bps", 0, 10_000
        ),
        confidence_bps=_integer(raw["confidence_bps"], "confidence_bps", 5_000, 9_999),
        bootstrap_samples=bootstrap_samples,
        baseline_configuration_digest=_digest(
            raw["baseline_configuration_digest"], "baseline_configuration_digest"
        ),
        candidate_configuration_digest=_digest(
            raw["candidate_configuration_digest"], "candidate_configuration_digest"
        ),
        dataset_digest=_digest(raw["dataset_digest"], "dataset_digest"),
        task_set_digest=_digest(raw["task_set_digest"], "task_set_digest"),
    )


def _validate_policy_literals(raw: Mapping[str, object]) -> None:
    expected = {
        "schema": _PROFILE_SCHEMA,
        "authority": "list_rate",
        "currency": "USD",
        "freshness_contract": "frozen_receipt_snapshot",
        "claim_mode": "observational",
    }
    for key, value in expected.items():
        if raw[key] != value:
            raise ComparisonConfigurationError(f"policy {key} is unsupported in v1")


def _ordered_reasons(reasons: Sequence[str]) -> list[str]:
    present = set(reasons)
    return [reason for reason in _REASON_ORDER if reason in present]


def _binding_reasons(baseline: _Arm, candidate: _Arm, policy: _Policy) -> list[str]:
    reasons: list[str] = []
    if (
        baseline.dataset_digest != policy.dataset_digest
        or candidate.dataset_digest != policy.dataset_digest
    ):
        reasons.append("DATASET_BINDING_MISMATCH")
    if (
        baseline.task_set_digest != policy.task_set_digest
        or candidate.task_set_digest != policy.task_set_digest
    ):
        reasons.append("TASK_SET_BINDING_MISMATCH")
    if not _configurations_match(baseline, candidate, policy):
        reasons.append("CONFIGURATION_BINDING_MISMATCH")
    if (
        baseline.privacy_profile != candidate.privacy_profile
        or baseline.privacy_profile != "metadata_minimized_v1"
    ):
        reasons.append("PRIVACY_PROFILE_MISMATCH")
    reasons.extend(_roster_reasons(baseline, candidate, policy))
    if (
        baseline.source_ids != policy.expected_source_ids
        or candidate.source_ids != policy.expected_source_ids
    ):
        reasons.append("SOURCE_DENOMINATOR_MISMATCH")
    return reasons


def _configurations_match(baseline: _Arm, candidate: _Arm, policy: _Policy) -> bool:
    return (
        baseline.configuration_digest == policy.baseline_configuration_digest
        and candidate.configuration_digest == policy.candidate_configuration_digest
        and all(
            item.configuration_digest == baseline.configuration_digest for item in baseline.cases
        )
        and all(
            item.configuration_digest == candidate.configuration_digest for item in candidate.cases
        )
    )


def _case_signature(item: _Case) -> tuple[str, str, str, str, str, str, str]:
    return (
        item.case_id,
        item.pair_id,
        item.task_version,
        item.evaluator_id,
        item.verifier_id,
        item.verifier_version,
        item.outcome_source_id,
    )


def _roster_reasons(baseline: _Arm, candidate: _Arm, policy: _Policy) -> list[str]:
    reasons: list[str] = []
    base_ids = tuple(item.case_id for item in baseline.cases)
    candidate_ids = tuple(item.case_id for item in candidate.cases)
    if base_ids != policy.expected_case_ids or candidate_ids != policy.expected_case_ids:
        reasons.append("CASE_ROSTER_MISMATCH")
    if base_ids == candidate_ids:
        reasons.extend(_pairwise_roster_reasons(baseline.cases, candidate.cases))
    attempts = [item.attempt_id for item in (*baseline.cases, *candidate.cases)]
    if len(set(attempts)) != len(attempts):
        reasons.append("ATTEMPT_ID_REUSED")
    run_ids = [item.run_id for item in (*baseline.cases, *candidate.cases)]
    if len(set(run_ids)) != len(run_ids):
        reasons.append("RUN_ID_REUSED")
    return reasons


def _pairwise_roster_reasons(baseline: Sequence[_Case], candidate: Sequence[_Case]) -> list[str]:
    reasons: list[str] = []
    signatures = tuple(zip(baseline, candidate, strict=True))
    fields = (
        ("PAIR_ROSTER_MISMATCH", lambda item: item.pair_id),
        ("TASK_VERSION_MISMATCH", lambda item: item.task_version),
        ("EVALUATOR_ROSTER_MISMATCH", lambda item: item.evaluator_id),
        ("VERIFIER_ROSTER_MISMATCH", lambda item: (item.verifier_id, item.verifier_version)),
        ("OUTCOME_SOURCE_ROSTER_MISMATCH", lambda item: item.outcome_source_id),
    )
    for reason, selector in fields:
        if any(selector(left) != selector(right) for left, right in signatures):
            reasons.append(reason)
    return reasons


def _receipt_digest(receipt: Mapping[str, object]) -> str | None:
    integrity = receipt.get("integrity")
    if not isinstance(integrity, Mapping) or integrity.get("algorithm") != "sha256":
        return None
    digest = integrity.get("payload_digest")
    return str(digest) if isinstance(digest, str) and _HEX_DIGEST.fullmatch(digest) else None


def _receipt_integrity_valid(receipt: Mapping[str, object]) -> bool:
    expected = _receipt_digest(receipt)
    payload = {key: value for key, value in receipt.items() if key != "integrity"}
    return expected is not None and expected == _sha256(payload)


def _safe_receipt(
    conn: sqlite3.Connection, run_id: str
) -> tuple[dict[str, object] | None, str | None]:
    if conn.execute("SELECT 1 FROM causal_runs WHERE run_id = ?", (run_id,)).fetchone() is None:
        return None, "RUN_NOT_FOUND"
    try:
        receipt = build_receipt(conn, run_id)
    except ValueError:
        return None, "RECEIPT_MALFORMED"
    except (TypeError, KeyError):
        return None, "RECEIPT_MALFORMED"
    if not isinstance(receipt, dict):
        return None, "RECEIPT_MALFORMED"
    return cast(dict[str, object], receipt), None


def _profile_qualified(receipt: Mapping[str, object], profile_id: str) -> bool:
    evidence = receipt.get("evidence")
    if not isinstance(evidence, Mapping):
        return False
    profiles = evidence.get("claim_profiles")
    profile = profiles.get(profile_id) if isinstance(profiles, Mapping) else None
    return bool(
        isinstance(profile, Mapping)
        and profile.get("completeness") == "complete"
        and profile.get("contradiction") == "clear"
    )


def _receipt_binding_reasons(receipt: Mapping[str, object], item: _Case) -> list[str]:
    reasons: list[str] = []
    if receipt.get("run_id") != item.run_id:
        reasons.append("RUN_ID_BINDING_MISMATCH")
    if not _receipt_integrity_valid(receipt):
        reasons.append("RECEIPT_INTEGRITY_MISMATCH")
    elif _receipt_digest(receipt) != item.receipt_digest:
        reasons.append("RECEIPT_DIGEST_MISMATCH")
    if receipt.get("lifecycle") not in _TERMINAL_LIFECYCLES:
        reasons.append("ATTEMPT_NOT_SETTLED")
    if not _profile_qualified(receipt, "structural"):
        reasons.append("STRUCTURAL_EVIDENCE_UNQUALIFIED")
    if not _profile_qualified(receipt, "outcome"):
        reasons.append("OUTCOME_EVIDENCE_UNQUALIFIED")
    return reasons


def _source_reasons(receipt: Mapping[str, object], expected: Sequence[str]) -> list[str]:
    evidence = receipt.get("evidence")
    present = evidence.get("sources_present") if isinstance(evidence, Mapping) else None
    if not isinstance(present, list) or not all(isinstance(item, str) for item in present):
        return ["SOURCE_EVIDENCE_INCOMPLETE"]
    present_sources = set(cast(list[str], present))
    expected_sources = set(expected)
    reasons: list[str] = []
    if not expected_sources.issubset(present_sources):
        reasons.append("SOURCE_EVIDENCE_INCOMPLETE")
    if not present_sources.issubset(expected_sources):
        reasons.append("SOURCE_DENOMINATOR_MISMATCH")
    return reasons


def _outcome_measure(
    conn: sqlite3.Connection, receipt: Mapping[str, object], item: _Case
) -> tuple[int | None, str | None, list[str]]:
    outcome = receipt.get("outcome")
    evidence = receipt.get("outcome_evidence")
    if not isinstance(outcome, Mapping) or not isinstance(evidence, list):
        return None, None, ["RECEIPT_MALFORMED"]
    selected = [row for row in evidence if _evidence_matches(row, item.outcome_evidence_id)]
    if len(selected) != 1:
        return None, None, ["OUTCOME_EVIDENCE_BINDING_MISMATCH"]
    row = cast(Mapping[str, object], selected[0])
    reasons = _outcome_row_reasons(outcome, row)
    reasons.extend(_outcome_db_binding_reasons(conn, item))
    status = outcome.get("status")
    evidence_type = row.get("evidence_type")
    return (
        1 if status == "good" else 0 if status == "bad" else None,
        str(evidence_type) if isinstance(evidence_type, str) else None,
        reasons,
    )


def _evidence_matches(value: object, evidence_id: str) -> bool:
    return isinstance(value, Mapping) and value.get("evidence_id") == evidence_id


def _outcome_row_reasons(outcome: Mapping[str, object], row: Mapping[str, object]) -> list[str]:
    reasons: list[str] = []
    status = outcome.get("status")
    if (
        status not in {"good", "bad"}
        or row.get("status") != status
        or row.get("active") is not True
    ):
        reasons.append("OUTCOME_NOT_DECISIVE")
    if row.get("evidence_type") not in _DETERMINISTIC_OUTCOMES:
        reasons.append("OUTCOME_NOT_DETERMINISTIC")
    if row.get("confidence") not in {"observed", "explicit"}:
        reasons.append("OUTCOME_CONFIDENCE_UNQUALIFIED")
    return reasons


def _outcome_db_binding_reasons(conn: sqlite3.Connection, item: _Case) -> list[str]:
    row = conn.execute(
        "SELECT run_id, source FROM outcome_evidence WHERE evidence_id = ?",
        (item.outcome_evidence_id,),
    ).fetchone()
    if row is None or str(row[0]) != item.run_id:
        return ["OUTCOME_EVIDENCE_BINDING_MISMATCH"]
    if str(row[1]) != item.outcome_source_id:
        return ["OUTCOME_SOURCE_BINDING_MISMATCH"]
    return []


def _has_reconciliation_evidence(conn: sqlite3.Connection, run_id: str) -> bool:
    """Return whether non-journal reconciliation state affects this receipt.

    Reconciliation batches are useful local evidence, but v1 cannot rebuild
    them from the append-only journal.  A qualified comparison therefore
    abstains whenever they are present instead of treating their mutable state
    as verified by the journal/projection check.
    """
    return (
        conn.execute(
            "SELECT 1 FROM reconciliation_batches WHERE run_id = ? LIMIT 1",
            (run_id,),
        ).fetchone()
        is not None
    )


def _economic_measure(
    conn: sqlite3.Connection,
    receipt: Mapping[str, object],
    item: _Case,
    policy: _Policy,
) -> tuple[int | None, list[str]]:
    groups = receipt.get("valuation_groups")
    if not isinstance(groups, list):
        return None, ["VALUATION_GROUP_MALFORMED"]
    selected_groups = [group for group in groups if _group_in_scope(group, policy)]
    if not selected_groups:
        return None, ["DECLARED_AUTHORITY_MISSING"]
    meters, reasons = _qualified_meter_index(receipt, selected_groups)
    amounts, tariff_digests, group_reasons = _measure_groups(
        conn, item, policy, selected_groups, meters
    )
    reasons.extend(group_reasons)
    reasons.extend(_tariff_binding_reasons(item, tariff_digests))
    if _has_reconciliation_evidence(conn, item.run_id):
        reasons.append("RECONCILIATION_EVIDENCE_UNVERIFIED")
    return (sum(amounts) if not reasons else None), reasons


def _qualified_meter_index(
    receipt: Mapping[str, object], groups: Sequence[object]
) -> tuple[dict[str, Mapping[str, object]], list[str]]:
    meters = receipt.get("meter_facts")
    if not isinstance(meters, list):
        return {}, ["RECEIPT_MALFORMED"]
    meter_reason = _meter_list_reason(meters)
    if meter_reason is not None:
        return {}, [meter_reason]
    meter_index = {
        str(item["fact_id"]): cast(Mapping[str, object], item)
        for item in meters
        if isinstance(item, Mapping) and isinstance(item.get("fact_id"), str)
    }
    if not meter_index or len(meter_index) != len(meters):
        return {}, ["RECEIPT_MALFORMED"]
    if not _groups_cover_meters(groups, meter_index):
        return {}, ["VALUATION_COVERAGE_INCOMPLETE"]
    return meter_index, []


def _meter_list_reason(meters: Sequence[object]) -> str | None:
    if any(not isinstance(item, Mapping) or item.get("aggregation") != "delta" for item in meters):
        return "METER_AGGREGATION_UNSUPPORTED"
    if any(cast(Mapping[str, object], item).get("finality") != "final" for item in meters):
        return "VALUATION_COVERAGE_INCOMPLETE"
    if any(not _meter_scope_supported(item) for item in meters):
        return "METER_SCOPE_UNSUPPORTED"
    return None


def _groups_cover_meters(groups: Sequence[object], meter_index: Mapping[str, object]) -> bool:
    group_fact_ids = [
        str(item.get("economic_fact_key"))
        for item in groups
        if isinstance(item, Mapping) and isinstance(item.get("economic_fact_key"), str)
    ]
    return (
        len(group_fact_ids) == len(groups)
        and len(set(group_fact_ids)) == len(group_fact_ids)
        and len(group_fact_ids) == len(meter_index)
        and set(group_fact_ids) == set(meter_index)
    )


def _meter_scope_supported(value: object) -> bool:
    return bool(
        isinstance(value, Mapping)
        and value.get("meter_name") in {"tokens.input", "tokens.output"}
        and value.get("unit") == "token"
        and isinstance(value.get("quantity_micros"), int)
        and not isinstance(value.get("quantity_micros"), bool)
        and cast(int, value["quantity_micros"]) >= 0
    )


def _measure_groups(
    conn: sqlite3.Connection,
    item: _Case,
    policy: _Policy,
    groups: Sequence[object],
    meters: Mapping[str, Mapping[str, object]],
) -> tuple[list[int], list[str], list[str]]:
    amounts: list[int] = []
    tariffs: list[str] = []
    reasons: list[str] = []
    for group in groups:
        amount, tariff, group_reasons = _group_measure(conn, item, policy, group, meters)
        reasons.extend(group_reasons)
        if amount is not None:
            amounts.append(amount)
        if tariff is not None:
            tariffs.append(tariff)
    return amounts, tariffs, reasons


def _tariff_binding_reasons(item: _Case, tariffs: Sequence[str]) -> list[str]:
    if tariffs and any(value != item.tariff_digest for value in tariffs):
        return ["TARIFF_BINDING_MISMATCH"]
    return []


def _group_in_scope(value: object, policy: _Policy) -> bool:
    return bool(
        isinstance(value, Mapping)
        and value.get("currency") == policy.currency
        and value.get("line_item") in policy.line_items
    )


def _group_measure(
    conn: sqlite3.Connection,
    item: _Case,
    policy: _Policy,
    value: object,
    meters: Mapping[str, Mapping[str, object]],
) -> tuple[int | None, str | None, list[str]]:
    if (
        not isinstance(value, Mapping)
        or value.get("aggregation_rule") != "alternatives_not_additive"
    ):
        return None, None, ["VALUATION_GROUP_MALFORMED"]
    valuations = value.get("valuations")
    if not isinstance(valuations, list):
        return None, None, ["VALUATION_GROUP_MALFORMED"]
    matches = [row for row in valuations if _authority_matches(row, policy.authority)]
    if len(matches) != 1:
        reason = "DECLARED_AUTHORITY_MISSING" if not matches else "DECLARED_AUTHORITY_AMBIGUOUS"
        return None, None, [reason]
    return _valuation_measure(conn, item, value, cast(Mapping[str, object], matches[0]), meters)


def _authority_matches(value: object, authority: str) -> bool:
    return isinstance(value, Mapping) and value.get("authority") == authority


def _valuation_measure(
    conn: sqlite3.Connection,
    item: _Case,
    group: Mapping[str, object],
    valuation: Mapping[str, object],
    meters: Mapping[str, Mapping[str, object]],
) -> tuple[int | None, str | None, list[str]]:
    parsed = _valuation_fields(valuation)
    if parsed is None:
        return None, None, ["VALUATION_GROUP_MALFORMED"]
    fact_id, amount, charge_id = parsed
    if group.get("economic_fact_key") != fact_id:
        return None, None, ["VALUATION_NOT_FACT_BOUND"]
    if not _meter_fact_is_bound(conn, item.run_id, fact_id):
        return None, None, ["VALUATION_NOT_FACT_BOUND"]
    meter = meters.get(fact_id)
    if meter is None:
        return None, None, ["VALUATION_NOT_FACT_BOUND"]
    row = _charge_row(conn, charge_id)
    return _qualified_charge(row, item, valuation, amount, meter)


def _meter_fact_is_bound(conn: sqlite3.Connection, run_id: str, fact_id: str) -> bool:
    return (
        conn.execute(
            "SELECT 1 FROM meter_facts m JOIN causal_spans s ON s.span_key = m.span_key "
            "WHERE m.fact_id = ? AND s.run_id = ?",
            (fact_id, run_id),
        ).fetchone()
        is not None
    )


def _valuation_fields(valuation: Mapping[str, object]) -> tuple[str, int, str] | None:
    fact_id = valuation.get("fact_id")
    amount = valuation.get("amount_micros")
    charge_id = valuation.get("charge_id")
    if (
        not isinstance(fact_id, str)
        or isinstance(amount, bool)
        or not isinstance(amount, int)
        or amount < 0
        or not isinstance(charge_id, str)
    ):
        return None
    return fact_id, amount, charge_id


def _qualified_charge(
    row: sqlite3.Row | tuple[object, ...] | None,
    item: _Case,
    valuation: Mapping[str, object],
    amount: int,
    meter: Mapping[str, object],
) -> tuple[int | None, str | None, list[str]]:
    if row is None or not _charge_row_matches(row, item, valuation):
        return None, None, ["VALUATION_GROUP_MALFORMED"]
    if valuation.get("finality") != "final" or str(row[4]) != "final":
        return None, None, ["VALUATION_NOT_FINAL"]
    tariff_object = _tariff_object(row[5])
    if tariff_object is None:
        return None, None, ["VALUATION_GROUP_MALFORMED"]
    expected = _recomputed_list_rate_amount(meter, tariff_object)
    if expected is None:
        return None, None, ["METER_SCOPE_UNSUPPORTED"]
    if expected != amount:
        return None, None, ["LIST_RATE_RECOMPUTATION_MISMATCH"]
    return amount, _sha256(tariff_object), []


def _charge_row(
    conn: sqlite3.Connection, charge_id: str
) -> sqlite3.Row | tuple[object, ...] | None:
    sql = (
        "SELECT s.run_id, c.fact_id, c.amount_micros, c.authority, c.finality, c.tariff_json "
        "FROM charges c JOIN causal_spans s ON s.span_key = c.span_key WHERE c.charge_id = ?"
    )
    row = conn.execute(sql, (charge_id,)).fetchone()
    return cast(sqlite3.Row | tuple[object, ...] | None, row)


def _charge_row_matches(
    row: sqlite3.Row | tuple[object, ...], item: _Case, valuation: Mapping[str, object]
) -> bool:
    return (
        str(row[0]) == item.run_id
        and str(row[1]) == valuation.get("fact_id")
        and row[2] == valuation.get("amount_micros")
        and str(row[3]) == valuation.get("authority")
    )


def _tariff_object(value: object) -> dict[str, object] | None:
    if not isinstance(value, str):
        return None
    try:
        tariff = json.loads(value)
    except (json.JSONDecodeError, TypeError):
        return None
    if not isinstance(tariff, dict):
        return None
    rate_snapshot = tariff.get("rate_snapshot")
    if not isinstance(rate_snapshot, str) or not rate_snapshot:
        return None
    if tariff.get("discount") not in {None, False}:
        return None
    return cast(dict[str, object], tariff)


def _tariff_digest(value: object) -> str | None:
    tariff = _tariff_object(value)
    return _sha256(tariff) if tariff is not None else None


def _recomputed_list_rate_amount(
    meter: Mapping[str, object], tariff: Mapping[str, object]
) -> int | None:
    meter_name = meter.get("meter_name")
    rate_key = {
        "tokens.input": "input_rate_micros",
        "tokens.output": "output_rate_micros",
    }.get(str(meter_name))
    quantity = meter.get("quantity_micros")
    rate = tariff.get(rate_key) if rate_key is not None else None
    if (
        rate_key is None
        or isinstance(quantity, bool)
        or not isinstance(quantity, int)
        or quantity < 0
        or isinstance(rate, bool)
        or not isinstance(rate, int)
        or rate < 0
    ):
        return None
    # Meter quantities are millionths of a token. Tariff rates are micro-USD
    # per one million tokens, so the exact integer conversion denominator is
    # 10^12. v1 uses floor rounding and validates the stored amount against it.
    return quantity * rate // 1_000_000_000_000


def _measure_case(
    conn: sqlite3.Connection, item: _Case, sources: Sequence[str], policy: _Policy
) -> tuple[_Measure | None, list[str]]:
    receipt, load_reason = _safe_receipt(conn, item.run_id)
    if receipt is None:
        return None, [load_reason or "RECEIPT_MALFORMED"]
    reasons = _receipt_binding_reasons(receipt, item)
    reasons.extend(_source_reasons(receipt, sources))
    outcome, outcome_type, outcome_reasons = _outcome_measure(conn, receipt, item)
    amount, economic_reasons = _economic_measure(conn, receipt, item, policy)
    reasons.extend(outcome_reasons)
    reasons.extend(economic_reasons)
    if reasons or outcome is None or outcome_type is None or amount is None:
        return None, reasons or ["RECEIPT_MALFORMED"]
    digest = _receipt_digest(receipt)
    if digest is None:  # covered by the integrity checks above
        return None, ["RECEIPT_MALFORMED"]
    return _Measure(amount, outcome, outcome_type, digest, item.tariff_digest), []


def _pair_payload(
    case_id: str, baseline: _Case, candidate: _Case, left: _Measure, right: _Measure
) -> dict[str, object]:
    return {
        "case_id": case_id,
        "pair_id": baseline.pair_id,
        "task_version": baseline.task_version,
        "baseline_attempt_id": baseline.attempt_id,
        "candidate_attempt_id": candidate.attempt_id,
        "baseline_run_id": baseline.run_id,
        "candidate_run_id": candidate.run_id,
        "baseline_amount_micros": left.amount_micros,
        "candidate_amount_micros": right.amount_micros,
        "baseline_outcome_score": left.outcome_score,
        "candidate_outcome_score": right.outcome_score,
        "outcome_evidence_type": left.outcome_evidence_type,
        "tariff_digest": left.tariff_digest,
    }


def _collect_pairs(
    conn: sqlite3.Connection, baseline: _Arm, candidate: _Arm, policy: _Policy
) -> tuple[list[dict[str, object]], list[dict[str, object]], list[str]]:
    qualified: list[dict[str, object]] = []
    excluded: list[dict[str, object]] = []
    reasons: list[str] = []
    for left_case, right_case in zip(baseline.cases, candidate.cases, strict=True):
        left, left_reasons = _measure_case(conn, left_case, baseline.source_ids, policy)
        right, right_reasons = _measure_case(conn, right_case, candidate.source_ids, policy)
        pair_reasons = _ordered_reasons([*left_reasons, *right_reasons])
        if left is None or right is None or left.tariff_digest != right.tariff_digest:
            if left is not None and right is not None and left.tariff_digest != right.tariff_digest:
                pair_reasons = _ordered_reasons([*pair_reasons, "TARIFF_SCOPE_MISMATCH"])
            excluded.append({"case_id": left_case.case_id, "reason_codes": pair_reasons})
            reasons.extend(pair_reasons)
        elif left.outcome_evidence_type != right.outcome_evidence_type:
            pair_reasons = _ordered_reasons([*pair_reasons, "OUTCOME_BASIS_MISMATCH"])
            excluded.append({"case_id": left_case.case_id, "reason_codes": pair_reasons})
            reasons.extend(pair_reasons)
        else:
            qualified.append(_pair_payload(left_case.case_id, left_case, right_case, left, right))
    return qualified, excluded, reasons


def _signed_bps(numerator: int, denominator: int) -> int:
    if denominator <= 0:
        raise ZeroDivisionError("comparison denominator must be positive")
    magnitude = abs(numerator) * 10_000 // denominator
    return magnitude if numerator >= 0 else -magnitude


def _bootstrap_index(seed: bytes, sample: int, draw: int, size: int) -> int:
    retry = 0
    ceiling = 1 << 256
    acceptance_limit = ceiling - (ceiling % size)
    while True:
        counter = sample.to_bytes(8, "big") + draw.to_bytes(8, "big") + retry.to_bytes(8, "big")
        candidate = int.from_bytes(hashlib.sha256(seed + counter).digest(), "big")
        if candidate < acceptance_limit:
            return candidate % size
        retry += 1


def _sample_statistics(
    pairs: Sequence[Mapping[str, object]], policy: _Policy, sample: int, seed: bytes
) -> tuple[int, int]:
    baseline_total = candidate_total = outcome_delta = 0
    for draw in range(len(pairs)):
        pair = pairs[_bootstrap_index(seed, sample, draw, len(pairs))]
        baseline_total += cast(int, pair["baseline_amount_micros"])
        candidate_total += cast(int, pair["candidate_amount_micros"])
        outcome_delta += cast(int, pair["candidate_outcome_score"]) - cast(
            int, pair["baseline_outcome_score"]
        )
    return (
        _signed_bps(baseline_total - candidate_total, baseline_total),
        _signed_bps(outcome_delta, len(pairs)),
    )


def _bounds(values: list[int], confidence_bps: int) -> tuple[int, int]:
    values.sort()
    tail_bps = (10_000 - confidence_bps) // 2
    lower_index = len(values) * tail_bps // 10_000
    upper_index = len(values) - 1 - lower_index
    return values[lower_index], values[upper_index]


def _bootstrap_seed(pairs: Sequence[Mapping[str, object]]) -> bytes:
    """Bind resampling only to the quantitative paired observations.

    Manifest identifiers are caller-chosen labels.  Including them in the seed
    lets a caller grind semantically irrelevant aliases until a finite bootstrap
    crosses a decision threshold.  Sorting the quantitative tuples keeps the
    sampling distribution invariant to case labels and manifest ordering.
    """
    observations = sorted(
        (
            cast(int, item["baseline_amount_micros"]),
            cast(int, item["candidate_amount_micros"]),
            cast(int, item["baseline_outcome_score"]),
            cast(int, item["candidate_outcome_score"]),
        )
        for item in pairs
    )
    material = {
        "protocol": "forecost.economic-outcome/1-bootstrap-v1",
        "paired_observations": observations,
    }
    return hashlib.sha256(_canonical_json(material).encode("utf-8")).digest()


def _statistics(
    pairs: Sequence[Mapping[str, object]], policy: _Policy
) -> tuple[dict[str, object], dict[str, object]]:
    base = sum(cast(int, item["baseline_amount_micros"]) for item in pairs)
    candidate = sum(cast(int, item["candidate_amount_micros"]) for item in pairs)
    outcome_delta = sum(
        cast(int, item["candidate_outcome_score"]) - cast(int, item["baseline_outcome_score"])
        for item in pairs
    )
    seed = _bootstrap_seed(pairs)
    samples = [
        _sample_statistics(pairs, policy, sample, seed)
        for sample in range(policy.bootstrap_samples)
    ]
    economic_bounds = _bounds([item[0] for item in samples], policy.confidence_bps)
    outcome_bounds = _bounds([item[1] for item in samples], policy.confidence_bps)
    economics: dict[str, object] = {
        "baseline_total_micros": base,
        "candidate_total_micros": candidate,
        "observed_reduction_bps": _signed_bps(base - candidate, base),
        "confidence_lower_bps": economic_bounds[0],
        "confidence_upper_bps": economic_bounds[1],
    }
    outcomes: dict[str, object] = {
        "baseline_good_count": sum(cast(int, item["baseline_outcome_score"]) for item in pairs),
        "candidate_good_count": sum(cast(int, item["candidate_outcome_score"]) for item in pairs),
        "observed_difference_bps": _signed_bps(outcome_delta, len(pairs)),
        "confidence_lower_bps": outcome_bounds[0],
        "confidence_upper_bps": outcome_bounds[1],
    }
    return economics, outcomes


def _threshold_reasons(
    economics: Mapping[str, object], outcomes: Mapping[str, object], policy: _Policy
) -> list[str]:
    reasons: list[str] = []
    if cast(int, economics["confidence_lower_bps"]) < policy.min_reduction_bps:
        reasons.append("ECONOMIC_BOUND_NOT_MET")
    if cast(int, outcomes["confidence_lower_bps"]) < -policy.max_outcome_regression_bps:
        reasons.append("OUTCOME_BOUND_NOT_MET")
    return reasons


def _decision_status(reasons: Sequence[str]) -> str:
    if any(reason in _INVALID_REASONS for reason in reasons):
        return "invalid"
    if any(reason in _FAIL_REASONS for reason in reasons):
        return "fail"
    if reasons:
        return "abstain"
    return "pass"


def _base_result(
    *,
    mode: str,
    profile: str | None,
    authority: str,
    currency: str,
    line_items: Sequence[str],
    input_material: object,
) -> dict[str, object]:
    input_digest = _sha256(input_material)
    return {
        "schema": _OUTPUT_SCHEMA,
        "mode": mode,
        "profile": profile,
        "comparison_id": f"comparison:{input_digest}",
        "scope": {
            "authority": authority,
            "currency": currency,
            "line_items": list(line_items),
            "claim_mode": "observational",
        },
        "decision_basis": None,
        "input_digest": input_digest,
        "matching": {},
        "economics": None,
        "outcomes": None,
        "evidence": {
            "freshness_contract": (
                "frozen_receipt_snapshot" if mode == "matched_cohort" else "not_qualified"
            ),
            "external_declaration_boundary": "manifest_attested_not_authenticated",
        },
        "decision": {"status": "abstain", "reason_codes": []},
        "limitations": list(_LIMITATIONS),
    }


def _finalize(result: dict[str, object], reasons: Sequence[str]) -> dict[str, object]:
    ordered = _ordered_reasons(reasons)
    result["decision"] = {"status": _decision_status(ordered), "reason_codes": ordered}
    payload = {key: value for key, value in result.items() if key != "integrity"}
    result["integrity"] = {"algorithm": "sha256", "payload_digest": _sha256(payload)}
    return result


def compare_manifests(
    conn: sqlite3.Connection,
    baseline_manifest: Mapping[str, object],
    candidate_manifest: Mapping[str, object],
    policy: Mapping[str, object],
) -> dict[str, object]:
    """Evaluate a digest-bound matched cohort under the v1 profile.

    Input shape violations raise :class:`ComparisonConfigurationError`.  Validly
    shaped inputs whose bindings or evidence fail return a signed-shape result
    with ``decision.status`` set to ``invalid`` or ``abstain``.
    """
    baseline, baseline_digest_ok = _arm(baseline_manifest, "baseline")
    candidate, candidate_digest_ok = _arm(candidate_manifest, "candidate")
    parsed_policy = _policy(policy)
    material = {
        "baseline_manifest_digest": baseline.manifest_digest,
        "candidate_manifest_digest": candidate.manifest_digest,
        "policy_digest": _sha256(policy),
    }
    result = _base_result(
        mode="matched_cohort",
        profile=_PROFILE_SCHEMA,
        authority=parsed_policy.authority,
        currency=parsed_policy.currency,
        line_items=parsed_policy.line_items,
        input_material=material,
    )
    result["decision_basis"] = _decision_basis(parsed_policy, str(material["policy_digest"]))
    result["input_bindings"] = _input_bindings(baseline, candidate, parsed_policy)
    reasons = [] if baseline_digest_ok and candidate_digest_ok else ["MANIFEST_DIGEST_MISMATCH"]
    reasons.extend(_binding_reasons(baseline, candidate, parsed_policy))
    if reasons:
        result["matching"] = _matching_payload(parsed_policy, [], [])
        return _finalize(result, reasons)
    with _validated_snapshot(conn) as (snapshot, validation_reason):
        if validation_reason is not None:
            reasons.append(validation_reason)
            result["matching"] = _matching_payload(parsed_policy, [], [])
            return _finalize(result, reasons)
        if snapshot is None:  # pragma: no cover - context contract
            raise RuntimeError("comparison snapshot was not created")
        reasons.extend(_evaluate_snapshot(snapshot, baseline, candidate, parsed_policy, result))
    return _finalize(result, reasons)


def _evaluate_snapshot(
    snapshot: sqlite3.Connection,
    baseline: _Arm,
    candidate: _Arm,
    policy: _Policy,
    result: dict[str, object],
) -> list[str]:
    """Match pairs on the validated snapshot, filling ``result``; return reasons."""
    pairs, excluded, reasons = _collect_pairs(snapshot, baseline, candidate, policy)
    result["matching"] = _matching_payload(policy, pairs, excluded)
    if len(pairs) < policy.min_pairs:
        reasons.append("MINIMUM_PAIRS_NOT_MET")
    if not reasons and any(cast(int, item["baseline_amount_micros"]) <= 0 for item in pairs):
        reasons.append("ZERO_BASELINE_DENOMINATOR")
    if not reasons:
        economics, outcomes = _statistics(pairs, policy)
        result["economics"] = economics
        result["outcomes"] = outcomes
        reasons.extend(_threshold_reasons(economics, outcomes, policy))
    return reasons


def validate_comparison_inputs(
    baseline_manifest: Mapping[str, object],
    candidate_manifest: Mapping[str, object],
    policy: Mapping[str, object],
) -> None:
    """Validate the strict v1 JSON shapes without opening or reading a ledger."""
    _arm(baseline_manifest, "baseline")
    _arm(candidate_manifest, "candidate")
    _policy(policy)


def validate_diagnostic_inputs(
    baseline_run_id: str,
    candidate_run_id: str,
    *,
    authority: str = "list_rate",
    currency: str = "USD",
    line_items: Sequence[str] = ("model_inference",),
) -> None:
    """Validate diagnostic scope before a CLI boundary opens the ledger."""
    _diagnostic_scope(
        baseline_run_id,
        candidate_run_id,
        authority=authority,
        currency=currency,
        line_items=line_items,
    )


@contextmanager
def _validated_snapshot(
    source: sqlite3.Connection,
) -> Iterator[tuple[sqlite3.Connection | None, str | None]]:
    """Yield one frozen, journal-validated in-memory comparison snapshot.

    SQLite's backup API includes committed WAL pages. Rebuilding only this
    private in-memory copy detects projection drift and guarantees that the
    subsequent decision reads the exact state that was validated.
    """
    if source.in_transaction:
        raise sqlite3.OperationalError(
            "comparison requires a settled source connection before snapshotting"
        )
    count_row = source.execute("SELECT COUNT(*) FROM journal_observations").fetchone()
    if count_row is None:  # pragma: no cover - aggregate invariant
        raise sqlite3.DatabaseError("journal row count was unavailable")
    if int(count_row[0]) > _MAX_VALIDATION_JOURNAL_ROWS:
        yield None, "PROJECTION_VALIDATION_RESOURCE_LIMIT"
        return

    snapshot = sqlite3.connect(":memory:")
    snapshot.row_factory = sqlite3.Row
    try:
        source.backup(snapshot)
        snapshot.execute("PRAGMA foreign_keys=ON")
        reason = _snapshot_validation_reason(snapshot)
        snapshot.execute("PRAGMA query_only=ON")
        yield snapshot, reason
    finally:
        snapshot.close()


def _snapshot_validation_reason(snapshot: sqlite3.Connection) -> str | None:
    if verify_journal_chain(snapshot).state != "intact":
        return "JOURNAL_INTEGRITY_NOT_INTACT"
    before = _projection_digest(snapshot)
    from forecost.ledger.evidence import rebuild_projections

    snapshot.execute("SAVEPOINT forecost_compare_projection_check")
    try:
        rebuild_projections(snapshot)
        after = _projection_digest(snapshot)
        snapshot.execute("RELEASE forecost_compare_projection_check")
    except (ValueError, TypeError, KeyError, sqlite3.IntegrityError):
        snapshot.execute("ROLLBACK TO forecost_compare_projection_check")
        snapshot.execute("RELEASE forecost_compare_projection_check")
        return "PROJECTION_REBUILD_FAILED"
    except BaseException:
        snapshot.execute("ROLLBACK TO forecost_compare_projection_check")
        snapshot.execute("RELEASE forecost_compare_projection_check")
        raise
    return "PROJECTION_INTEGRITY_MISMATCH" if before != after else None


def _quote_identifier(name: str) -> str:
    return '"' + name.replace('"', '""') + '"'


def _update_table_digest(
    update: Callable[[bytes], object], conn: sqlite3.Connection, table: str
) -> None:
    quoted_table = _quote_identifier(table)
    info = conn.execute(f"PRAGMA table_info({quoted_table})").fetchall()
    columns = [str(row[1]) for row in info]
    primary_key = [
        name for _, name in sorted((int(row[5]), str(row[1])) for row in info if int(row[5]) > 0)
    ]
    order = ",".join(_quote_identifier(column) for column in (primary_key or columns))
    update(_canonical_json({"table": table, "columns": columns}).encode("utf-8"))
    update(b"\n")
    # Table names are a fixed internal inventory; identifiers are quoted.
    cursor = conn.execute(f"SELECT * FROM {quoted_table} ORDER BY {order}")  # nosec B608  # noqa: S608
    while rows := cursor.fetchmany(1_000):
        for row in rows:
            update(_canonical_json([row[column] for column in columns]).encode("utf-8"))
            update(b"\n")


def _projection_digest(conn: sqlite3.Connection) -> str:
    tables = (
        "causal_run_identities",
        "causal_span_identities",
        "causal_runs",
        "causal_spans",
        "span_links",
        "meter_facts",
        "charges",
        "outcome_evidence",
    )
    digest = hashlib.sha256()
    for table in tables:
        _update_table_digest(digest.update, conn, table)
    return digest.hexdigest()


def _matching_payload(
    policy: _Policy,
    pairs: Sequence[Mapping[str, object]],
    excluded: Sequence[Mapping[str, object]],
) -> dict[str, object]:
    return {
        "expected_pairs": len(policy.expected_case_ids),
        "qualified_pairs": len(pairs),
        "minimum_pairs": policy.min_pairs,
        "pairs": list(pairs),
        "excluded": list(excluded),
    }


def _decision_basis(policy: _Policy, policy_digest: str) -> dict[str, object]:
    return {
        "schema": _PROFILE_SCHEMA,
        "policy_digest": policy_digest,
        "min_pairs": policy.min_pairs,
        "min_reduction_bps": policy.min_reduction_bps,
        "max_outcome_regression_bps": policy.max_outcome_regression_bps,
        "confidence_bps": policy.confidence_bps,
        "bootstrap_samples": policy.bootstrap_samples,
        "interval_method": "deterministic_sha256_counter_paired_bootstrap",
        "freshness_contract": "frozen_receipt_snapshot",
        "claim_mode": "observational",
    }


def _input_bindings(baseline: _Arm, candidate: _Arm, policy: _Policy) -> dict[str, object]:
    return {
        "baseline_manifest_digest": baseline.manifest_digest,
        "candidate_manifest_digest": candidate.manifest_digest,
        "baseline_dataset_digest": baseline.dataset_digest,
        "candidate_dataset_digest": candidate.dataset_digest,
        "policy_dataset_digest": policy.dataset_digest,
        "baseline_task_set_digest": baseline.task_set_digest,
        "candidate_task_set_digest": candidate.task_set_digest,
        "policy_task_set_digest": policy.task_set_digest,
        "baseline_configuration_digest": baseline.configuration_digest,
        "candidate_configuration_digest": candidate.configuration_digest,
        "policy_baseline_configuration_digest": policy.baseline_configuration_digest,
        "policy_candidate_configuration_digest": policy.candidate_configuration_digest,
        "baseline_privacy_profile": baseline.privacy_profile,
        "candidate_privacy_profile": candidate.privacy_profile,
        "expected_source_ids": list(policy.expected_source_ids),
    }


def _diagnostic_total(
    conn: sqlite3.Connection,
    receipt: Mapping[str, object],
    run_id: str,
    authority: str,
    currency: str,
    line_items: Sequence[str],
) -> tuple[int | None, tuple[str, ...] | None]:
    groups = receipt.get("valuation_groups")
    if not isinstance(groups, list):
        return None, None
    amounts: list[int] = []
    tariffs: list[str] = []
    for group in groups:
        value = _diagnostic_group(conn, group, run_id, authority, currency, line_items)
        if value is None:
            continue
        amount, tariff = value
        amounts.append(amount)
        tariffs.append(tariff)
    return (sum(amounts), tuple(sorted(set(tariffs)))) if amounts else (None, None)


def _diagnostic_group(
    conn: sqlite3.Connection,
    value: object,
    run_id: str,
    authority: str,
    currency: str,
    line_items: Sequence[str],
) -> tuple[int, str] | None:
    if not isinstance(value, Mapping) or value.get("currency") != currency:
        return None
    if value.get("line_item") not in line_items:
        return None
    valuations = value.get("valuations")
    if not isinstance(valuations, list):
        return None
    matches = [item for item in valuations if _authority_matches(item, authority)]
    return (
        _diagnostic_valuation(conn, cast(Mapping[str, object], matches[0]), run_id)
        if len(matches) == 1
        else None
    )


def _diagnostic_valuation(
    conn: sqlite3.Connection, valuation: Mapping[str, object], run_id: str
) -> tuple[int, str] | None:
    amount = valuation.get("amount_micros")
    charge_id = valuation.get("charge_id")
    fact_id = valuation.get("fact_id")
    if (
        valuation.get("finality") != "final"
        or not isinstance(amount, int)
        or isinstance(amount, bool)
        or not isinstance(fact_id, str)
        or not _meter_fact_is_bound(conn, run_id, fact_id)
    ):
        return None
    row = _charge_row(conn, str(charge_id)) if isinstance(charge_id, str) else None
    tariff = _tariff_digest(row[5]) if row is not None and str(row[0]) == run_id else None
    return (amount, tariff) if tariff is not None else None


def _diagnostic_scope(
    baseline_run_id: str,
    candidate_run_id: str,
    *,
    authority: str = "list_rate",
    currency: str = "USD",
    line_items: Sequence[str] = ("model_inference",),
) -> tuple[str, str, str, str, tuple[str, ...]]:
    baseline_id = _atom(baseline_run_id, "baseline_run_id")
    candidate_id = _atom(candidate_run_id, "candidate_run_id")
    allowed = {item.value for item in Authority}
    if authority not in allowed:
        raise ComparisonConfigurationError("diagnostic authority is unsupported")
    currency_value = _atom(currency, "currency")
    items = tuple(_atom(item, "line_item") for item in line_items)
    if not items or len(items) > _MAX_LINE_ITEMS or len(set(items)) != len(items):
        raise ComparisonConfigurationError("diagnostic line_items must be bounded and unique")
    return baseline_id, candidate_id, authority, currency_value, items


def compare_runs_diagnostic(
    conn: sqlite3.Connection,
    baseline_run_id: str,
    candidate_run_id: str,
    *,
    authority: str = "list_rate",
    currency: str = "USD",
    line_items: Sequence[str] = ("model_inference",),
) -> dict[str, object]:
    """Describe two runs without treating them as a qualified experiment."""
    baseline_id, candidate_id, authority, currency_value, items = _diagnostic_scope(
        baseline_run_id,
        candidate_run_id,
        authority=authority,
        currency=currency,
        line_items=line_items,
    )
    material = {
        "baseline_run_id": baseline_id,
        "candidate_run_id": candidate_id,
        "authority": authority,
        "currency": currency_value,
        "line_items": list(items),
    }
    result = _base_result(
        mode="diagnostic",
        profile=None,
        authority=authority,
        currency=currency_value,
        line_items=items,
        input_material=material,
    )
    reasons = ["COMPARISON_MANIFEST_REQUIRED"]
    with _validated_snapshot(conn) as (snapshot, validation_reason):
        if validation_reason is not None:
            reasons.append(validation_reason)
        else:
            if snapshot is None:  # pragma: no cover - context contract
                raise RuntimeError("comparison snapshot was not created")
            left, left_reason = _safe_receipt(snapshot, baseline_id)
            right, right_reason = _safe_receipt(snapshot, candidate_id)
            reasons.extend(reason for reason in (left_reason, right_reason) if reason is not None)
            _add_diagnostic_economics(result, snapshot, left, right, material)
    result["matching"] = {"expected_pairs": None, "qualified_pairs": 0, "minimum_pairs": 30}
    return _finalize(result, reasons)


def _add_diagnostic_economics(
    result: dict[str, object],
    conn: sqlite3.Connection,
    left: Mapping[str, object] | None,
    right: Mapping[str, object] | None,
    material: Mapping[str, object],
) -> None:
    if left is None or right is None:
        return
    scope = cast(Mapping[str, object], result["scope"])
    args = (
        str(scope["authority"]),
        str(scope["currency"]),
        cast(list[str], scope["line_items"]),
    )
    left_total, left_tariffs = _diagnostic_total(
        conn, left, str(material["baseline_run_id"]), *args
    )
    right_total, right_tariffs = _diagnostic_total(
        conn, right, str(material["candidate_run_id"]), *args
    )
    if left_total is None or right_total is None or left_tariffs != right_tariffs:
        return
    result["economics"] = {
        "baseline_total_micros": left_total,
        "candidate_total_micros": right_total,
        "observed_delta_micros": right_total - left_total,
        "tariff_digests": list(left_tariffs or ()),
    }


_EXIT_CODES = {"pass": 0, "fail": 2, "abstain": 3, "invalid": 4}  # nosec B105 - statuses


def comparison_exit_code(result: Mapping[str, object]) -> int:
    """Map a comparison decision to its stable process exit code."""
    decision = result.get("decision")
    status = decision.get("status") if isinstance(decision, Mapping) else None
    return _EXIT_CODES.get(str(status), 5)


def comparison_text(result: Mapping[str, object], markdown: bool = False) -> str:
    """Render a bounded human summary without widening the result claims."""
    decision = result.get("decision")
    decision_map = decision if isinstance(decision, Mapping) else {}
    status = str(decision_map.get("status", "invalid")).upper()
    reasons = decision_map.get("reason_codes")
    reason_text = ", ".join(str(item) for item in reasons) if isinstance(reasons, list) else ""
    heading = "# Forecost comparison" if markdown else "Forecost comparison"
    lines = [heading, f"Decision: {status}", f"Reasons: {reason_text or 'none'}"]
    lines.extend(_text_matching(result.get("matching")))
    lines.extend(_text_economics(result.get("economics")))
    lines.extend(_text_outcomes(result.get("outcomes")))
    lines.extend(_text_scope(result))
    return "\n".join(lines)


def _text_scope(result: Mapping[str, object]) -> list[str]:
    scope = result.get("scope")
    scope_map = scope if isinstance(scope, Mapping) else {}
    authority = str(scope_map.get("authority", "unknown"))
    currency = str(scope_map.get("currency", "unknown"))
    if result.get("mode") == "matched_cohort":
        return [
            f"Scope: observed paired difference; {currency} {authority} equivalent only.",
            "Evaluator and source declarations are manifest-attested, not authenticated.",
        ]
    return [
        f"Scope: unqualified diagnostic delta; authority={authority}, currency={currency}.",
        "No cohort manifest, workload match, or evaluator binding was supplied.",
    ]


def _text_matching(value: object) -> list[str]:
    if not isinstance(value, Mapping):
        return []
    qualified = value.get("qualified_pairs", 0)
    expected = value.get("expected_pairs", "unknown")
    return [f"Pairs: {qualified}/{expected} qualified"]


def _text_economics(value: object) -> list[str]:
    if not isinstance(value, Mapping):
        return ["Economics: withheld"]
    if "observed_reduction_bps" in value:
        return [
            "Economics: "
            f"baseline={value.get('baseline_total_micros')} USD-micros, "
            f"candidate={value.get('candidate_total_micros')} USD-micros, "
            f"difference={value.get('observed_reduction_bps')}bps"
        ]
    return [
        "Economics: "
        f"baseline={value.get('baseline_total_micros')} USD-micros, "
        f"candidate={value.get('candidate_total_micros')} USD-micros, "
        f"delta={value.get('observed_delta_micros')} USD-micros"
    ]


def _text_outcomes(value: object) -> list[str]:
    if not isinstance(value, Mapping):
        return ["Outcomes: withheld"]
    return [
        "Outcomes: "
        f"baseline_good={value.get('baseline_good_count')}, "
        f"candidate_good={value.get('candidate_good_count')}, "
        f"difference={value.get('observed_difference_bps')}bps"
    ]
