"""Content-free mappings for OpenAI Agents and LangGraph runtime records.

This module intentionally has no dependency on either SDK.  Integrators select
safe typed fields at the callback boundary and pass only this structural shape.
Full span/callback objects are never serialized and then redacted.
"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime

from forecost.adapters.causal import runtime_meter_observation, runtime_span_observation
from forecost.ledger.contracts import Observation

_OPENAI_OPERATIONS = {
    "agent": "agent",
    "generation": "model",
    "tool": "tool",
    "guardrail": "guardrail",
    "handoff": "handoff",
    "response": "model",
}
_LANGGRAPH_OPERATIONS = {
    "graph": "agent",
    "node": "agent",
    "tool": "tool",
    "checkpoint": "checkpoint",
    "interrupt": "human_approval",
}


def _integer(record: Mapping[str, object], key: str) -> int:
    value = record.get(key, 0)
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"{key} must be a non-negative integer")
    return value


def _mapped_span(
    record: Mapping[str, object], *, producer: str, operations: Mapping[str, str]
) -> Observation:
    span_type = record.get("span_type")
    operation = operations.get(span_type, "custom") if isinstance(span_type, str) else "custom"
    selected = {
        key: record.get(key)
        for key in (
            "conversation_id",
            "trace_id",
            "run_id",
            "span_id",
            "parent_span_id",
            "links",
            "source_sequence",
            "idempotency_key",
            "lifecycle",
            "agent_id",
            "workflow_node_id",
            "branch_id",
            "attempt_of_span_id",
            "checkpoint_id",
            "occurred_at",
            "observed_at",
        )
        if record.get(key) is not None
    }
    selected["operation_kind"] = operation
    return runtime_span_observation(selected, producer=producer)


def _usage_observations(
    record: Mapping[str, object], span: Observation, *, producer: str
) -> list[Observation]:
    occurred_at = span.occurred_at
    meters: list[Observation] = []
    for offset, (field, meter_name) in enumerate(
        (("input_tokens", "tokens.input"), ("output_tokens", "tokens.output")), start=1
    ):
        quantity = _integer(record, field)
        if not quantity:
            continue
        meters.append(
            runtime_meter_observation(
                span.causal,
                producer=producer,
                idempotency_key=f"{span.causal.idempotency_key}:{field}",
                source_sequence=span.causal.source_sequence + offset,
                meter_name=meter_name,
                quantity_micros=quantity * 1_000_000,
                occurred_at=occurred_at,
                finality="final" if record.get("usage_scope") == "generation" else "provisional",
            )
        )
    return meters


def openai_agents_observations(record: Mapping[str, object]) -> list[Observation]:
    """Map one selected Agents trace record and optional generation usage."""
    span = _mapped_span(record, producer="openai_agents", operations=_OPENAI_OPERATIONS)
    return [span, *_usage_observations(record, span, producer="openai_agents")]


def langgraph_observations(record: Mapping[str, object]) -> list[Observation]:
    """Map a node/checkpoint/interrupt/replay callback from a local graph."""
    span = _mapped_span(record, producer="langgraph", operations=_LANGGRAPH_OPERATIONS)
    return [span, *_usage_observations(record, span, producer="langgraph")]


def iso_timestamp(value: str) -> datetime:
    """Public fixture helper used by adapter integrations."""
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("timestamp must include a timezone")
    return parsed
