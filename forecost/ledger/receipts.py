"""Deterministic, content-minimized run receipts built from causal projections."""

from __future__ import annotations

import hashlib
import json
import sqlite3
from collections import defaultdict
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, cast

from forecost.evidence_profiles import (
    BUILTIN_PROFILES,
    ECONOMIC_ESTIMATE_V1,
    OUTCOME_V1,
    STRUCTURAL_V1,
    EvidenceSignal,
    assess_claim,
)
from forecost.ledger.contracts import (
    RECEIPT_SCHEMA_VERSION,
    Authority,
    EvidenceState,
    Finality,
    opaque_id,
)

_AUTHORITY_ORDER = {
    Authority.BILLED.value: 0,
    Authority.PROVIDER_ESTIMATE.value: 1,
    Authority.GATEWAY_ESTIMATE.value: 2,
    # A local file is an attributable claim, not authenticated provider truth.
    # Preserve it, but do not let it displace a provider/gateway valuation for
    # the same fact.  Canonical selection still chooses exactly one candidate.
    Authority.USER_IMPORTED_CLAIM.value: 3,
    Authority.LIST_RATE.value: 4,
    Authority.CONTRACT_ALLOCATION.value: 5,
    Authority.SUBSCRIPTION_QUOTA.value: 6,
    Authority.UNKNOWN.value: 7,
}

_OUTCOME_ROLES = {
    "explicit_mark": "human",
    "test_exit": "deterministic_test",
    "build_exit": "deterministic_test",
    "git_fact": "ci",
}


def _canonical_json(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def _row_dict(row: sqlite3.Row) -> dict[str, Any]:
    return {key: row[key] for key in row.keys()}  # noqa: SIM118 - sqlite Row is not a dict


@dataclass(frozen=True)
class _SupersessionSet:
    active: list[dict[str, Any]]
    invalid_source_ids: frozenset[str]


def _is_valid_supersession(
    source: dict[str, Any],
    target: dict[str, Any] | None,
    scope_key: Callable[[dict[str, Any]], object] | None,
) -> bool:
    if target is None:
        return False
    if int(target["journal_sequence"]) >= int(source["journal_sequence"]):
        return False
    return scope_key is None or scope_key(target) == scope_key(source)


def _supersession_set(
    rows: list[dict[str, Any]],
    *,
    identity_key: str,
    supersedes_key: str,
    scope_key: Callable[[dict[str, Any]], object] | None = None,
) -> _SupersessionSet:
    by_id = {str(row[identity_key]): row for row in rows}
    valid_targets: set[str] = set()
    invalid_sources: set[str] = set()
    for row in rows:
        target_id = row[supersedes_key]
        if target_id is None:
            continue
        target = by_id.get(str(target_id))
        if not _is_valid_supersession(row, target, scope_key):
            invalid_sources.add(str(row[identity_key]))
        else:
            valid_targets.add(str(target_id))
    return _SupersessionSet(
        active=[row for row in rows if str(row[identity_key]) not in valid_targets],
        invalid_source_ids=frozenset(invalid_sources),
    )


def _charge_supersession_set(rows: list[dict[str, Any]]) -> _SupersessionSet:
    return _supersession_set(
        rows,
        identity_key="charge_id",
        supersedes_key="supersedes_charge_id",
        scope_key=lambda row: (
            str(row["fact_id"] or row["span_key"]),
            str(row["currency"]),
            str(row["line_item"]),
        ),
    )


def _active_charges(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return _charge_supersession_set(rows).active


def _active_outcomes(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return _outcome_supersession_set(rows).active


def _outcome_supersession_set(rows: list[dict[str, Any]]) -> _SupersessionSet:
    return _supersession_set(
        rows,
        identity_key="evidence_id",
        supersedes_key="supersedes_evidence_id",
        scope_key=lambda row: _OUTCOME_ROLES.get(
            str(row["evidence_type"]), str(row["evidence_type"])
        ),
    )


def _outcomes_conflicted(rows: list[dict[str, Any]]) -> bool:
    # Good and bad are directly incompatible even when independent source roles
    # disagree. Partial/unknown evidence remains visible but cannot on its own
    # establish which decisive status is false without case-attempt identity.
    statuses = {str(row["outcome_status"]) for row in rows}
    return {"good", "bad"}.issubset(statuses)


def _economic_fact_key(row: dict[str, Any]) -> str:
    return str(row["fact_id"] or row["span_key"])


def _canonical_charges(rows: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], bool]:
    """Select one authority per economic line without adding alternatives."""
    grouped: dict[tuple[str, str, str], list[dict[str, Any]]] = defaultdict(list)
    supersession = _charge_supersession_set(rows)
    for row in supersession.active:
        key = (_economic_fact_key(row), row["currency"], row["line_item"])
        grouped[key].append(row)
    chosen: list[dict[str, Any]] = []
    conflicted = bool(supersession.invalid_source_ids)
    for candidates in grouped.values():
        candidates.sort(
            key=lambda row: (
                _AUTHORITY_ORDER.get(row["authority"], 99),
                row["observed_at"],
                row["charge_id"],
            )
        )
        canonical = candidates[0]
        chosen.append(canonical)
        same_authority = [row for row in candidates if row["authority"] == canonical["authority"]]
        if len({row["amount_micros"] for row in same_authority}) > 1:
            conflicted = True
    return chosen, conflicted


def _interval_union_micros(intervals: list[tuple[datetime, datetime]]) -> int:
    if not intervals:
        return 0
    merged: list[tuple[datetime, datetime]] = []
    for start, end in sorted(intervals):
        if end <= start:
            continue
        if not merged or start > merged[-1][1]:
            merged.append((start, end))
        else:
            merged[-1] = (merged[-1][0], max(merged[-1][1], end))
    return sum(int((end - start).total_seconds() * 1_000_000) for start, end in merged)


def _span_interval(row: dict[str, Any]) -> tuple[datetime, datetime]:
    if (
        row["timing_semantic"] != "explicit_interval"
        or row["started_at"] is None
        or row["ended_at"] is None
    ):
        raise ValueError("span lacks a complete explicit interval")
    return (
        datetime.fromisoformat(row["started_at"]).astimezone(timezone.utc),
        datetime.fromisoformat(row["ended_at"]).astimezone(timezone.utc),
    )


def _causal_predecessors(
    spans: list[dict[str, Any]], links: list[tuple[str, str]]
) -> dict[str, set[str]]:
    span_keys = {str(row["span_key"]) for row in spans}
    predecessors: dict[str, set[str]] = {span_key: set() for span_key in span_keys}
    for row in spans:
        span_key = str(row["span_key"])
        parent = row["parent_span_key"]
        if parent in span_keys:
            predecessors[span_key].add(str(parent))
    for span_key, linked_span_key in links:
        if span_key in span_keys and linked_span_key in span_keys:
            predecessors[span_key].add(linked_span_key)
    return predecessors


def _has_causal_cycle(spans: list[dict[str, Any]], links: list[tuple[str, str]]) -> bool:
    predecessors = _causal_predecessors(spans, links)
    successors: dict[str, set[str]] = defaultdict(set)
    remaining = {span_key: len(parents) for span_key, parents in predecessors.items()}
    for span_key, parents in predecessors.items():
        for parent in parents:
            successors[parent].add(span_key)
    ready = [span_key for span_key, count in remaining.items() if count == 0]
    visited = 0
    while ready:
        parent = ready.pop()
        visited += 1
        for child in successors[parent]:
            remaining[child] -= 1
            if remaining[child] == 0:
                ready.append(child)
    return visited != len(predecessors)


def _has_retry_cycle(spans: list[dict[str, Any]]) -> bool:
    """Return whether explicit ``attempt_of`` lineage contains a cycle.

    Retry lineage is independent from parent/fan-in topology.  It therefore
    needs its own validation rather than being folded into the scheduling-edge
    calculation used by the timing summary.
    """
    span_keys = {str(row["span_key"]) for row in spans}
    predecessor = {
        str(row["span_key"]): str(row["attempt_of_span_key"])
        for row in spans
        if row["attempt_of_span_key"] in span_keys
    }
    complete: set[str] = set()
    for origin in sorted(span_keys):
        path: set[str] = set()
        current = origin
        while current in predecessor and current not in complete:
            if current in path:
                return True
            path.add(current)
            current = predecessor[current]
        complete.update(path)
    return False


def _has_complete_explicit_interval(row: dict[str, Any]) -> bool:
    return (
        row["timing_semantic"] == "explicit_interval"
        and row["started_at"] is not None
        and row["ended_at"] is not None
        and row["duration_micros"] is not None
    )


def _timing_payload(
    *,
    state: str,
    basis: str,
    spans: list[dict[str, Any]],
    known: int,
    critical_path: int | None = None,
    service: int | None = None,
    wait: int | None = None,
    elapsed: int | None = None,
) -> dict[str, object]:
    return {
        "state": state,
        "basis": basis,
        "critical_path": critical_path,
        "service": service,
        "wait": wait,
        "elapsed": elapsed,
        "spans_total": len(spans),
        "spans_with_duration": known,
    }


def _incomplete_timing_summary(
    spans: list[dict[str, Any]], *, known: int, cycle_detected: bool
) -> tuple[dict[str, object], bool]:
    return (
        _timing_payload(
            state="unknown" if known == 0 else "partial",
            basis="explicit_span_timing_required",
            spans=spans,
            known=known,
        ),
        cycle_detected,
    )


def _elapsed_envelope_micros(intervals: list[tuple[datetime, datetime]]) -> int:
    starts = [start for start, _ in intervals]
    ends = [end for _, end in intervals]
    return int((max(ends) - min(starts)).total_seconds() * 1_000_000)


def _trivial_critical_path(spans: list[dict[str, Any]], links: list[tuple[str, str]]) -> int | None:
    if len(spans) != 1 or links or spans[0]["parent_span_key"] is not None:
        return None
    start, end = _span_interval(spans[0])
    return int((end - start).total_seconds() * 1_000_000)


def _complete_timing_basis(*, cycle_detected: bool, critical_path: int | None) -> str:
    prefix = "explicit_interval_unions_and_elapsed_envelope"
    if cycle_detected:
        return f"{prefix};critical_path_withheld_causal_cycle"
    if critical_path is None:
        return f"{prefix};critical_path_withheld_untyped_execution_edges"
    return f"{prefix};critical_path_trivial_single_span"


def _complete_timing_summary(
    spans: list[dict[str, Any]], links: list[tuple[str, str]], *, known: int
) -> tuple[dict[str, object], bool]:
    intervals = [(row, _span_interval(row)) for row in spans]
    service_intervals = [
        interval for row, interval in intervals if row["operation_kind"] != "queue_wait"
    ]
    wait_intervals = [
        interval for row, interval in intervals if row["operation_kind"] == "queue_wait"
    ]
    cycle_detected = _has_causal_cycle(spans, links)
    critical_path = None if cycle_detected else _trivial_critical_path(spans, links)
    state = "invalid" if cycle_detected else "complete" if critical_path is not None else "partial"
    return (
        _timing_payload(
            state=state,
            basis=_complete_timing_basis(
                cycle_detected=cycle_detected,
                critical_path=critical_path,
            ),
            spans=spans,
            known=known,
            critical_path=critical_path,
            service=_interval_union_micros(service_intervals),
            wait=_interval_union_micros(wait_intervals),
            elapsed=_elapsed_envelope_micros([interval for _, interval in intervals]),
        ),
        cycle_detected,
    )


def _timing_summary(
    spans: list[dict[str, Any]], links: list[tuple[str, str]]
) -> tuple[dict[str, object], bool]:
    """Return interval-safe wall timing without inventing execution dependencies.

    Service and wait are independent unions of their classified intervals, so
    neither nested nor parallel spans double-count within an aggregate. They may
    overlap each other and therefore are not additive. Elapsed is the wall-clock
    envelope and includes gaps. Current parent/fan-in edges describe trace
    topology, not typed scheduling dependencies, so a non-trivial critical path
    is withheld. Occurrence and observation timestamps are never endpoints.
    """
    known = sum(row["duration_micros"] is not None for row in spans)
    cycle_detected = _has_causal_cycle(spans, links)
    complete_intervals = bool(spans) and all(_has_complete_explicit_interval(row) for row in spans)
    if not complete_intervals:
        return _incomplete_timing_summary(
            spans,
            known=known,
            cycle_detected=cycle_detected,
        )
    return _complete_timing_summary(spans, links, known=known)


@dataclass(frozen=True)
class _StructuralObservation:
    producer: str
    observed_at: datetime
    span_id: str
    parent_span_id: str | None
    lifecycle: str
    journal_sequence: int


@dataclass(frozen=True)
class _ReceiptRows:
    run: sqlite3.Row
    spans: list[dict[str, Any]]
    meters: list[dict[str, Any]]
    charges: list[dict[str, Any]]
    outcomes: list[dict[str, Any]]
    reconciliations: list[dict[str, Any]]
    sources: list[str]
    structural_observations: list[_StructuralObservation]
    links: list[tuple[str, str]]


def _query_dicts(conn: sqlite3.Connection, sql: str, run_id: str) -> list[dict[str, Any]]:
    return [_row_dict(row) for row in conn.execute(sql, (run_id,)).fetchall()]


def _load_receipt_rows(conn: sqlite3.Connection, run_id: str) -> _ReceiptRows:
    run = conn.execute("SELECT * FROM causal_runs WHERE run_id = ?", (run_id,)).fetchone()
    if run is None:
        raise ValueError("run not found")
    spans = _query_dicts(
        conn, "SELECT * FROM causal_spans WHERE run_id = ? ORDER BY source_order", run_id
    )
    meters = _query_dicts(
        conn,
        "SELECT m.* FROM meter_facts m JOIN causal_spans s ON s.span_key = m.span_key "
        "WHERE s.run_id = ? ORDER BY m.occurred_at, m.fact_id",
        run_id,
    )
    charges = _query_dicts(
        conn,
        "SELECT c.*, j.producer AS source, j.journal_sequence FROM charges c "
        "JOIN causal_spans s ON s.span_key = c.span_key "
        "JOIN journal_observations j ON j.observation_id = c.observation_id "
        "WHERE s.run_id = ? ORDER BY c.occurred_at, c.charge_id",
        run_id,
    )
    outcomes = _query_dicts(
        conn,
        "SELECT o.*, j.producer AS source, j.journal_sequence FROM outcome_evidence o "
        "JOIN journal_observations j ON j.observation_id = o.observation_id "
        "WHERE o.run_id = ? ORDER BY o.observed_at, o.evidence_id",
        run_id,
    )
    reconciliations = _query_dicts(
        conn,
        "SELECT r.*, "
        "CASE WHEN EXISTS (SELECT 1 FROM reconciliation_batches newer "
        "                  WHERE newer.supersedes_batch_id = r.batch_id) "
        "     THEN 0 ELSE 1 END AS active, "
        "(SELECT COUNT(*) FROM reconciliation_evidence e "
        " WHERE e.batch_id = r.batch_id AND e.source_role = 'local' "
        " AND e.match_state = 'exact_identity') AS exact_match_count "
        "FROM reconciliation_batches r WHERE r.run_id = ? "
        "ORDER BY r.created_at, r.batch_id",
        run_id,
    )
    return _ReceiptRows(
        run=run,
        spans=spans,
        meters=meters,
        charges=charges,
        outcomes=outcomes,
        reconciliations=reconciliations,
        sources=_load_sources(conn, run_id),
        structural_observations=_load_structural_observations(conn, run_id),
        links=_load_links(conn, run_id),
    )


def _load_sources(conn: sqlite3.Connection, run_id: str) -> list[str]:
    rows = conn.execute(
        "SELECT DISTINCT j.producer FROM journal_observations j "
        "JOIN causal_spans s "
        "ON s.trace_id = json_extract(j.causal_json, '$.trace_id') "
        "AND s.span_id = json_extract(j.causal_json, '$.span_id') "
        "WHERE s.run_id = ? ORDER BY j.producer",
        (run_id,),
    ).fetchall()
    return [str(row[0]) for row in rows]


def _load_structural_observations(
    conn: sqlite3.Connection, run_id: str
) -> list[_StructuralObservation]:
    rows = conn.execute(
        "SELECT producer, observed_at, "
        "json_extract(causal_json, '$.span_id') AS span_id, "
        "json_extract(causal_json, '$.parent_span_id') AS parent_span_id, "
        "json_extract(payload_json, '$.lifecycle') AS lifecycle, journal_sequence "
        "FROM journal_observations WHERE event_kind = 'span' "
        "AND json_extract(causal_json, '$.run_id') = ? "
        "ORDER BY journal_sequence",
        (run_id,),
    ).fetchall()
    return [
        _StructuralObservation(
            producer=str(row["producer"]),
            observed_at=datetime.fromisoformat(str(row["observed_at"])).astimezone(timezone.utc),
            span_id=str(row["span_id"]),
            parent_span_id=(
                str(row["parent_span_id"]) if row["parent_span_id"] is not None else None
            ),
            lifecycle=str(row["lifecycle"]),
            journal_sequence=int(row["journal_sequence"]),
        )
        for row in rows
    ]


def _load_links(conn: sqlite3.Connection, run_id: str) -> list[tuple[str, str]]:
    rows = conn.execute(
        "SELECT l.span_key, l.linked_span_key FROM span_links l "
        "JOIN causal_spans s ON s.span_key = l.span_key "
        "WHERE s.run_id = ? ORDER BY l.span_key, l.linked_span_key",
        (run_id,),
    ).fetchall()
    return [(row["span_key"], row["linked_span_key"]) for row in rows]


def _economic_totals(charges: list[dict[str, Any]]) -> dict[str, dict[str, int]]:
    totals: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    for charge in charges:
        totals[charge["currency"]][charge["authority"]] += charge["amount_micros"]
    return {currency: dict(values) for currency, values in sorted(totals.items())}


def _expected_sources(run: sqlite3.Row) -> list[str]:
    try:
        coverage = json.loads(run["source_coverage_json"])
    except (TypeError, json.JSONDecodeError):
        return []
    if not isinstance(coverage, dict):
        return []
    return sorted(value for value in coverage.get("sources_expected", []) if isinstance(value, str))


def _evidence_state(
    spans: list[dict[str, Any]],
    meters: list[dict[str, Any]],
    charges: list[dict[str, Any]],
    *,
    conflicted: bool,
    missing_sources: list[str],
) -> str:
    if not spans:
        return EvidenceState.UNKNOWN.value
    if conflicted:
        return EvidenceState.CONFLICTED.value
    finalities = {row["finality"] for row in [*meters, *charges]}
    if (
        missing_sources
        or Finality.PROVISIONAL.value in finalities
        or Finality.UNKNOWN.value in finalities
    ):
        return EvidenceState.INCOMPLETE.value
    if not meters and not charges:
        return EvidenceState.UNKNOWN.value
    return EvidenceState.COMPLETE.value


def _select_outcome(outcomes: list[dict[str, Any]]) -> dict[str, Any] | None:
    outcome_rank = {"explicit_mark": 3, "test_exit": 2, "build_exit": 2, "git_fact": 1}
    if not outcomes:
        return None
    return max(
        outcomes,
        key=lambda row: (
            row["outcome_status"] != "unknown",
            outcome_rank.get(row["evidence_type"], 0),
            row["observed_at"],
            row["evidence_id"],
        ),
    )


def _causal_graph(spans: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "span_key": row["span_key"],
            "span_id": row["span_id"],
            "parent_span_key": row["parent_span_key"],
            "parent_span_id": row["parent_span_id"],
            "operation_kind": row["operation_kind"],
            "lifecycle": row["lifecycle"],
            "branch_id": row["branch_id"],
            "attempt_of_span_key": row["attempt_of_span_key"],
            "attempt_of_span_id": row["attempt_of_span_id"],
            "checkpoint_id": row["checkpoint_id"],
            "timing": {
                "state": (
                    "complete"
                    if row["duration_micros"] is not None
                    else "partial"
                    if row["timing_semantic"] is not None
                    else "unknown"
                ),
                "started_at": row["started_at"],
                "ended_at": row["ended_at"],
                "duration_micros": row["duration_micros"],
                "semantic": row["timing_semantic"],
                "producer": row["timing_producer"],
            },
        }
        for row in spans
    ]


def _topology_blind_spots(rows: _ReceiptRows, span_keys: set[str]) -> list[str]:
    blind_spots: list[str] = []
    if any(row["parent_span_key"] not in (None, *span_keys) for row in rows.spans):
        blind_spots.append("missing_parent")
    if any(linked_span_key not in span_keys for _, linked_span_key in rows.links):
        blind_spots.append("missing_link_target")
    if any(row["attempt_of_span_key"] not in (None, *span_keys) for row in rows.spans):
        blind_spots.append("missing_attempt_target")
    return blind_spots


def _timing_blind_spot(spans: list[dict[str, Any]]) -> str | None:
    if not spans:
        return None
    timing_known = sum(row["duration_micros"] is not None for row in spans)
    if timing_known == 0:
        return "span_timing_unknown"
    if timing_known < len(spans):
        return "span_timing_incomplete"
    if any(row["timing_semantic"] != "explicit_interval" for row in spans):
        return "span_timing_incomplete"
    return None


def _known_blind_spots(
    rows: _ReceiptRows,
    missing_sources: list[str],
    cycle_detected: bool,
) -> list[str]:
    span_keys = {row["span_key"] for row in rows.spans}
    blind_spots = [*missing_sources, *_topology_blind_spots(rows, span_keys)]
    timing_gap = _timing_blind_spot(rows.spans)
    if timing_gap is not None:
        blind_spots.append(timing_gap)
    if cycle_detected:
        blind_spots.append("causal_cycle")
    if _has_retry_cycle(rows.spans):
        blind_spots.append("retry_lineage_cycle")
    return sorted(blind_spots)


def _stored_json_object(value: object, *, field: str) -> dict[str, object]:
    try:
        decoded = json.loads(str(value))
    except (TypeError, json.JSONDecodeError) as error:
        raise ValueError(f"stored {field} is not valid JSON") from error
    if not isinstance(decoded, dict):
        raise ValueError(f"stored {field} must be a JSON object")
    return cast(dict[str, object], decoded)


def _meter_payload(meters: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "fact_id": row["fact_id"],
            "span_key": row["span_key"],
            "span_id": row["span_id"],
            "meter_name": row["meter_name"],
            "unit": row["unit"],
            "quantity_micros": row["quantity_micros"],
            "aggregation": row["aggregation"],
            "dimensions": _stored_json_object(row["dimensions_json"], field="meter dimensions"),
            "source": row["source"],
            "finality": row["finality"],
            "observed_at": row["observed_at"],
        }
        for row in meters
    ]


def _charge_payload(charges: list[dict[str, Any]]) -> list[dict[str, Any]]:
    keys = (
        "charge_id",
        "fact_id",
        "span_key",
        "span_id",
        "amount_micros",
        "currency",
        "authority",
        "line_item",
        "account_scope",
        "billing_period",
        "source",
        "finality",
        "observed_at",
        "supersedes_charge_id",
    )
    return [
        {
            **{key: row[key] for key in keys},
            "tariff": _stored_json_object(row["tariff_json"], field="charge tariff"),
        }
        for row in charges
    ]


def _reconciliation_payload(rows: list[dict[str, Any]]) -> list[dict[str, object]]:
    """Expose stored reconciliation provenance without legacy provider labels."""

    def semantic_source_set(row: dict[str, Any]) -> dict[str, object]:
        source_set = _stored_json_object(row["source_set_json"], field="reconciliation source set")
        # Reconciliation v1's historical ``provider`` storage label described
        # the arbitrary local file import path, not authenticated provider
        # provenance. Preserve that truth at the receipt boundary.
        legacy_value = source_set.pop("provider", None)
        if legacy_value is not None and "user_imported_claim" not in source_set:
            source_set["user_imported_claim"] = legacy_value
        return dict(sorted(source_set.items()))

    return [
        {
            "batch_id": row["batch_id"],
            "schema_version": row["schema_version"],
            "active": bool(row["active"]),
            "source_set": semantic_source_set(row),
            "account_scope": row["account_scope"],
            "dimensions": _stored_json_object(
                row["dimensions_json"], field="reconciliation dimensions"
            ),
            "window_start": row["window_start"],
            "window_end": row["window_end"],
            "watermarks": _stored_json_object(
                row["watermarks_json"], field="reconciliation watermarks"
            ),
            "expected_count": row["expected_count"],
            "observed_count": row["observed_count"],
            "exact_match_count": row["exact_match_count"],
            "unmatched_local_count": row["unmatched_local_count"],
            "unmatched_user_imported_claim_count": row["unmatched_provider_count"],
            "local_amount_micros": row["local_amount_micros"],
            "user_imported_claim_amount_micros": row["provider_amount_micros"],
            "residual_micros": row["residual_micros"],
            "tolerance_micros": row["tolerance_micros"],
            "finality": row["finality"],
            "state": row["state"],
            "created_at": row["created_at"],
            "supersedes_batch_id": row["supersedes_batch_id"],
        }
        for row in rows
    ]


def _valuation_groups(
    charges: list[dict[str, Any]], selected_charges: list[dict[str, Any]]
) -> list[dict[str, object]]:
    """Retain every competing valuation while identifying the non-additive choice."""
    supersession = _charge_supersession_set(charges)
    selected_ids = {str(row["charge_id"]) for row in selected_charges}
    grouped: dict[tuple[str, str, str], list[dict[str, Any]]] = defaultdict(list)
    for row in supersession.active:
        grouped[(_economic_fact_key(row), row["currency"], row["line_item"])].append(row)
    result: list[dict[str, object]] = []
    for (fact_key, currency, line_item), candidates in sorted(grouped.items()):
        ordered = sorted(
            candidates,
            key=lambda row: (
                _AUTHORITY_ORDER.get(row["authority"], 99),
                row["observed_at"],
                row["charge_id"],
            ),
        )
        selected = next(row for row in ordered if str(row["charge_id"]) in selected_ids)
        alternatives = []
        for row in ordered:
            charge = _charge_payload([row])[0]
            charge["selected"] = row["charge_id"] == selected["charge_id"]
            charge["supersession_valid"] = (
                None
                if row["supersedes_charge_id"] is None
                else str(row["charge_id"]) not in supersession.invalid_source_ids
            )
            alternatives.append(charge)
        result.append(
            {
                "economic_fact_key": fact_key,
                "currency": currency,
                "line_item": line_item,
                "canonical_charge_id": selected["charge_id"],
                "selection_reason": "authority_precedence_then_observation_then_identity",
                "aggregation_rule": "alternatives_not_additive",
                "valuations": alternatives,
            }
        )
    return result


def _outcome_payload(outcome: dict[str, Any] | None) -> dict[str, Any]:
    if outcome is None:
        return {"status": "unknown", "confidence": "unknown"}
    return {
        "status": outcome["outcome_status"],
        "reason_code": outcome["reason_code"],
        "evidence_type": outcome["evidence_type"],
        "source": outcome["source"],
        "confidence": outcome["confidence"],
    }


def _outcome_evidence_payload(outcomes: list[dict[str, Any]]) -> list[dict[str, Any]]:
    supersession = _outcome_supersession_set(outcomes)
    active_ids = {str(row["evidence_id"]) for row in supersession.active}
    return [
        {
            "evidence_id": row["evidence_id"],
            "status": row["outcome_status"],
            "reason_code": row["reason_code"],
            "evidence_type": row["evidence_type"],
            "source": row["source"],
            "confidence": row["confidence"],
            "observed_at": row["observed_at"],
            "supersedes_evidence_id": row["supersedes_evidence_id"],
            "supersession_valid": (
                None
                if row["supersedes_evidence_id"] is None
                else str(row["evidence_id"]) not in supersession.invalid_source_ids
            ),
            "active": str(row["evidence_id"]) in active_ids,
        }
        for row in outcomes
    ]


def _producer_role(producer: str) -> str | None:
    known = {
        opaque_id("producer", "otel"): "otel",
        opaque_id("producer", "offline_lab"): "runtime",
        opaque_id("producer", "claude_code"): "runtime",
        opaque_id("producer", "openai_agents"): "runtime",
        opaque_id("producer", "langgraph"): "runtime",
        opaque_id("producer", "litellm"): "gateway",
    }
    return known.get(producer)


def _observed_at(row: dict[str, Any]) -> datetime:
    return datetime.fromisoformat(str(row["observed_at"])).astimezone(timezone.utc)


def _branches_are_closed(spans: list[dict[str, Any]]) -> bool:
    if not spans:
        return False
    terminal = {"completed", "failed", "cancelled"}
    return all(row["lifecycle"] in terminal for row in spans)


def _structural_observation_signals(
    observation: _StructuralObservation,
) -> list[EvidenceSignal]:
    role = _producer_role(observation.producer)
    if role not in {"runtime", "otel"}:
        return []
    signals = [EvidenceSignal("run_identity", role, observation.observed_at)]
    if observation.parent_span_id is None:
        signals.append(EvidenceSignal("root_span", role, observation.observed_at))
    return signals


def _lifecycle_contradiction(rows: _ReceiptRows) -> _StructuralObservation | None:
    by_span: dict[str, list[_StructuralObservation]] = defaultdict(list)
    for observation in rows.structural_observations:
        if _producer_role(observation.producer) in {"runtime", "otel"}:
            by_span[observation.span_id].append(observation)
    terminal = {"completed", "failed", "cancelled"}
    contradictions: list[_StructuralObservation] = []
    for observations in by_span.values():
        terminal_lifecycle: str | None = None
        for observation in sorted(
            observations,
            key=lambda item: (item.observed_at, item.journal_sequence),
        ):
            if terminal_lifecycle is not None and observation.lifecycle != terminal_lifecycle:
                contradictions.append(observation)
            if observation.lifecycle in terminal:
                terminal_lifecycle = observation.lifecycle
    return (
        max(contradictions, key=lambda item: (item.observed_at, item.journal_sequence))
        if contradictions
        else None
    )


def _structural_contradiction(rows: _ReceiptRows) -> _StructuralObservation | None:
    candidates = [item for item in (_lifecycle_contradiction(rows),) if item is not None]
    if _has_causal_cycle(rows.spans, rows.links) or _has_retry_cycle(rows.spans):
        candidates.extend(
            item
            for item in rows.structural_observations
            if _producer_role(item.producer) in {"runtime", "otel"}
        )
    return (
        max(candidates, key=lambda item: (item.observed_at, item.journal_sequence))
        if candidates
        else None
    )


def _required_structural_role(observation: _StructuralObservation) -> str:
    role = _producer_role(observation.producer)
    if role not in {"runtime", "otel"}:  # pragma: no cover - callers filter candidates
        raise ValueError("structural observation lacks an eligible producer role")
    return role


def _contradictory_closure_signal(observation: _StructuralObservation) -> EvidenceSignal:
    return EvidenceSignal(
        "branch_closure",
        _required_structural_role(observation),
        observation.observed_at,
        closed=False,
        contradictory=True,
    )


def _latest_terminal_observation(rows: _ReceiptRows) -> _StructuralObservation | None:
    terminal = {"completed", "failed", "cancelled"}
    candidates = [
        item
        for item in rows.structural_observations
        if item.lifecycle in terminal and _producer_role(item.producer) in {"runtime", "otel"}
    ]
    return (
        max(candidates, key=lambda item: (item.observed_at, item.journal_sequence))
        if candidates
        else None
    )


def _topology_is_closed(rows: _ReceiptRows) -> bool:
    span_keys = {str(row["span_key"]) for row in rows.spans}
    missing_sources = set(_expected_sources(rows.run)) - set(rows.sources)
    return (
        not missing_sources
        and not _topology_blind_spots(rows, span_keys)
        and _branches_are_closed(rows.spans)
    )


def _closure_signal(rows: _ReceiptRows) -> EvidenceSignal | None:
    contradiction = _structural_contradiction(rows)
    if contradiction is not None:
        return _contradictory_closure_signal(contradiction)
    if not _topology_is_closed(rows):
        return None
    observation = _latest_terminal_observation(rows)
    if observation is None:
        return None
    return EvidenceSignal(
        "branch_closure",
        _required_structural_role(observation),
        observation.observed_at,
        closed=True,
    )


def _structural_signals(rows: _ReceiptRows) -> list[EvidenceSignal]:
    signals: list[EvidenceSignal] = []
    for observation in rows.structural_observations:
        signals.extend(_structural_observation_signals(observation))
    closure = _closure_signal(rows)
    if closure is not None:
        signals.append(closure)
    return signals


def _meter_signal(row: dict[str, Any]) -> EvidenceSignal | None:
    role = _producer_role(str(row["source"]))
    if role not in {"runtime", "gateway", "otel"}:
        return None
    return EvidenceSignal(
        "meter_fact",
        role,
        _observed_at(row),
        finality=str(row["finality"]),
    )


def _meter_signals(rows: list[dict[str, Any]]) -> list[EvidenceSignal]:
    signals: list[EvidenceSignal] = []
    for row in rows:
        signal = _meter_signal(row)
        if signal is not None:
            signals.append(signal)
    return signals


def _valuation_role(authority: str) -> str | None:
    if authority == Authority.LIST_RATE.value:
        return "pricing_table"
    if authority in {Authority.GATEWAY_ESTIMATE.value, Authority.PROVIDER_ESTIMATE.value}:
        return "gateway"
    return None


def _valuation_signal(row: dict[str, Any], *, valuation_conflicted: bool) -> EvidenceSignal | None:
    role = _valuation_role(str(row["authority"]))
    if role is None:
        return None
    return EvidenceSignal(
        "valuation",
        role,
        _observed_at(row),
        finality=str(row["finality"]),
        contradictory=valuation_conflicted,
    )


def _valuation_signals(
    rows: list[dict[str, Any]], *, valuation_conflicted: bool
) -> list[EvidenceSignal]:
    signals: list[EvidenceSignal] = []
    for row in _active_charges(rows):
        signal = _valuation_signal(row, valuation_conflicted=valuation_conflicted)
        if signal is not None:
            signals.append(signal)
    return signals


def _reconciliation_time(row: dict[str, Any]) -> datetime:
    return datetime.fromisoformat(str(row["created_at"])).astimezone(timezone.utc)


def _reconciliation_source_set(row: dict[str, Any]) -> dict[str, object]:
    try:
        source_set = json.loads(str(row["source_set_json"]))
    except json.JSONDecodeError:
        return {}
    return source_set if isinstance(source_set, dict) else {}


def _economic_scope_signal(row: dict[str, Any], *, closed: bool) -> EvidenceSignal | None:
    if not closed or row["observed_count"] != row["expected_count"]:
        return None
    return EvidenceSignal(
        "economic_scope",
        "reconciler",
        _reconciliation_time(row),
        finality=str(row["finality"]),
        closed=True,
        contradictory=row["state"] == "discrepant",
    )


def _billing_scope_signal(row: dict[str, Any], *, closed: bool) -> EvidenceSignal | None:
    if _reconciliation_source_set(row).get("provider_authenticated") is not True:
        return None
    return EvidenceSignal(
        "billing_scope_join",
        "reconciler",
        _reconciliation_time(row),
        finality=str(row["finality"]),
        closed=closed,
    )


def _reconciliation_signals(rows: list[dict[str, Any]]) -> list[EvidenceSignal]:
    signals: list[EvidenceSignal] = []
    for row in rows:
        if not bool(row["active"]):
            continue
        closed = row["state"] in {"reconciled", "discrepant"}
        for signal in (
            _economic_scope_signal(row, closed=closed),
            _billing_scope_signal(row, closed=closed),
        ):
            if signal is not None:
                signals.append(signal)
    return signals


def _outcome_signals(row: dict[str, Any], *, outcome_conflicted: bool) -> list[EvidenceSignal]:
    role = _OUTCOME_ROLES.get(str(row["evidence_type"]))
    if role is None:
        return []
    observed = _observed_at(row)
    return [
        EvidenceSignal(
            obligation,
            role,
            observed,
            finality="final",
            closed=row["outcome_status"] != "unknown",
            contradictory=outcome_conflicted,
        )
        for obligation in ("outcome_identity", "outcome_result")
    ]


def _all_outcome_signals(rows: list[dict[str, Any]]) -> list[EvidenceSignal]:
    supersession = _outcome_supersession_set(rows)
    conflicted = bool(supersession.invalid_source_ids) or _outcomes_conflicted(supersession.active)
    signals: list[EvidenceSignal] = []
    for row in supersession.active:
        signals.extend(_outcome_signals(row, outcome_conflicted=conflicted))
    return signals


def _assess_profiles(
    signals: list[EvidenceSignal], assessment_time: datetime
) -> dict[str, dict[str, object]]:
    # A local authority label cannot satisfy authenticated provider billing or
    # protected-CI obligations. Those profiles need separate proof producers.
    relevant_signals = {
        STRUCTURAL_V1.profile_id: signals,
        ECONOMIC_ESTIMATE_V1.profile_id: signals,
        OUTCOME_V1.profile_id: signals,
        "provider-billed": [],
        "ci": [],
    }
    assessments: dict[str, dict[str, object]] = {}
    for profile_id, profile in BUILTIN_PROFILES.items():
        selected = relevant_signals.get(profile_id, signals)
        assessments[profile_id] = assess_claim(profile, selected, as_of=assessment_time).as_dict()
    return assessments


def _claim_assessments(
    rows: _ReceiptRows,
    *,
    as_of: str,
    valuation_conflicted: bool,
) -> dict[str, dict[str, object]]:
    """Evaluate built-in claim denominators without inferring caller intent."""
    assessment_time = datetime.fromisoformat(as_of).astimezone(timezone.utc)
    signals = [
        *_structural_signals(rows),
        *_meter_signals(rows.meters),
        *_valuation_signals(rows.charges, valuation_conflicted=valuation_conflicted),
        *_reconciliation_signals(rows.reconciliations),
        *_all_outcome_signals(rows.outcomes),
    ]
    return _assess_profiles(signals, assessment_time)


def _assessment_as_of(rows: _ReceiptRows) -> str:
    observed = [
        str(rows.run["observed_at"]),
        *(str(row["observed_at"]) for row in rows.spans),
        *(str(row["observed_at"]) for row in rows.meters),
        *(str(row["observed_at"]) for row in rows.charges),
        *(str(row["observed_at"]) for row in rows.outcomes),
        *(str(row["created_at"]) for row in rows.reconciliations),
        *(item.observed_at.isoformat() for item in rows.structural_observations),
    ]
    return max(
        observed,
        key=lambda value: datetime.fromisoformat(value).astimezone(timezone.utc),
    )


def _receipt_payload(rows: _ReceiptRows, run_id: str) -> dict[str, object]:
    outcome_supersession = _outcome_supersession_set(rows.outcomes)
    active_outcomes = outcome_supersession.active
    outcome_conflicted = bool(outcome_supersession.invalid_source_ids) or _outcomes_conflicted(
        active_outcomes
    )
    selected_charges, conflicted = _canonical_charges(rows.charges)
    expected_sources = _expected_sources(rows.run)
    missing_sources = sorted(set(expected_sources) - set(rows.sources))
    timing, cycle_detected = _timing_summary(rows.spans, rows.links)
    as_of = _assessment_as_of(rows)
    claims = _claim_assessments(rows, as_of=as_of, valuation_conflicted=conflicted)
    payload: dict[str, object] = {
        "schema_version": RECEIPT_SCHEMA_VERSION,
        "run_id": run_id,
        "conversation_id": rows.run["conversation_id"],
        "trace_id": rows.run["trace_id"],
        "as_of": as_of,
        "lifecycle": rows.run["lifecycle"],
        "stop_reason": rows.run["stop_reason"],
        "evidence": {
            "legacy_projection_state": _evidence_state(
                rows.spans,
                rows.meters,
                selected_charges,
                conflicted=conflicted,
                missing_sources=missing_sources,
            ),
            "sources_expected": expected_sources,
            "sources_present": rows.sources,
            "freshness_as_of": as_of,
            "known_blind_spots": _known_blind_spots(rows, missing_sources, cycle_detected),
            "claim_profiles": claims,
        },
        "causal_graph": _causal_graph(rows.spans),
        "timing_micros": timing,
        "meter_facts": _meter_payload(rows.meters),
        "economic_totals_micros": _economic_totals(selected_charges),
        "charges": _charge_payload(selected_charges),
        "valuation_groups": _valuation_groups(rows.charges, selected_charges),
        "reconciliation_batches": _reconciliation_payload(rows.reconciliations),
        "outcome": _outcome_payload(
            None if outcome_conflicted else _select_outcome(active_outcomes)
        ),
        "outcome_evidence": _outcome_evidence_payload(rows.outcomes),
    }
    return payload


def build_receipt(conn: sqlite3.Connection, run_id: str) -> dict[str, object]:
    """Build a receipt whose bytes depend only on the stored evidence set."""
    payload = _receipt_payload(_load_receipt_rows(conn, run_id), run_id)
    digest = hashlib.sha256(_canonical_json(payload).encode("utf-8")).hexdigest()
    payload["integrity"] = {"algorithm": "sha256", "payload_digest": digest}
    return payload


def save_receipt(conn: sqlite3.Connection, receipt: dict[str, object]) -> str:
    """Persist a receipt snapshot idempotently; it is an artifact, not a mutation of facts."""
    integrity = receipt["integrity"]
    if not isinstance(integrity, dict):  # pragma: no cover - build_receipt contract
        raise ValueError("receipt lacks integrity")
    receipt_id = f"receipt:{integrity['payload_digest']}"
    evidence = receipt["evidence"]
    if not isinstance(evidence, dict):  # pragma: no cover - build_receipt contract
        raise ValueError("receipt lacks evidence")
    profiles = evidence.get("claim_profiles")
    evidence_state = "unknown"
    if isinstance(profiles, dict):
        structural = profiles.get("structural")
        if isinstance(structural, dict):
            evidence_state = str(structural.get("state", "unknown"))
    conn.execute(
        """
        INSERT OR IGNORE INTO receipt_snapshots(
            receipt_id, run_id, schema_version, generated_at, evidence_state, payload_json
        ) VALUES (?,?,?,?,?,?)
        """,
        (
            receipt_id,
            receipt["run_id"],
            receipt["schema_version"],
            receipt["as_of"],
            evidence_state,
            _canonical_json(receipt),
        ),
    )
    conn.commit()
    return receipt_id


@dataclass(frozen=True)
class _ReceiptTextParts:
    evidence: dict[str, object]
    timing: dict[str, object]
    outcome: dict[str, object]
    totals: dict[str, object]
    integrity: dict[str, object]


def _receipt_text_parts(receipt: dict[str, object]) -> _ReceiptTextParts:
    evidence = receipt["evidence"]
    timing = receipt["timing_micros"]
    outcome = receipt["outcome"]
    totals = receipt["economic_totals_micros"]
    integrity = receipt["integrity"]
    if not all(isinstance(value, dict) for value in (evidence, timing, outcome, totals, integrity)):
        raise ValueError("invalid receipt shape")
    return _ReceiptTextParts(
        evidence=cast(dict[str, object], evidence),
        timing=cast(dict[str, object], timing),
        outcome=cast(dict[str, object], outcome),
        totals=cast(dict[str, object], totals),
        integrity=cast(dict[str, object], integrity),
    )


def _profile_line(profile_id: object, value: dict[object, object]) -> str:
    unmet = value.get("unmet_obligations", [])
    unmet_text = ",".join(str(item) for item in unmet) if isinstance(unmet, list) else ""
    return (
        "  {profile}: completeness={completeness} freshness={freshness} "
        "contradiction={contradiction} satisfied={satisfied}/{denominator} "
        "unmet={unmet}"
    ).format(
        profile=profile_id,
        completeness=value.get("completeness", "unknown"),
        freshness=value.get("freshness", "unknown"),
        contradiction=value.get("contradiction", "unknown"),
        satisfied=value.get("satisfied", 0),
        denominator=value.get("denominator", 0),
        unmet=unmet_text or "none",
    )


def _profile_lines(evidence: dict[str, object]) -> list[str]:
    profiles = evidence.get("claim_profiles")
    if not isinstance(profiles, dict):
        return []
    return [
        _profile_line(profile_id, value)
        for profile_id, value in sorted(profiles.items())
        if isinstance(value, dict)
    ]


def _blind_spot_lines(evidence: dict[str, object]) -> list[str]:
    blind_spots = evidence.get("known_blind_spots", [])
    if isinstance(blind_spots, list) and blind_spots:
        return ["Known blind spots: " + ", ".join(str(item) for item in blind_spots)]
    return []


def _receipt_timing_line(timing: dict[str, object]) -> str:
    if all(timing.get(key) is not None for key in ("service", "wait", "elapsed")):
        critical = timing.get("critical_path")
        critical_text = (
            f"critical path {critical}us"
            if critical is not None
            else "critical path withheld (execution-edge semantics unavailable)"
        )
        return (
            "Timing (explicit interval unions; service/wait not additive): "
            "wall-service {service}us | wall-wait {wait}us | "
            "elapsed envelope {elapsed}us | {critical}"
        ).format(
            service=timing["service"],
            wait=timing["wait"],
            elapsed=timing["elapsed"],
            critical=critical_text,
        )
    return (
        "Timing: {state}; critical path/service/wait not claimed "
        "without complete explicit span intervals"
    ).format(state=timing.get("state", "unknown"))


def _economic_total_lines(totals: dict[str, object]) -> list[str]:
    lines: list[str] = []
    for currency, by_authority in totals.items():
        if isinstance(by_authority, dict):
            lines.append(
                f"  {currency}: "
                + ", ".join(
                    f"{authority}={amount}" for authority, amount in sorted(by_authority.items())
                )
            )
    return lines


def receipt_text(receipt: dict[str, object], *, markdown: bool = False) -> str:
    """Render a compact stable receipt with no color or terminal assumptions."""
    parts = _receipt_text_parts(receipt)
    heading = "# Forecost run receipt" if markdown else "Forecost run receipt"
    lines = [
        heading,
        f"Run: {receipt['run_id']}",
        "Evidence profiles (receipt v2; no global completeness claim):",
    ]
    lines.extend(_profile_lines(parts.evidence))
    lines.extend(_blind_spot_lines(parts.evidence))
    lines.append(f"Lifecycle: {receipt['lifecycle']} | outcome: {parts.outcome['status']}")
    lines.append(_receipt_timing_line(parts.timing))
    lines.append("Economic totals (micros):")
    lines.extend(_economic_total_lines(parts.totals))
    lines.append(
        "Integrity (local consistency only; same-user rewrite not excluded): "
        f"sha256:{parts.integrity['payload_digest']}"
    )
    return "\n".join(lines) + "\n"
