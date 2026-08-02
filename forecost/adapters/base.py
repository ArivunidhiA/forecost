"""Ingestion adapter contracts: UsageEvent, PostingSpec, and the adapter ABCs.

An adapter turns whatever a harness/gateway exposes into UsageEvent objects,
which the ledger writer turns into (usage_events, postings) rows. Adapters
never write the database directly — they go through a LedgerSink so the
WriteQueue discipline (own connection, batched, never-blocks) is enforced in
one place.

INVARIANT (enforced by validation plus irreversible normalization at every sink
boundary and tested by the privacy canary): open-ended identifiers are hashed;
metadata values must be numbers, bools, reviewed enum strings, or opaque ids.
Prompt text, completion text, file contents, and raw file paths are FORBIDDEN —
this is the content-free ledger invariant (BASEMENT.md law L5) that the entire
trust story depends on.
"""

from __future__ import annotations

import hashlib
import json
import math
import re
from abc import ABC, abstractmethod
from collections.abc import Mapping
from dataclasses import dataclass, field, replace
from datetime import datetime

# Metadata is intentionally a tiny, centrally reviewed vocabulary.  Adding an
# adapter attribute requires adding its content-free key here; arbitrary keys
# are not accepted because names like "payload" can quietly turn the local
# ledger into a prompt/completion store.
ALLOWED_METADATA_KEYS = frozenset(
    {
        "call_type",
        "entrypoint",
        "is_sidechain",
        "migrated_from",
    }
)
_FORBIDDEN_KEY_FRAGMENTS = (
    "completion",
    "content",
    "file",
    "message",
    "payload",
    "prompt",
    "response",
    "text",
    "tool_input",
    "tool_output",
)
_MAX_METADATA_ENTRIES = 16
_MAX_METADATA_STRING_LENGTH = 256
_MAX_METADATA_BYTES = 4_096
_MAX_METADATA_NUMBER = 1_000_000_000_000_000
_MAX_TOKEN_COUNT = 1_000_000_000_000
_MAX_MONEY_AMOUNT = 1_000_000_000
_SAFE_ATOM = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/@+\-]*$")
_OPAQUE_IDENTIFIER = re.compile(r"^[a-z][a-z0-9_-]*:[0-9a-f]{64}$")

# Human-readable values are retained only when they come from a finite,
# reviewed vocabulary.  Every open-ended identifier is irreversibly hashed at
# the persistence boundary; syntactically identifier-shaped prompt text is not
# safe merely because it contains no spaces.
_KNOWN_SOURCES = frozenset(
    {
        "api",
        "claude_code",
        "gateway",
        "legacy-costs-db",
        "legacy-recovery",
        "litellm",
        "mcp",
        "migrate",
        "recovery",
        "stress",
        "test",
        "tracker",
    }
)
_KNOWN_PROVIDERS = frozenset(
    {
        "anthropic",
        "azure",
        "bedrock",
        "cohere",
        "deepseek",
        "google",
        "groq",
        "mistral",
        "openai",
        "vertex_ai",
        "xai",
    }
)
_KNOWN_AGENTS = frozenset({"claude-code", "litellm", "mcp", "stress", "test"})
_KNOWN_METADATA_ENUMS = {
    "call_type": frozenset(
        {
            "acompletion",
            "aembedding",
            "aimage_generation",
            "atranscription",
            "chat",
            "completion",
            "embedding",
            "image_generation",
            "text_completion",
            "transcription",
        }
    ),
    "entrypoint": frozenset({"cli", "plugin", "sdk", "unknown"}),
    "migrated_from": frozenset({"costs.db"}),
}
_POSTING_BASES = frozenset({"plan_model", "pricing_table", "source_reported"})
_MAX_POSTING_AMOUNT = 1_000_000_000


def _validate_metadata_key(key: str) -> None:
    normalized_key = key.lower()
    is_forbidden = any(fragment in normalized_key for fragment in _FORBIDDEN_KEY_FRAGMENTS)
    if key not in ALLOWED_METADATA_KEYS or is_forbidden:
        raise ValueError("metadata key is not content-free and approved")


def _validate_metadata_string(key: str, value: str) -> None:
    if len(value) > _MAX_METADATA_STRING_LENGTH:
        raise ValueError("metadata string is too long")
    if value and _SAFE_ATOM.fullmatch(value) is None:
        raise ValueError("metadata string is not an enum or opaque identifier")


def _validate_metadata_number(key: str, value: int | float) -> None:
    if isinstance(value, float) and not math.isfinite(value):
        raise ValueError("metadata number must be finite")
    if abs(value) > _MAX_METADATA_NUMBER:
        raise ValueError("metadata number is out of bounds")


def _validate_metadata_value(key: str, value: object) -> None:
    if value is None or isinstance(value, bool):
        return
    if isinstance(value, str):
        _validate_metadata_string(key, value)
        return
    if isinstance(value, (int, float)):
        _validate_metadata_number(key, value)
        return
    raise ValueError("metadata value must be a scalar")


def validate_metadata(metadata: Mapping[str, object]) -> None:
    """Enforce the ledger's bounded, content-free metadata contract.

    Values are scalars only; nested objects/arrays and long strings are rejected
    before either synchronous or asynchronous persistence can observe them.
    """
    if len(metadata) > _MAX_METADATA_ENTRIES:
        raise ValueError(f"metadata has more than {_MAX_METADATA_ENTRIES} entries")
    for key, value in metadata.items():
        _validate_metadata_key(key)
        _validate_metadata_value(key, value)

    encoded = json.dumps(metadata, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    if len(encoded) > _MAX_METADATA_BYTES:
        raise ValueError(f"metadata exceeds {_MAX_METADATA_BYTES} UTF-8 bytes")


def _validate_atom(name: str, value: object, *, required: bool, maximum: int = 256) -> None:
    if value is None and not required:
        return
    if not isinstance(value, str) or not value or len(value) > maximum:
        raise ValueError(f"{name} must be a bounded identifier")
    if _SAFE_ATOM.fullmatch(value) is None:
        raise ValueError(f"{name} must contain identifier characters only")


def _validate_tokens(name: str, value: object) -> None:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"{name} must be an integer")
    if value < 0 or value > _MAX_TOKEN_COUNT:
        raise ValueError(f"{name} is out of bounds")


def _validate_event_timestamp(value: object) -> None:
    if not isinstance(value, datetime) or value.utcoffset() is None:
        raise ValueError("event timestamp must be timezone-aware")


def _validate_event_atoms(event: UsageEvent) -> None:
    _validate_atom("event_uid", event.event_uid, required=True, maximum=512)
    _validate_atom("source", event.source, required=True)
    _validate_atom("model", event.model, required=True)
    _validate_atom("provider", event.provider, required=False)
    _validate_atom("session_uid", event.session_uid, required=False, maximum=512)
    _validate_atom("run_id", event.run_id, required=False, maximum=512)
    _validate_atom("agent", event.agent, required=False)


def _is_absolute_workspace_path(value: str) -> bool:
    return value.startswith(("/", "\\\\")) or re.match(r"^[A-Za-z]:[\\/]", value) is not None


def _validate_workspace_path(value: object) -> None:
    if value is None:
        return
    if (
        not isinstance(value, str)
        or not _is_absolute_workspace_path(value)
        or len(value) > 4_096
        or any(ord(character) < 32 for character in value)
    ):
        raise ValueError("workspace_path must be a bounded absolute path")


def _validate_event_tokens(event: UsageEvent) -> None:
    for name in (
        "tokens_in",
        "tokens_out",
        "tokens_cache_read",
        "tokens_cache_write",
    ):
        _validate_tokens(name, getattr(event, name))


def _validate_reported_cost(value: Money | None) -> None:
    if value is None:
        return
    amount = value.amount
    if isinstance(amount, bool) or not isinstance(amount, (int, float)):
        raise ValueError("reported cost must be numeric")
    if not math.isfinite(float(amount)) or amount < 0 or amount > _MAX_MONEY_AMOUNT:
        raise ValueError("reported cost is out of bounds")
    _validate_atom("currency", value.currency, required=True)


def validate_usage_event(event: UsageEvent) -> None:
    """Validate every persisted field, not only the metadata envelope."""
    _validate_event_timestamp(event.ts)
    _validate_event_atoms(event)
    _validate_workspace_path(event.workspace_path)
    _validate_event_tokens(event)
    _validate_reported_cost(event.reported_cost)
    validate_metadata(event.metadata)


@dataclass(frozen=True)
class Money:
    amount: float
    currency: str  # 'USD' | 'CREDIT:<plan_uid>' | 'QUOTA:<plan_uid>:<window>'


@dataclass(frozen=True)
class PostingSpec:
    """One valuation of a UsageEvent in one currency."""

    currency: str
    amount: float
    basis: str  # 'source_reported' | 'pricing_table' | 'plan_model'
    pricing_version: str | None = None


@dataclass(frozen=True)
class UsageEvent:
    event_uid: str  # globally unique, idempotent re-ingest key
    ts: datetime  # timezone-aware UTC
    source: str  # adapter name, e.g. 'claude_code'
    model: str
    provider: str | None = None
    session_uid: str | None = None
    run_id: str | None = None
    agent: str | None = None
    workspace_path: str | None = None
    tokens_in: int = 0
    tokens_out: int = 0
    tokens_cache_read: int = 0
    tokens_cache_write: int = 0
    reported_cost: Money | None = None
    metadata: dict[str, object] = field(default_factory=dict)
    # Resolved at write time by the caller (session_uid/workspace_path -> db ids):
    session_db_id: int | None = None
    workspace_db_id: int | None = None


def content_free_identifier(namespace: str, value: str) -> str:
    """Return a stable opaque id without retaining caller-controlled text."""
    if _OPAQUE_IDENTIFIER.fullmatch(value) is not None and value.startswith(f"{namespace}:"):
        return value
    digest = hashlib.sha256(value.encode("utf-8", errors="replace")).hexdigest()
    return f"{namespace}:{digest}"


def _normalize_enum(namespace: str, value: str | None, known: frozenset[str]) -> str | None:
    if value is None or value in known:
        return value
    return content_free_identifier(namespace, value)


def _normalize_model(value: str) -> str:
    if value.startswith("model:") and _OPAQUE_IDENTIFIER.fullmatch(value):
        return value
    # Lazy import avoids coupling the adapter contracts to pricing at import
    # time while preserving useful, reviewed model names in reports.
    from forecost.pricing import is_priced

    return value if is_priced(value) else content_free_identifier("model", value)


def _normalize_currency(value: str) -> str:
    if value == "USD" or (value.startswith("currency:") and _OPAQUE_IDENTIFIER.fullmatch(value)):
        return value
    return content_free_identifier("currency", value)


def _normalize_pricing_version(value: str | None) -> str | None:
    if value is None:
        return None
    if value.startswith("pricing:") and _OPAQUE_IDENTIFIER.fullmatch(value):
        return value
    # Only versions emitted by the bundled pricing engine remain readable.
    if re.fullmatch(
        r"bundled-[0-9]{4}-[0-9]{2}"
        r"(?:/sonnet5-(?:intro-through-2026-08-31|standard-from-2026-09-01))?"
        r"(?:/unpriced-guess)?",
        value,
    ) or re.fullmatch(r"(?:historic-snapshot|synthetic-plan)/v[0-9]+", value):
        return value
    return content_free_identifier("pricing", value)


def _normalize_metadata(metadata: Mapping[str, object]) -> dict[str, object]:
    normalized: dict[str, object] = {}
    for key, value in metadata.items():
        _validate_metadata_key(key)
        if isinstance(value, str) and value not in _KNOWN_METADATA_ENUMS.get(key, frozenset()):
            normalized[key] = content_free_identifier("metadata", value)
        else:
            normalized[key] = value
    return normalized


def normalize_usage_event(event: UsageEvent) -> UsageEvent:
    """Validate and irreversibly normalize all caller-controlled ledger text."""
    validate_usage_event(event)
    reported_cost = event.reported_cost
    if reported_cost is not None:
        reported_cost = replace(reported_cost, currency=_normalize_currency(reported_cost.currency))
    normalized = replace(
        event,
        event_uid=content_free_identifier("event", event.event_uid),
        source=_normalize_enum("source", event.source, _KNOWN_SOURCES) or "source:unknown",
        model=_normalize_model(event.model),
        provider=_normalize_enum("provider", event.provider, _KNOWN_PROVIDERS),
        session_uid=(
            content_free_identifier("session", event.session_uid)
            if event.session_uid is not None
            else None
        ),
        run_id=(content_free_identifier("run", event.run_id) if event.run_id is not None else None),
        agent=_normalize_enum("agent", event.agent, _KNOWN_AGENTS),
        reported_cost=reported_cost,
        metadata=_normalize_metadata(event.metadata),
    )
    validate_usage_event(normalized)
    return normalized


def normalize_posting_spec(posting: PostingSpec) -> PostingSpec:
    """Validate one posting and remove caller-controlled textual payloads."""
    amount = posting.amount
    if isinstance(amount, bool) or not isinstance(amount, (int, float)):
        raise ValueError("posting amount must be numeric")
    if not math.isfinite(float(amount)) or amount < 0 or amount > _MAX_POSTING_AMOUNT:
        raise ValueError("posting amount is out of bounds")
    if posting.basis not in _POSTING_BASES:
        raise ValueError("posting basis is not supported")
    _validate_atom("posting currency", posting.currency, required=True)
    if posting.pricing_version is not None:
        _validate_atom("pricing_version", posting.pricing_version, required=True)
    normalized = replace(
        posting,
        currency=_normalize_currency(posting.currency),
        pricing_version=_normalize_pricing_version(posting.pricing_version),
    )
    _validate_atom("posting currency", normalized.currency, required=True)
    if normalized.pricing_version is not None:
        _validate_atom("pricing_version", normalized.pricing_version, required=True)
    return normalized


class LedgerSink(ABC):
    """Write side. Backed by the LedgerWriteQueue; computes postings via pricing."""

    @abstractmethod
    def emit(self, event: UsageEvent) -> bool:
        """Accept an event for recording.

        Synchronous sinks return False for a duplicate ``event_uid``. A queued
        internal sink can only report queue acceptance. Transient durability
        failures raise so pull adapters do not advance their cursor.
        """

    @abstractmethod
    def flush(self, timeout: float = 2.0) -> None: ...


class IngestStateStore(ABC):
    @abstractmethod
    def get(self, source: str, key: str) -> str | None: ...

    @abstractmethod
    def set(self, source: str, key: str, value: str) -> None: ...


class PullAdapter(ABC):
    """Adapter that is polled (CLI invocation, hook, daemon tick).

    Stateless between calls; all resume state lives in ingest_state via the
    store handed in. MUST be idempotent (event_uid dedup handles this at the
    write layer) and MUST swallow-and-log per-record parse errors — one
    corrupt line must never halt ingestion (Iron Rule #1 analogue).
    """

    name: str

    @abstractmethod
    def poll(self, state: IngestStateStore, sink: LedgerSink) -> int:
        """Ingest new events since the stored cursor. Returns count ingested."""


class PushAdapter(ABC):
    """Adapter that receives events from a host process (OTel receiver, gateway callback)."""

    name: str

    def __init__(self, sink: LedgerSink) -> None:
        self._sink = sink

    @abstractmethod
    def start(self) -> None: ...

    @abstractmethod
    def stop(self) -> None: ...
