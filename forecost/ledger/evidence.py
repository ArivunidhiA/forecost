"""Append-only causal/economic journal and deterministic rebuildable projections."""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import datetime, timezone

from forecost.ledger.contracts import CausalIdentity, Observation, canonical_json, opaque_id
from forecost.ledger.integrity import advance_chain


@dataclass(frozen=True)
class AppendBatchResult:
    inserted: int
    duplicates: int
    batches: int


def _iso(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat()


def _begin_append(conn: sqlite3.Connection, nested: bool) -> None:
    if nested:
        conn.execute("SAVEPOINT forecost_append_observation")
    else:
        conn.execute("BEGIN IMMEDIATE")


def _finish_append(conn: sqlite3.Connection, nested: bool) -> None:
    if nested:
        conn.execute("RELEASE SAVEPOINT forecost_append_observation")
    else:
        conn.commit()


def _abort_append(conn: sqlite3.Connection, nested: bool) -> None:
    if nested:
        conn.execute("ROLLBACK TO SAVEPOINT forecost_append_observation")
        conn.execute("RELEASE SAVEPOINT forecost_append_observation")
    else:
        conn.rollback()


def _is_replay(
    conn: sqlite3.Connection,
    item: Observation,
    causal_json: str,
    payload_json: str,
) -> bool:
    existing = conn.execute(
        "SELECT observation_id, causal_json, payload_json, event_kind "
        "FROM journal_observations WHERE producer = ? AND idempotency_key = ?",
        (item.producer, item.causal.idempotency_key),
    ).fetchone()
    if existing is None:
        return False
    changed = (
        existing["causal_json"] != causal_json
        or existing["payload_json"] != payload_json
        or existing["event_kind"] != item.event_kind
    )
    if changed:
        raise ValueError("idempotency key already belongs to different evidence")
    return True


def _insert_observation(
    conn: sqlite3.Connection,
    item: Observation,
    causal_json: str,
    payload_json: str,
) -> sqlite3.Row:
    conn.execute(
        """
        INSERT INTO journal_observations(
            observation_id, schema_version, producer, source_sequence,
            idempotency_key, event_kind, occurred_at, observed_at,
            causal_json, payload_json, supersedes_observation_id
        ) VALUES (?,?,?,?,?,?,?,?,?,?,?)
        """,
        (
            item.observation_id,
            item.schema_version,
            item.producer,
            item.causal.source_sequence,
            item.causal.idempotency_key,
            item.event_kind,
            _iso(item.occurred_at),
            _iso(item.observed_at),
            causal_json,
            payload_json,
            item.supersedes_observation_id,
        ),
    )
    advance_chain(conn, item.observation_id)
    row: sqlite3.Row | None = conn.execute(
        "SELECT * FROM journal_observations WHERE observation_id=?", (item.observation_id,)
    ).fetchone()
    if row is None:  # pragma: no cover - insert/select invariant
        raise RuntimeError("observation insert did not yield a row")
    return row


def append_observation(conn: sqlite3.Connection, observation: Observation) -> bool:
    """Append exactly one observation, then rebuild projections deterministically.

    ``producer + idempotency_key`` is a durable replay boundary.  A duplicate
    with different evidence is rejected instead of silently overwriting the
    first fact.
    """
    item = observation.normalized()
    causal_json = canonical_json(item.causal.to_dict())
    payload_json = canonical_json(item.payload)
    nested = conn.in_transaction
    _begin_append(conn, nested)
    try:
        if _is_replay(conn, item, causal_json, payload_json):
            _finish_append(conn, nested)
            return False
        row = _insert_observation(conn, item, causal_json, payload_json)
        _project_row(conn, row)
        _finish_append(conn, nested)
    except BaseException:
        _abort_append(conn, nested)
        raise
    return True


def append_observations(
    conn: sqlite3.Connection,
    observations: Iterable[Observation],
    *,
    batch_size: int = 1_000,
) -> AppendBatchResult:
    """Append a stream in bounded transactions without materializing it.

    Each committed batch is a durable recovery boundary. A conflict rolls back
    its entire batch, while earlier batches remain committed and replay-safe.
    """
    if (
        isinstance(batch_size, bool)
        or not isinstance(batch_size, int)
        or not 1 <= batch_size <= 10_000
    ):
        raise ValueError("batch_size must be an integer between 1 and 10000")
    inserted = duplicates = batches = 0
    pending: list[Observation] = []

    def flush(items: list[Observation]) -> tuple[int, int]:
        conn.execute("BEGIN IMMEDIATE")
        added = replayed = 0
        try:
            for item in items:
                if append_observation(conn, item):
                    added += 1
                else:
                    replayed += 1
            conn.commit()
            return added, replayed
        except BaseException:
            conn.rollback()
            raise

    for item in observations:
        pending.append(item)
        if len(pending) >= batch_size:
            added, replayed = flush(pending)
            inserted += added
            duplicates += replayed
            batches += 1
            pending.clear()
    if pending:
        added, replayed = flush(pending)
        inserted += added
        duplicates += replayed
        batches += 1
    return AppendBatchResult(inserted, duplicates, batches)


def _causal(row: sqlite3.Row) -> dict[str, object]:
    value = json.loads(row["causal_json"])
    if not isinstance(value, dict):  # pragma: no cover - stored by canonical serializer
        raise ValueError("invalid causal envelope")
    return value


def _payload(row: sqlite3.Row) -> dict[str, object]:
    value = json.loads(row["payload_json"])
    if not isinstance(value, dict):  # pragma: no cover - stored by canonical serializer
        raise ValueError("invalid observation payload")
    return value


def rebuild_projections(conn: sqlite3.Connection) -> None:
    """Rebuild query tables from journal order, never arrival order or row ID."""
    conn.execute("DELETE FROM outcome_evidence")
    conn.execute("DELETE FROM charges")
    conn.execute("DELETE FROM meter_facts")
    conn.execute("DELETE FROM span_links")
    conn.execute("DELETE FROM causal_spans")
    conn.execute("DELETE FROM causal_runs")
    rows = conn.execute(
        """
        SELECT * FROM journal_observations
        ORDER BY producer ASC, source_sequence ASC, idempotency_key ASC
        """
    ).fetchall()
    for row in rows:
        _project_row(conn, row)


def _project_row(conn: sqlite3.Connection, row: sqlite3.Row) -> None:
    causal = _causal(row)
    payload = _payload(row)
    source_order = f"{row['producer']}:{row['source_sequence']:020d}:{row['idempotency_key']}"
    if row["event_kind"] == "span":
        _project_span(conn, row, causal, payload, source_order)
    elif row["event_kind"] == "meter":
        _project_meter(conn, row, causal, payload)
    elif row["event_kind"] == "charge":
        _project_charge(conn, row, causal, payload)
    elif row["event_kind"] == "outcome":
        _project_outcome(conn, row, causal, payload)
    else:  # pragma: no cover - append validates event kinds
        raise ValueError(f"unsupported event kind: {row['event_kind']}")


def _project_span(
    conn: sqlite3.Connection,
    row: sqlite3.Row,
    causal: dict[str, object],
    payload: Mapping[str, object],
    source_order: str,
) -> None:
    conn.execute(
        """
        INSERT INTO causal_runs(run_id, conversation_id, trace_id, lifecycle, created_at,
                                observed_at, stop_reason, source_coverage_json, source_order)
        VALUES (?,?,?,?,?,?,?,?,?)
        ON CONFLICT(run_id) DO UPDATE SET
            lifecycle=excluded.lifecycle, observed_at=excluded.observed_at,
            stop_reason=excluded.stop_reason, source_order=excluded.source_order,
            created_at=MIN(causal_runs.created_at, excluded.created_at)
        WHERE excluded.source_order > causal_runs.source_order
        """,
        (
            causal["run_id"],
            causal["conversation_id"],
            causal["trace_id"],
            payload["lifecycle"],
            row["occurred_at"],
            row["observed_at"],
            payload.get("stop_reason"),
            "{}",
            source_order,
        ),
    )
    conn.execute(
        """
        INSERT INTO causal_spans(
            span_id, run_id, conversation_id, trace_id, parent_span_id, operation_kind,
            lifecycle, agent_id, workflow_node_id, branch_id, attempt_of_span_id,
            checkpoint_id, occurred_at, observed_at, source_order
        ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        ON CONFLICT(span_id) DO UPDATE SET
            lifecycle=excluded.lifecycle, observed_at=excluded.observed_at,
            source_order=excluded.source_order
        WHERE excluded.source_order > causal_spans.source_order
        """,
        (
            causal["span_id"],
            causal["run_id"],
            causal["conversation_id"],
            causal["trace_id"],
            causal.get("parent_span_id"),
            payload["operation_kind"],
            payload["lifecycle"],
            payload.get("agent_id"),
            payload.get("workflow_node_id"),
            payload.get("branch_id"),
            payload.get("attempt_of_span_id"),
            payload.get("checkpoint_id"),
            row["occurred_at"],
            row["observed_at"],
            source_order,
        ),
    )
    links = causal.get("links", [])
    if not isinstance(links, list):  # pragma: no cover - causal contract validation
        raise ValueError("causal links must be a list")
    for linked_span_id in links:
        if not isinstance(linked_span_id, str):  # pragma: no cover - causal contract validation
            raise ValueError("causal link must be an identifier")
        conn.execute(
            "INSERT INTO span_links(span_id, linked_span_id, link_type, observation_id) "
            "VALUES (?,?,?,?)",
            (causal["span_id"], linked_span_id, "fan_in", row["observation_id"]),
        )


def _project_meter(
    conn: sqlite3.Connection,
    row: sqlite3.Row,
    causal: dict[str, object],
    payload: dict[str, object],
) -> None:
    conn.execute(
        """
        INSERT INTO meter_facts(
            fact_id, span_id, meter_name, unit, quantity_micros, aggregation,
            dimensions_json, source, finality, occurred_at, observed_at, observation_id
        ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)
        """,
        (
            opaque_id("fact", row["observation_id"]),
            causal["span_id"],
            payload["meter_name"],
            payload["unit"],
            payload["quantity_micros"],
            payload["aggregation"],
            canonical_json(payload.get("dimensions", {})),
            row["producer"],
            payload["finality"],
            row["occurred_at"],
            row["observed_at"],
            row["observation_id"],
        ),
    )


def _project_charge(
    conn: sqlite3.Connection,
    row: sqlite3.Row,
    causal: dict[str, object],
    payload: dict[str, object],
) -> None:
    conn.execute(
        """
        INSERT INTO charges(
            charge_id, fact_id, span_id, amount_micros, currency, authority, line_item,
            tariff_json, account_scope, billing_period, finality, occurred_at, observed_at,
            supersedes_charge_id, observation_id
        ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        """,
        (
            opaque_id("charge", row["observation_id"]),
            payload.get("fact_id"),
            causal["span_id"],
            payload["amount_micros"],
            payload["currency"],
            payload["authority"],
            payload["line_item"],
            canonical_json(payload.get("tariff", {})),
            payload.get("account_scope"),
            payload.get("billing_period"),
            payload["finality"],
            row["occurred_at"],
            row["observed_at"],
            payload.get("supersedes_charge_id"),
            row["observation_id"],
        ),
    )


def _project_outcome(
    conn: sqlite3.Connection,
    row: sqlite3.Row,
    causal: dict[str, object],
    payload: dict[str, object],
) -> None:
    conn.execute(
        """
        INSERT INTO outcome_evidence(
            evidence_id, run_id, outcome_status, reason_code, evidence_type, source,
            confidence, observed_at, supersedes_evidence_id, observation_id
        ) VALUES (?,?,?,?,?,?,?,?,?,?)
        """,
        (
            opaque_id("outcome", row["observation_id"]),
            causal["run_id"],
            payload["outcome_status"],
            payload.get("reason_code"),
            payload["evidence_type"],
            row["producer"],
            payload["confidence"],
            row["observed_at"],
            payload.get("supersedes_evidence_id"),
            row["observation_id"],
        ),
    )


def observation(
    *,
    producer: str,
    event_kind: str,
    causal: CausalIdentity,
    payload: Mapping[str, object],
    occurred_at: datetime | None = None,
    observed_at: datetime | None = None,
) -> Observation:
    """Small ergonomic factory used by adapters and the offline conformance lab."""
    now = datetime.now(timezone.utc)
    return Observation(
        producer=producer,
        event_kind=event_kind,
        causal=causal,
        payload=dict(payload),
        occurred_at=occurred_at or now,
        observed_at=observed_at or now,
    )
