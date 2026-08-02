"""Concrete LedgerSink: resolves workspace/session ids, prices events via
pricing.py, and hands (UsageEvent, postings) to the LedgerWriteQueue.
"""

from __future__ import annotations

from forecost.adapters.base import (
    LedgerSink,
    PostingSpec,
    UsageEvent,
    normalize_posting_spec,
    normalize_usage_event,
    validate_usage_event,
)
from forecost.ledger.db import (
    get_ledger_db,
    get_or_create_session,
    get_or_create_workspace,
    ledger_write_lock,
)
from forecost.ledger.writer import LedgerWriteError, LedgerWriteQueue, _insert_batch
from forecost.pricing import calculate_cost, get_pricing_period, is_priced

PRICING_SNAPSHOT_VERSION = "bundled-2026-08"
# Marker appended to pricing_version when the model was not in the pricing table
# and its cost is a DEFAULT_COST guess. Kept as a version suffix (not a new
# basis) so canonical spend selection is unaffected; `forecost pricing-audit`
# and reconcile can surface these as low-confidence.
UNPRICED_SUFFIX = "/unpriced-guess"

# Backward-compatible internal imports used by hooks and focused tests.
_get_or_create_session = get_or_create_session
_get_or_create_workspace = get_or_create_workspace


def _price_event(event: UsageEvent) -> list[PostingSpec]:
    validate_usage_event(event)
    postings: list[PostingSpec] = []
    usd_cost = calculate_cost(
        event.model,
        event.tokens_in,
        event.tokens_out,
        event.tokens_cache_read,
        event.tokens_cache_write,
        as_of=event.ts,
    )
    pricing_version = PRICING_SNAPSHOT_VERSION
    period = get_pricing_period(event.model, event.ts)
    if period:
        pricing_version += f"/{period}"
    if not is_priced(event.model):
        pricing_version += UNPRICED_SUFFIX  # cost is a DEFAULT_COST guess, flag it
    postings.append(
        PostingSpec(
            currency="USD",
            amount=usd_cost,
            basis="pricing_table",
            pricing_version=pricing_version,
        )
    )
    if event.reported_cost is not None:
        postings.append(
            PostingSpec(
                currency=event.reported_cost.currency,
                amount=event.reported_cost.amount,
                basis="source_reported",
            )
        )
    return [normalize_posting_spec(posting) for posting in postings]


class SyncLedgerSink(LedgerSink):
    """Direct, synchronous writes — correct-by-default for CLI batch ingestion
    (e.g. `forecost ingest`, reading a few hundred JSONL turns in one pass).
    Uses INSERT OR IGNORE on event_uid for idempotent re-ingest, same as the
    async path. This is the supported sink for CLI, hooks, and gateways."""

    def __init__(self, ledger_path=None) -> None:
        self._conn = get_ledger_db(ledger_path)

    def emit(self, event: UsageEvent) -> bool:
        # A shared check_same_thread=False connection still needs application
        # serialization: without this lock, one thread could commit another
        # thread's half-written event. _insert_batch wraps resolution, event,
        # postings, and commit in one rollback-safe transaction.
        normalized = normalize_usage_event(event)
        with ledger_write_lock:
            return _insert_batch(self._conn, [(normalized, _price_event(normalized))]) == 1

    def emit_with_postings(self, event: UsageEvent, postings: list[PostingSpec]) -> bool:
        """Replay already-durable postings without re-pricing or losing provenance."""
        normalized = normalize_usage_event(event)
        normalized_postings = [normalize_posting_spec(posting) for posting in postings]
        with ledger_write_lock:
            return _insert_batch(self._conn, [(normalized, normalized_postings)]) == 1

    def flush(self, timeout: float = 2.0) -> None:
        del timeout
        with ledger_write_lock:
            self._conn.commit()


class DefaultLedgerSink(LedgerSink):
    """Internal asynchronous sink retained for compatibility and stress tests.

    Supported integrations use ``SyncLedgerSink`` so returning from ``emit``
    means the event is durable. This class guarantees durability on explicit
    ``flush`` and normal process exit, but queued duplicate status is unknown.
    """

    def __init__(self, ledger_path=None) -> None:
        from forecost.ledger.db import LEDGER_PATH

        self._queue = LedgerWriteQueue(ledger_path if ledger_path is not None else LEDGER_PATH)

    def emit(self, event: UsageEvent) -> bool:
        normalized = normalize_usage_event(event)
        accepted = self._queue.put(normalized, _price_event(normalized))
        if not accepted:
            raise LedgerWriteError(self._queue.last_error or "ledger queue refused event")
        # Queued for the async worker; duplicate detection happens at write time.
        # Report True (accepted for writing) — the DB's INSERT OR IGNORE is the
        # source of truth for idempotency, so callers must not treat this as a
        # guaranteed new-row count.
        return accepted

    def flush(self, timeout: float = 5.0) -> None:
        # Real drain barrier (not a sleep): returns once every queued event has
        # been committed, so a subsequent read (e.g. calibration reconcile) sees
        # its own writes. Callers that need read-your-writes must see a drain or
        # spill failure rather than silently continuing with stale aggregates.
        if not self._queue.drain(timeout):
            raise LedgerWriteError(self._queue.last_error or "ledger drain failed")
