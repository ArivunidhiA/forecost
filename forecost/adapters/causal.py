"""Content-free adapter conformance helpers for runtime and OTel-style events."""

from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime, timezone

from forecost.ledger.contracts import CausalIdentity, Observation
from forecost.ledger.evidence import observation


def _timestamp(value: object) -> datetime:
    if not isinstance(value, str):
        raise ValueError("runtime event timestamp must be ISO-8601 text")
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("runtime event timestamp must include a timezone")
    return parsed.astimezone(timezone.utc)


def runtime_span_observation(event: Mapping[str, object], *, producer: str) -> Observation:
    """Map a generic OpenAI Agents/OTel-style span to the Forecost contract.

    The mapper intentionally accepts only structural fields.  Attributes,
    messages, inputs, outputs, baggage, and tracestate are neither inspected
    nor retained.
    """
    def required(name: str) -> str:
        value = event.get(name)
        if not isinstance(value, str) or not value:
            raise ValueError(f"runtime event needs {name}")
        return value

    parent_span_id = event.get("parent_span_id")
    links_value = event.get("links", ())
    links = (
        tuple(value for value in links_value if isinstance(value, str))
        if isinstance(links_value, (list, tuple))
        else ()
    )
    source_sequence = event.get("source_sequence", 0)
    if isinstance(source_sequence, bool) or not isinstance(source_sequence, int):
        raise ValueError("source_sequence must be a non-negative integer")
    causal = CausalIdentity(
        conversation_id=required("conversation_id"),
        trace_id=required("trace_id"),
        run_id=required("run_id"),
        span_id=required("span_id"),
        parent_span_id=parent_span_id if isinstance(parent_span_id, str) else None,
        links=links,
        source_sequence=source_sequence,
        idempotency_key=required("idempotency_key"),
    )
    return observation(
        producer=producer,
        event_kind="span",
        causal=causal,
        payload={
            "operation_kind": event.get("operation_kind", "custom"),
            "lifecycle": event.get("lifecycle", "running"),
            "agent_id": event.get("agent_id"),
            "workflow_node_id": event.get("workflow_node_id"),
            "branch_id": event.get("branch_id"),
            "attempt_of_span_id": event.get("attempt_of_span_id"),
            "checkpoint_id": event.get("checkpoint_id"),
        },
        occurred_at=_timestamp(event.get("occurred_at")),
        observed_at=_timestamp(event.get("observed_at", event.get("occurred_at"))),
    )


def runtime_meter_observation(
    span: CausalIdentity,
    *,
    producer: str,
    idempotency_key: str,
    source_sequence: int,
    meter_name: str,
    quantity_micros: int,
    occurred_at: datetime,
    finality: str = "provisional",
) -> Observation:
    """Map one runtime meter fact; callers choose delta/subset/checkpoint/gauge."""
    return observation(
        producer=producer,
        event_kind="meter",
        causal=CausalIdentity(
            conversation_id=span.conversation_id,
            trace_id=span.trace_id,
            run_id=span.run_id,
            span_id=span.span_id,
            parent_span_id=span.parent_span_id,
            source_sequence=source_sequence,
            idempotency_key=idempotency_key,
        ),
        payload={
            "meter_name": meter_name,
            "unit": "token",
            "quantity_micros": quantity_micros,
            "aggregation": "delta",
            "dimensions": {},
            "finality": finality,
        },
        occurred_at=occurred_at,
        observed_at=occurred_at,
    )
