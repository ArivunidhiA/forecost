"""Offline OTel/GenAI JSON/JSONL mapping with no collector or network."""

from __future__ import annotations

import json
from collections.abc import Iterable, Mapping
from datetime import datetime
from typing import TextIO

from forecost.adapters.causal import runtime_meter_observation, runtime_span_observation
from forecost.ledger.contracts import CausalIdentity, Observation


def _jsonl_records(raw: str) -> list[Mapping[str, object]]:
    decoded: list[Mapping[str, object]] = []
    for line_number, line in enumerate(raw.splitlines(), start=1):
        if not line.strip():
            continue
        try:
            item = json.loads(line)
        except json.JSONDecodeError as error:
            raise ValueError(f"invalid JSONL at line {line_number}") from error
        if not isinstance(item, Mapping):
            raise ValueError(f"JSONL line {line_number} is not an object") from None
        decoded.append(item)
    return decoded


def _record_list(decoded: object) -> list[Mapping[str, object]]:
    if isinstance(decoded, Mapping):
        decoded = [decoded]
    if not isinstance(decoded, list) or not all(isinstance(item, Mapping) for item in decoded):
        raise ValueError("OTel input must be an object, array of objects, or JSONL objects")
    return decoded


def load_records(stream: TextIO) -> list[Mapping[str, object]]:
    """Read either one JSON array or newline-delimited JSON objects."""
    raw = stream.read()
    if not raw.strip():
        return []
    try:
        decoded = json.loads(raw)
    except json.JSONDecodeError:
        return _jsonl_records(raw)
    return _record_list(decoded)


def _required(record: Mapping[str, object], name: str) -> str:
    value = record.get(name)
    if not isinstance(value, str) or not value:
        raise ValueError(f"OTel record needs {name}")
    return value


def _timestamp(value: object) -> datetime:
    if not isinstance(value, str):
        raise ValueError("OTel metric needs occurred_at")
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("OTel metric timestamp must include a timezone")
    return parsed


def _sequence(record: Mapping[str, object]) -> int:
    value = record.get("source_sequence", 0)
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError("OTel source_sequence must be non-negative")
    return value


def _finality(record: Mapping[str, object]) -> str:
    value = record.get("finality")
    return value if isinstance(value, str) else "provisional"


def _causal(record: Mapping[str, object]) -> CausalIdentity:
    parent_value = record.get("parent_span_id")
    return CausalIdentity(
        conversation_id=_required(record, "conversation_id"),
        trace_id=_required(record, "trace_id"),
        run_id=_required(record, "run_id"),
        span_id=_required(record, "span_id"),
        parent_span_id=parent_value if isinstance(parent_value, str) else None,
        source_sequence=_sequence(record),
        idempotency_key=_required(record, "idempotency_key"),
    )


def otel_observations(
    records: Iterable[Mapping[str, object]], *, producer: str = "otel"
) -> list[Observation]:
    """Select only causal, lifecycle and meter fields from OTel exports."""
    result: list[Observation] = []
    for record in records:
        kind = record.get("kind", "span")
        if kind == "span":
            result.append(runtime_span_observation(record, producer=producer))
            continue
        if kind != "metric":
            raise ValueError("OTel kind must be span or metric")
        quantity = record.get("quantity_micros")
        if isinstance(quantity, bool) or not isinstance(quantity, int) or quantity < 0:
            raise ValueError("OTel metric quantity_micros must be non-negative")
        result.append(
            runtime_meter_observation(
                _causal(record),
                producer=producer,
                idempotency_key=_required(record, "idempotency_key"),
                source_sequence=_sequence(record),
                meter_name=_required(record, "meter_name"),
                quantity_micros=quantity,
                occurred_at=_timestamp(record.get("occurred_at")),
                finality=_finality(record),
            )
        )
    return result
