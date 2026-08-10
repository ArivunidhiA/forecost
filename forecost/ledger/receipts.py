"""Deterministic, content-free run receipts built from causal projections."""

from __future__ import annotations

import hashlib
import json
import sqlite3
from collections import defaultdict
from dataclasses import dataclass
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
        (
            datetime.fromisoformat(end).astimezone(timezone.utc)
            - datetime.fromisoformat(start).astimezone(timezone.utc)
        ).total_seconds()
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


def _span_interval(row: dict[str, Any]) -> tuple[datetime, datetime]:
    return (
        datetime.fromisoformat(row["occurred_at"]).astimezone(timezone.utc),
        datetime.fromisoformat(row["observed_at"]).astimezone(timezone.utc),
    )


@dataclass
class _CriticalPathGraph:
    by_id: dict[str, dict[str, Any]]
    children: dict[str, list[str]]
    predecessors: dict[str, set[str]]
    memo: dict[str, int]
    cycle_detected: bool = False

    def exclusive_duration(self, span_id: str) -> int:
        start, end = _span_interval(self.by_id[span_id])
        own = max(0, int((end - start).total_seconds() * 1_000_000))
        covered = self._covered_child_intervals(span_id, start, end)
        return max(0, own - _interval_union_micros(covered))

    def _covered_child_intervals(
        self, span_id: str, start: datetime, end: datetime
    ) -> list[tuple[datetime, datetime]]:
        covered: list[tuple[datetime, datetime]] = []
        for child_id in self.children[span_id]:
            child_start, child_end = _span_interval(self.by_id[child_id])
            clipped = (max(start, child_start), min(end, child_end))
            if clipped[1] > clipped[0]:
                covered.append(clipped)
        return covered

    def path_duration(self, span_id: str, active: set[str]) -> int:
        if span_id in self.memo:
            return self.memo[span_id]
        if span_id in active:
            self.cycle_detected = True
            return 0
        previous = [
            self.path_duration(parent, active | {span_id})
            for parent in sorted(self.predecessors[span_id])
        ]
        result = self.exclusive_duration(span_id) + max(previous, default=0)
        self.memo[span_id] = result
        return result


def _critical_path_graph(
    spans: list[dict[str, Any]], links: list[tuple[str, str]]
) -> _CriticalPathGraph:
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
    return _CriticalPathGraph(by_id, children, predecessors, {})


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
    graph = _critical_path_graph(spans, links)
    durations = [graph.path_duration(row["span_id"], set()) for row in spans]
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
    return max(durations, default=0), service, wait, graph.cycle_detected


@dataclass(frozen=True)
class _ReceiptRows:
    run: sqlite3.Row
    spans: list[dict[str, Any]]
    meters: list[dict[str, Any]]
    charges: list[dict[str, Any]]
    outcomes: list[dict[str, Any]]
    sources: list[str]
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
        "SELECT m.* FROM meter_facts m JOIN causal_spans s ON s.span_id = m.span_id "
        "WHERE s.run_id = ? ORDER BY m.occurred_at, m.fact_id",
        run_id,
    )
    charges = _query_dicts(
        conn,
        "SELECT c.* FROM charges c JOIN causal_spans s ON s.span_id = c.span_id "
        "WHERE s.run_id = ? ORDER BY c.occurred_at, c.charge_id",
        run_id,
    )
    outcomes = _query_dicts(
        conn,
        "SELECT * FROM outcome_evidence WHERE run_id = ? ORDER BY observed_at, evidence_id",
        run_id,
    )
    return _ReceiptRows(
        run=run,
        spans=spans,
        meters=meters,
        charges=charges,
        outcomes=outcomes,
        sources=_load_sources(conn, run_id),
        links=_load_links(conn, run_id),
    )


def _load_sources(conn: sqlite3.Connection, run_id: str) -> list[str]:
    rows = conn.execute(
        "SELECT DISTINCT j.producer FROM journal_observations j "
        "JOIN causal_spans s ON s.span_id = json_extract(j.causal_json, '$.span_id') "
        "WHERE s.run_id = ? ORDER BY j.producer",
        (run_id,),
    ).fetchall()
    return [str(row[0]) for row in rows]


def _load_links(conn: sqlite3.Connection, run_id: str) -> list[tuple[str, str]]:
    rows = conn.execute(
        "SELECT l.span_id, l.linked_span_id FROM span_links l "
        "JOIN causal_spans s ON s.span_id = l.span_id "
        "WHERE s.run_id = ? ORDER BY l.span_id, l.linked_span_id",
        (run_id,),
    ).fetchall()
    return [(row["span_id"], row["linked_span_id"]) for row in rows]


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


def _known_blind_spots(
    rows: _ReceiptRows,
    missing_sources: list[str],
    cycle_detected: bool,
) -> list[str]:
    span_ids = {row["span_id"] for row in rows.spans}
    blind_spots = list(missing_sources)
    if not any(row["authority"] == Authority.BILLED.value for row in rows.charges):
        blind_spots.append("provider_billing_absent")
    if any(row["parent_span_id"] not in (None, *span_ids) for row in rows.spans):
        blind_spots.append("missing_parent")
    if any(linked_span_id not in span_ids for _, linked_span_id in rows.links):
        blind_spots.append("missing_link_target")
    if cycle_detected:
        blind_spots.append("causal_cycle")
    return sorted(blind_spots)


def _meter_payload(meters: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
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
    ]


def _charge_payload(charges: list[dict[str, Any]]) -> list[dict[str, Any]]:
    keys = (
        "charge_id",
        "fact_id",
        "span_id",
        "amount_micros",
        "currency",
        "authority",
        "line_item",
        "finality",
    )
    return [{key: row[key] for key in keys} for row in charges]


def _outcome_payload(outcome: dict[str, Any] | None) -> dict[str, Any]:
    if outcome is None:
        return {"status": "unknown", "confidence": "unknown"}
    return {
        "status": outcome["outcome_status"],
        "reason_code": outcome["reason_code"],
        "evidence_type": outcome["evidence_type"],
        "confidence": outcome["confidence"],
    }


def _outcome_evidence_payload(outcomes: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "status": row["outcome_status"],
            "reason_code": row["reason_code"],
            "evidence_type": row["evidence_type"],
            "confidence": row["confidence"],
            "observed_at": row["observed_at"],
        }
        for row in outcomes
    ]


def _receipt_payload(rows: _ReceiptRows, run_id: str) -> dict[str, object]:
    selected_charges, conflicted = _canonical_charges(rows.charges)
    expected_sources = _expected_sources(rows.run)
    missing_sources = sorted(set(expected_sources) - set(rows.sources))
    critical_path, service_time, wait_time, cycle_detected = _critical_path(rows.spans, rows.links)
    observed = [
        row["observed_at"] for row in [*rows.spans, *rows.meters, *rows.charges, *rows.outcomes]
    ]
    as_of = max(observed, default=rows.run["observed_at"])
    payload: dict[str, object] = {
        "schema_version": RECEIPT_SCHEMA_VERSION,
        "run_id": run_id,
        "conversation_id": rows.run["conversation_id"],
        "trace_id": rows.run["trace_id"],
        "as_of": as_of,
        "lifecycle": rows.run["lifecycle"],
        "stop_reason": rows.run["stop_reason"],
        "evidence": {
            "state": _evidence_state(
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
        },
        "causal_graph": _causal_graph(rows.spans),
        "timing_micros": {
            "critical_path": critical_path,
            "service": service_time,
            "wait": wait_time,
            "elapsed": (
                max(0, _duration_micros(min(row["occurred_at"] for row in rows.spans), as_of))
                if rows.spans
                else 0
            ),
        },
        "meter_facts": _meter_payload(rows.meters),
        "economic_totals_micros": _economic_totals(selected_charges),
        "charges": _charge_payload(selected_charges),
        "outcome": _outcome_payload(_select_outcome(rows.outcomes)),
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
                f"  {currency}: "
                + ", ".join(
                    f"{authority}={amount}" for authority, amount in sorted(by_authority.items())
                )
            )
    lines.append(f"Integrity: sha256:{integrity['payload_digest']}")
    return "\n".join(lines) + "\n"
