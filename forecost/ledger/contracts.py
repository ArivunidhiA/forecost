"""Versioned, content-free contracts for Forecost causal/economic evidence."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from typing import Any

CAUSAL_SCHEMA_VERSION = 1
RECEIPT_SCHEMA_VERSION = 1

_SAFE_ATOM = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/@+\-]*$")
_TRACE_ID = re.compile(r"^(?!0{32})[0-9a-f]{32}$")
_SPAN_ID = re.compile(r"^(?!0{16})[0-9a-f]{16}$")
_OPAQUE = re.compile(r"^[a-z][a-z0-9_-]*:[0-9a-f]{64}$")
_MAX_INT = 1_000_000_000_000_000


class Lifecycle(str, Enum):
    CREATED = "created"
    QUEUED = "queued"
    RUNNING = "running"
    WAITING = "waiting"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    INCOMPLETE = "incomplete"
    REPLAYED = "replayed"
    SUPERSEDED = "superseded"


class OperationKind(str, Enum):
    AGENT = "agent"
    MODEL = "model"
    TOOL = "tool"
    HANDOFF = "handoff"
    GUARDRAIL = "guardrail"
    CHECKPOINT = "checkpoint"
    HUMAN_APPROVAL = "human_approval"
    QUEUE_WAIT = "queue_wait"
    CUSTOM = "custom"


class Aggregation(str, Enum):
    DELTA = "delta"
    SUBSET = "subset"
    CHECKPOINT = "checkpoint"
    GAUGE = "gauge"


class Authority(str, Enum):
    BILLED = "billed"
    PROVIDER_ESTIMATE = "provider_estimate"
    GATEWAY_ESTIMATE = "gateway_estimate"
    LIST_RATE = "list_rate"
    CONTRACT_ALLOCATION = "contract_allocation"
    SUBSCRIPTION_QUOTA = "subscription_quota"
    UNKNOWN = "unknown"


class Finality(str, Enum):
    PROVISIONAL = "provisional"
    FINAL = "final"
    UNKNOWN = "unknown"


class OutcomeStatus(str, Enum):
    GOOD = "good"
    BAD = "bad"
    PARTIAL = "partial"
    UNKNOWN = "unknown"


class EvidenceState(str, Enum):
    COMPLETE = "complete"
    INCOMPLETE = "incomplete"
    CONFLICTED = "conflicted"
    UNKNOWN = "unknown"


_OUTCOME_EVIDENCE_TYPES = frozenset({"explicit_mark", "test_exit", "build_exit", "git_fact"})
_OUTCOME_CONFIDENCE = frozenset({"explicit", "observed", "inferred", "unknown"})
_REVIEWED_DIMENSION_KEYS = frozenset({"model_class", "cache_class", "service_tier", "batch"})
_REVIEWED_METERS = frozenset(
    {"tokens.input", "tokens.output", "tokens.cache_read", "tokens.cache_write"}
)
_REVIEWED_UNITS = frozenset({"token", "usd_micros", "call", "step", "retry", "millisecond"})
_REVIEWED_CURRENCIES = frozenset({"USD"})
_REVIEWED_LINE_ITEMS = frozenset({"model_inference", "tool_call", "subscription_quota"})


def opaque_id(namespace: str, value: str) -> str:
    """Create a stable, irreversible identifier safe to retain at rest."""
    if _OPAQUE.fullmatch(value) and value.startswith(f"{namespace}:"):
        return value
    digest = hashlib.sha256(value.encode("utf-8", errors="replace")).hexdigest()
    return f"{namespace}:{digest}"


def _normalized_atom(namespace: str, value: str | None, *, maximum: int = 512) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str) or not value or len(value) > maximum:
        raise ValueError(f"{namespace} must be a bounded identifier")
    return opaque_id(namespace, value)


def normalize_trace_id(value: str) -> str:
    value = value.lower()
    return value if _TRACE_ID.fullmatch(value) else opaque_id("trace", value)


def normalize_span_id(value: str) -> str:
    value = value.lower()
    return value if _SPAN_ID.fullmatch(value) else opaque_id("span", value)


def canonical_json(value: Any) -> str:
    """Serialize JSON deterministically and reject floats/content-shaped values."""

    def validate(item: Any) -> None:
        if item is None or isinstance(item, bool):
            return
        if isinstance(item, int):
            if abs(item) > _MAX_INT:
                raise ValueError("integer payload value is out of bounds")
            return
        if isinstance(item, str):
            if len(item) > 256 or _SAFE_ATOM.fullmatch(item) is None:
                raise ValueError("payload strings must be bounded content-free atoms")
            return
        if isinstance(item, list):
            for child in item:
                validate(child)
            return
        if isinstance(item, dict):
            for key, child in item.items():
                if not isinstance(key, str) or _SAFE_ATOM.fullmatch(key) is None:
                    raise ValueError("payload keys must be safe atoms")
                validate(child)
            return
        raise ValueError("payload values must be JSON primitives without floats")

    validate(value)
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("timestamps must be timezone-aware")
    return value.astimezone(timezone.utc)


def _enum_value(name: str, value: object, values: type[Enum] | frozenset[str]) -> str:
    allowed = {member.value for member in values} if isinstance(values, type) else values
    if not isinstance(value, str) or value not in allowed:
        raise ValueError(f"{name} is not an approved enum value")
    return value


def _opaque_payload_id(namespace: str, value: object, *, optional: bool = False) -> str | None:
    if value is None and optional:
        return None
    if not isinstance(value, str) or not value:
        raise ValueError(f"{namespace} must be a non-empty identifier")
    return opaque_id(namespace, value)


def _reviewed_or_opaque(namespace: str, value: object, approved: frozenset[str]) -> str:
    if not isinstance(value, str) or not value:
        raise ValueError(f"{namespace} must be a non-empty identifier")
    return value if value in approved else opaque_id(namespace, value)


def _normalise_dimensions(value: object) -> dict[str, object]:
    if value is None:
        return {}
    if not isinstance(value, dict):
        raise ValueError("meter dimensions must be an object")
    normalized: dict[str, object] = {}
    for key, item in value.items():
        if key not in _REVIEWED_DIMENSION_KEYS:
            raise ValueError("meter dimension is not approved")
        if isinstance(item, (bool, int)):
            normalized[key] = item
        elif isinstance(item, str):
            normalized[key] = opaque_id(f"dimension-{key}", item)
        else:
            raise ValueError("meter dimension value must be a scalar")
    return normalized


def _normalise_tariff(value: object) -> dict[str, object]:
    if value is None:
        return {}
    if not isinstance(value, dict):
        raise ValueError("tariff must be an object")
    normalized: dict[str, object] = {}
    for key, item in value.items():
        if key not in {"rate_snapshot", "input_rate_micros", "output_rate_micros", "discount"}:
            raise ValueError("tariff component is not approved")
        if isinstance(item, (bool, int)):
            normalized[key] = item
        elif isinstance(item, str):
            normalized[key] = opaque_id(f"tariff-{key}", item)
        else:
            raise ValueError("tariff component must be a scalar")
    return normalized


def _normalise_span_payload(payload: dict[str, object]) -> dict[str, object]:
    return {
        "operation_kind": _enum_value(
            "operation_kind", payload.get("operation_kind"), OperationKind
        ),
        "lifecycle": _enum_value("lifecycle", payload.get("lifecycle"), Lifecycle),
        "agent_id": _opaque_payload_id("agent", payload.get("agent_id"), optional=True),
        "workflow_node_id": _opaque_payload_id(
            "workflow-node", payload.get("workflow_node_id"), optional=True
        ),
        "branch_id": _opaque_payload_id("branch", payload.get("branch_id"), optional=True),
        "attempt_of_span_id": (
            normalize_span_id(str(payload["attempt_of_span_id"]))
            if payload.get("attempt_of_span_id") is not None
            else None
        ),
        "checkpoint_id": _opaque_payload_id(
            "checkpoint", payload.get("checkpoint_id"), optional=True
        ),
        "stop_reason": _opaque_payload_id("stop-reason", payload.get("stop_reason"), optional=True),
    }


def _nonnegative_integer(payload: dict[str, object], key: str) -> int:
    value = payload.get(key)
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"{key} must be a non-negative integer")
    return value


def _normalise_meter_payload(payload: dict[str, object]) -> dict[str, object]:
    return {
        "meter_name": _reviewed_or_opaque("meter", payload.get("meter_name"), _REVIEWED_METERS),
        "unit": _reviewed_or_opaque("unit", payload.get("unit"), _REVIEWED_UNITS),
        "quantity_micros": _nonnegative_integer(payload, "quantity_micros"),
        "aggregation": _enum_value("aggregation", payload.get("aggregation"), Aggregation),
        "dimensions": _normalise_dimensions(payload.get("dimensions")),
        "finality": _enum_value("finality", payload.get("finality"), Finality),
    }


def _normalise_charge_payload(payload: dict[str, object]) -> dict[str, object]:
    return {
        "fact_id": _opaque_payload_id("fact", payload.get("fact_id"), optional=True),
        "amount_micros": _nonnegative_integer(payload, "amount_micros"),
        "currency": _reviewed_or_opaque("currency", payload.get("currency"), _REVIEWED_CURRENCIES),
        "authority": _enum_value("authority", payload.get("authority"), Authority),
        "line_item": _reviewed_or_opaque(
            "line-item", payload.get("line_item"), _REVIEWED_LINE_ITEMS
        ),
        "tariff": _normalise_tariff(payload.get("tariff")),
        "account_scope": _opaque_payload_id(
            "account-scope", payload.get("account_scope"), optional=True
        ),
        "billing_period": _opaque_payload_id(
            "billing-period", payload.get("billing_period"), optional=True
        ),
        "finality": _enum_value("finality", payload.get("finality"), Finality),
        "supersedes_charge_id": _opaque_payload_id(
            "charge", payload.get("supersedes_charge_id"), optional=True
        ),
    }


def _normalise_outcome_payload(payload: dict[str, object]) -> dict[str, object]:
    return {
        "outcome_status": _enum_value(
            "outcome_status", payload.get("outcome_status"), OutcomeStatus
        ),
        "reason_code": _opaque_payload_id("reason", payload.get("reason_code"), optional=True),
        "evidence_type": _enum_value(
            "evidence_type", payload.get("evidence_type"), _OUTCOME_EVIDENCE_TYPES
        ),
        "confidence": _enum_value("confidence", payload.get("confidence"), _OUTCOME_CONFIDENCE),
        "supersedes_evidence_id": _opaque_payload_id(
            "outcome", payload.get("supersedes_evidence_id"), optional=True
        ),
    }


_PAYLOAD_NORMALIZERS = {
    "span": _normalise_span_payload,
    "meter": _normalise_meter_payload,
    "charge": _normalise_charge_payload,
    "outcome": _normalise_outcome_payload,
}


def normalise_payload(event_kind: str, payload: dict[str, object]) -> dict[str, object]:
    """Validate every event kind and erase open-ended payload identifiers."""
    normalizer = _PAYLOAD_NORMALIZERS.get(event_kind)
    if normalizer is None:
        raise ValueError("observation event_kind is not supported")
    return normalizer(payload)


@dataclass(frozen=True)
class CausalIdentity:
    """The smallest identity envelope that can reconstruct agent execution."""

    conversation_id: str
    trace_id: str
    run_id: str
    span_id: str
    parent_span_id: str | None = None
    links: tuple[str, ...] = ()
    source_sequence: int = 0
    idempotency_key: str = "event"

    def normalized(self) -> CausalIdentity:
        if self.source_sequence < 0:
            raise ValueError("source_sequence must be non-negative")
        links = tuple(sorted(normalize_span_id(link) for link in self.links))
        return CausalIdentity(
            conversation_id=opaque_id("conversation", self.conversation_id),
            trace_id=normalize_trace_id(self.trace_id),
            run_id=opaque_id("run", self.run_id),
            span_id=normalize_span_id(self.span_id),
            parent_span_id=(
                normalize_span_id(self.parent_span_id) if self.parent_span_id is not None else None
            ),
            links=links,
            source_sequence=self.source_sequence,
            idempotency_key=opaque_id("idempotency", self.idempotency_key),
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "conversation_id": self.conversation_id,
            "trace_id": self.trace_id,
            "run_id": self.run_id,
            "span_id": self.span_id,
            "parent_span_id": self.parent_span_id,
            "links": list(self.links),
            "source_sequence": self.source_sequence,
            "idempotency_key": self.idempotency_key,
        }


@dataclass(frozen=True)
class Observation:
    """One append-only, replayable content-free observation."""

    producer: str
    event_kind: str
    causal: CausalIdentity
    occurred_at: datetime
    observed_at: datetime
    payload: dict[str, object]
    supersedes_observation_id: str | None = None
    schema_version: int = CAUSAL_SCHEMA_VERSION

    def normalized(self) -> Observation:
        if self.schema_version != CAUSAL_SCHEMA_VERSION:
            raise ValueError(f"unsupported observation schema version: {self.schema_version}")
        if self.event_kind not in {"span", "meter", "charge", "outcome"}:
            raise ValueError("observation event_kind is not supported")
        if not isinstance(self.producer, str) or not self.producer:
            raise ValueError("producer must be a non-empty identifier")
        causal = self.causal.normalized()
        occurred_at = _as_utc(self.occurred_at)
        observed_at = _as_utc(self.observed_at)
        normalized_payload = normalise_payload(self.event_kind, self.payload)
        payload_json = canonical_json(normalized_payload)
        return Observation(
            producer=opaque_id("producer", self.producer),
            event_kind=self.event_kind,
            causal=causal,
            occurred_at=occurred_at,
            observed_at=observed_at,
            payload=json.loads(payload_json),
            supersedes_observation_id=(
                opaque_id("observation", self.supersedes_observation_id)
                if self.supersedes_observation_id is not None
                else None
            ),
            schema_version=self.schema_version,
        )

    @property
    def observation_id(self) -> str:
        normal = self.normalized()
        return opaque_id(
            "observation",
            "|".join(
                (
                    normal.producer,
                    normal.causal.idempotency_key,
                    normal.event_kind,
                    normal.occurred_at.isoformat(),
                    canonical_json(normal.payload),
                )
            ),
        )
