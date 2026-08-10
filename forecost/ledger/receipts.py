"""Deterministic, content-free run receipts built from causal projections."""

from __future__ import annotations

import hashlib
import json
import sqlite3
from collections import defaultdict
from datetime import datetime, timezone
from typing import Any, cast

from forecost.ledger.contracts import RECEIPT_SCHEMA_VERSION, Authority, EvidenceState, Finality

_AUTHORITY_ORDER = {
    Authority.BILLED.value: 0,
    Authority.PROVIDER_ESTIMATE.value: 1,
    Authority.GATEWAY_ESTIMATE.value: 2,
    Authority.LIST_RATE.value: 3,
    Authority.CONTRACT_ALLOCATION.value: 4,
    Authority.SUBSCRIPTION_QUOTA.value: 5,
    Authority.UNKNOWN.value: 6,
}


def _canonical_json(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def _row_dict(row: sqlite3.Row) -> dict[str, Any]:
    return {key: row[key] for key in row.keys()}  # noqa: SIM118 - sqlite Row is not a dict


def _duration_micros(start: str, end: str) -> int:
    return int(
        (datetime.fromisoformat(end).astimezone(timezone.utc)
        - datetime.fromisoformat(start).astimezone(timezone.utc)).total_seconds()
        * 1_000_000
    )


def _active_charges(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    superseded = {row["supersedes_charge_id"] for row in rows if row["supersedes_charge_id"]}
    return [row for row in rows if row["charge_id"] not in superseded]


def _canonical_charges(rows: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], bool]:
    """Select one authority per economic line without adding alternatives."""
    grouped: dict[tuple[str, str, str], list[dict[str, Any]]] = defaultdict(list)
    for row in _active_charges(rows):
        key = (row["fact_id"] or row["span_id"], row["currency"], row["line_item"])
        grouped[key].append(row)
    chosen: list[dict[str, Any]] = []
    conflicted = False
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


def _critical_path(
    spans: list[dict[str, Any]], links: list[tuple[str, str]]
) -> tuple[int, int, int, bool]:
    """Return causal critical path plus aggregate service/wait time.

    Parent spans frequently enclose their children. Counting both full
    durations exaggerates a path, so a parent's own contribution excludes the
    union of direct child intervals that overlap it. Fan-in links are additional
    causal predecessors. Cycles are surfaced instead of being silently treated
    as a valid DAG.
    """
    by_id = {row["span_id"]: row for row in spans}
    children: dict[str, list[str]] = defaultdict(list)
    predecessors: dict[str, set[str]] = defaultdict(set)
    for row in spans:
        parent = row["parent_span_id"]
        if parent in by_id:
            children[parent].append(row["span_id"])
            predecessors[row["span_id"]].add(parent)
    for span_id, linked_span_id in links:
        if span_id in by_id and linked_span_id in by_id:
            predecessors[span_id].add(linked_span_id)
    memo: dict[str, int] = {}
    cycle_detected = False

    def interval(row: dict[str, Any]) -> tuple[datetime, datetime]:
        return (
            datetime.fromisoformat(row["occurred_at"]).astimezone(timezone.utc),
            datetime.fromisoformat(row["observed_at"]).astimezone(timezone.utc),
        )

    def exclusive_duration(span_id: str) -> int:
        start, end = interval(by_id[span_id])
        own = max(0, int((end - start).total_seconds() * 1_000_000))
        covered: list[tuple[datetime, datetime]] = []
        for child_id in children[span_id]:
            child_start, child_end = interval(by_id[child_id])
            clipped = (max(start, child_start), min(end, child_end))
            if clipped[1] > clipped[0]:
                covered.append(clipped)
        return max(0, own - _interval_union_micros(covered))

    def path_duration(span_id: str, active: set[str]) -> int:
        nonlocal cycle_detected
        if span_id in memo:
            return memo[span_id]
        if span_id in active:
            cycle_detected = True
            return 0
        previous = [
            path_duration(parent, active | {span_id})
            for parent in sorted(predecessors[span_id])
        ]
        result = exclusive_duration(span_id) + max(previous, default=0)
        memo[span_id] = result
        return result

    durations = [path_duration(row["span_id"], set()) for row in spans]
    wait = sum(
        max(0, _duration_micros(row["occurred_at"], row["observed_at"]))
        for row in spans
        if row["operation_kind"] == "queue_wait"
    )
    service = sum(
        max(0, _duration_micros(row["occurred_at"], row["observed_at"]))
        for row in spans
        if row["operation_kind"] != "queue_wait"
    )
    return max(durations, default=0), service, wait, cycle_detected


def build_receipt(conn: sqlite3.Connection, run_id: str) -> dict[str, object]:
    """Build a receipt whose bytes depend only on the stored evidence set."""
    run = conn.execute("SELECT * FROM causal_runs WHERE run_id = ?", (run_id,)).fetchone()
    if run is None:
        raise ValueError("run not found")
    spans = [_row_dict(row) for row in conn.execute(
        "SELECT * FROM causal_spans WHERE run_id = ? ORDER BY source_order", (run_id,)
    ).fetchall()]
    meters = [_row_dict(row) for row in conn.execute(
        "SELECT m.* FROM meter_facts m JOIN causal_spans s ON s.span_id = m.span_id "
        "WHERE s.run_id = ? ORDER BY m.occurred_at, m.fact_id",
        (run_id,),
    ).fetchall()]
    charges = [_row_dict(row) for row in conn.execute(
        "SELECT c.* FROM charges c JOIN causal_spans s ON s.span_id = c.span_id "
        "WHERE s.run_id = ? ORDER BY c.occurred_at, c.charge_id",
        (run_id,),
    ).fetchall()]
    outcomes = [
        _row_dict(row)
        for row in conn.execute(
            "SELECT * FROM outcome_evidence WHERE run_id = ? ORDER BY observed_at, evidence_id",
            (run_id,),
        ).fetchall()
    ]
    sources = [row[0] for row in conn.execute(
        "SELECT DISTINCT j.producer FROM journal_observations j "
        "JOIN causal_spans s ON s.span_id = json_extract(j.causal_json, '$.span_id') "
        "WHERE s.run_id = ? ORDER BY j.producer",
        (run_id,),
    ).fetchall()]
    links = [
        (row["span_id"], row["linked_span_id"])
        for row in conn.execute(
            "SELECT l.span_id, l.linked_span_id FROM span_links l "
            "JOIN causal_spans s ON s.span_id = l.span_id "
            "WHERE s.run_id = ? ORDER BY l.span_id, l.linked_span_id",
            (run_id,),
        ).fetchall()
    ]
    selected_charges, conflicted = _canonical_charges(charges)
    totals: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    for charge in selected_charges:
        totals[charge["currency"]][charge["authority"]] += charge["amount_micros"]
    finalities = {row["finality"] for row in [*meters, *selected_charges]}
    try:
        coverage = json.loads(run["source_coverage_json"])
    except (TypeError, json.JSONDecodeError):
        coverage = {}
    expected_sources = (
        sorted(value for value in coverage.get("sources_expected", []) if isinstance(value, str))
        if isinstance(coverage, dict)
        else []
    )
    missing_sources = sorted(set(expected_sources) - set(sources))
    if not spans:
        evidence_state = EvidenceState.UNKNOWN.value
    elif conflicted:
        evidence_state = EvidenceState.CONFLICTED.value
    elif (
        missing_sources
        or Finality.PROVISIONAL.value in finalities
        or Finality.UNKNOWN.value in finalities
    ):
        evidence_state = EvidenceState.INCOMPLETE.value
    elif not meters and not charges:
        evidence_state = EvidenceState.UNKNOWN.value
    else:
        evidence_state = EvidenceState.COMPLETE.value
    critical_path, service_time, wait_time, cycle_detected = _critical_path(spans, links)
    span_ids = {row["span_id"] for row in spans}
    missing_parent = any(
        row["parent_span_id"] is not None and row["parent_span_id"] not in span_ids
        for row in spans
    )
    missing_link = any(linked_span_id not in span_ids for _, linked_span_id in links)
    observed = [row["observed_at"] for row in [*spans, *meters, *charges, *outcomes]]
    as_of = max(observed, default=run["observed_at"])
    outcome_rank = {"explicit_mark": 3, "test_exit": 2, "build_exit": 2, "git_fact": 1}
    outcome = (
        max(
            outcomes,
            key=lambda row: (
                row["outcome_status"] != "unknown",
                outcome_rank.get(row["evidence_type"], 0),
                row["observed_at"],
                row["evidence_id"],
            ),
        )
        if outcomes
        else None
    )
    graph = [
        {
            "span_id": row["span_id"],
            "parent_span_id": row["parent_span_id"],
            "operation_kind": row["operation_kind"],
            "lifecycle": row["lifecycle"],
            "branch_id": row["branch_id"],
            "attempt_of_span_id": row["attempt_of_span_id"],
            "checkpoint_id": row["checkpoint_id"],
        }
        for row in spans
    ]
    payload: dict[str, object] = {
        "schema_version": RECEIPT_SCHEMA_VERSION,
        "run_id": run_id,
        "conversation_id": run["conversation_id"],
        "trace_id": run["trace_id"],
        "as_of": as_of,
        "lifecycle": run["lifecycle"],
        "stop_reason": run["stop_reason"],
        "evidence": {
            "state": evidence_state,
            "sources_expected": expected_sources,
            "sources_present": sources,
            "freshness_as_of": as_of,
            "known_blind_spots": sorted(
                [
                    *missing_sources,
                    *(
                        ["provider_billing_absent"]
                        if not any(row["authority"] == Authority.BILLED.value for row in charges)
                        else []
                    ),
                    *(["missing_parent"] if missing_parent else []),
                    *(["missing_link_target"] if missing_link else []),
                    *(["causal_cycle"] if cycle_detected else []),
                ]
            ),
        },
        "causal_graph": graph,
        "timing_micros": {
            "critical_path": critical_path,
            "service": service_time,
            "wait": wait_time,
            "elapsed": (
                max(0, _duration_micros(min(row["occurred_at"] for row in spans), as_of))
                if spans
                else 0
            ),
        },
        "meter_facts": [
            {
                "fact_id": row["fact_id"],
                "span_id": row["span_id"],
                "meter_name": row["meter_name"],
                "unit": row["unit"],
                "quantity_micros": row["quantity_micros"],
                "aggregation": row["aggregation"],
                "finality": row["finality"],
            }
            for row in meters
        ],
        "economic_totals_micros": {
            currency: dict(values) for currency, values in sorted(totals.items())
        },
        "charges": [
            {
                "charge_id": row["charge_id"],
                "fact_id": row["fact_id"],
                "span_id": row["span_id"],
                "amount_micros": row["amount_micros"],
                "currency": row["currency"],
                "authority": row["authority"],
                "line_item": row["line_item"],
                "finality": row["finality"],
            }
            for row in selected_charges
        ],
        "outcome": (
            {
                "status": outcome["outcome_status"],
                "reason_code": outcome["reason_code"],
                "evidence_type": outcome["evidence_type"],
                "confidence": outcome["confidence"],
            }
            if outcome is not None
            else {"status": "unknown", "confidence": "unknown"}
        ),
        "outcome_evidence": [
            {
                "status": row["outcome_status"],
                "reason_code": row["reason_code"],
                "evidence_type": row["evidence_type"],
                "confidence": row["confidence"],
                "observed_at": row["observed_at"],
            }
            for row in outcomes
        ],
    }
    digest = hashlib.sha256(_canonical_json(payload).encode("utf-8")).hexdigest()
    payload["integrity"] = {"algorithm": "sha256", "payload_digest": digest}
    return payload


def save_receipt(conn: sqlite3.Connection, receipt: dict[str, object]) -> str:
    """Persist a receipt snapshot idempotently; it is an artifact, not a mutation of facts."""
    integrity = receipt["integrity"]
    if not isinstance(integrity, dict):  # pragma: no cover - build_receipt contract
        raise ValueError("receipt lacks integrity")
    receipt_id = f"receipt:{integrity['payload_digest']}"
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
            receipt["evidence"]["state"],  # type: ignore[index]
            _canonical_json(receipt),
        ),
    )
    conn.commit()
    return receipt_id


def receipt_text(receipt: dict[str, object], *, markdown: bool = False) -> str:
    """Render a compact stable receipt with no color or terminal assumptions."""
    evidence = receipt["evidence"]
    timing = receipt["timing_micros"]
    outcome = receipt["outcome"]
    totals = receipt["economic_totals_micros"]
    integrity = receipt["integrity"]
    if not all(isinstance(value, dict) for value in (evidence, timing, outcome, totals, integrity)):
        raise ValueError("invalid receipt shape")
    evidence = cast(dict[str, object], evidence)
    timing = cast(dict[str, object], timing)
    outcome = cast(dict[str, object], outcome)
    totals = cast(dict[str, object], totals)
    integrity = cast(dict[str, object], integrity)
    heading = "# Forecost run receipt" if markdown else "Forecost run receipt"
    lines = [heading, f"Run: {receipt['run_id']}", f"Evidence: {evidence['state']}"]
    lines.append(f"Lifecycle: {receipt['lifecycle']} | outcome: {outcome['status']}")
    lines.append(
        "Timing: critical path {critical}us | service {service}us | wait {wait}us".format(
            critical=timing["critical_path"], service=timing["service"], wait=timing["wait"]
        )
    )
    lines.append("Economic totals (micros):")
    for currency, by_authority in totals.items():
        if isinstance(by_authority, dict):
            lines.append(
                f"  {currency}: " + ", ".join(
                    f"{authority}={amount}" for authority, amount in sorted(by_authority.items())
                )
            )
    lines.append(f"Integrity: sha256:{integrity['payload_digest']}")
    return "\n".join(lines) + "\n"
