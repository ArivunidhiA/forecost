"""Ingestion adapter contracts: UsageEvent, PostingSpec, and the adapter ABCs.

An adapter turns whatever a harness/gateway exposes into UsageEvent objects,
which the ledger writer turns into (usage_events, postings) rows. Adapters
never write the database directly — they go through a LedgerSink so the
WriteQueue discipline (own connection, batched, never-blocks) is enforced in
one place.

INVARIANT (enforced by convention here, tested by a canary test in Phase 1's
acceptance criteria): UsageEvent.metadata values must be numbers, bools, short
enum strings, or opaque ids. Prompt text, completion text, file contents, and
raw file paths are FORBIDDEN — this is the content-free ledger invariant
(BASEMENT.md law L5) that the entire trust story depends on.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime


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
    metadata: dict = field(default_factory=dict)
    # Resolved at write time by the caller (session_uid/workspace_path -> db ids):
    session_db_id: int | None = None
    workspace_db_id: int | None = None


class LedgerSink(ABC):
    """Write side. Backed by the LedgerWriteQueue; computes postings via pricing."""

    @abstractmethod
    def emit(self, event: UsageEvent) -> bool:
        """Record an event. Returns True if a NEW row was accepted, False if a
        duplicate event_uid was ignored. Raises only on a transient failure the
        caller should retry (adapters treat a raise as 'do not advance cursor')."""

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
