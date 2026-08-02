"""Deterministic, synthetic, content-free product fixtures for Forecost Run Lab."""

from __future__ import annotations

import random
import sqlite3
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from hashlib import sha256

from forecost.ledger.contracts import CausalIdentity, opaque_id
from forecost.ledger.evidence import append_observation, observation


def _at(index: int) -> datetime:
    return datetime(2026, 1, 1, tzinfo=timezone.utc) + timedelta(seconds=index)


def _causal(seed: int, span: str, sequence: int, *, parent: str | None = None) -> CausalIdentity:
    def span_id(name: str) -> str:
        return sha256(f"{seed}:{name}".encode()).hexdigest()[:16]

    return CausalIdentity(
        conversation_id=f"lab-conversation-{seed}",
        trace_id=f"{seed:032x}"[-32:],
        run_id=f"lab-run-{seed}",
        span_id=span_id(span),
        parent_span_id=(span_id(parent) if parent else None),
        source_sequence=sequence,
        idempotency_key=f"lab-{seed}-{span}-{sequence}",
    )


def seed_demo(conn: sqlite3.Connection, seed: int = 7) -> str:
    """Create a compact fan-out/retry/fan-in receipt with conflicting sources."""
    root = _causal(seed, "root", 1)
    model_a = _causal(seed, "model-a", 2, parent="root")
    model_b = _causal(seed, "model-b", 3, parent="root")
    retry = _causal(seed, "retry", 4, parent="root")
    tool = _causal(seed, "tool", 5, parent="root")
    join = replace(
        _causal(seed, "join", 6, parent="root"),
        links=(model_a.span_id, model_b.span_id, retry.span_id, tool.span_id),
    )
    spans = (
        (root, {"operation_kind": "agent", "lifecycle": "completed", "branch_id": "root"}),
        (model_a, {"operation_kind": "model", "lifecycle": "completed", "branch_id": "a"}),
        (model_b, {"operation_kind": "model", "lifecycle": "completed", "branch_id": "b"}),
        (
            retry,
            {
                "operation_kind": "model",
                "lifecycle": "completed",
                "branch_id": "a",
                "attempt_of_span_id": model_a.normalized().span_id,
            },
        ),
        (tool, {"operation_kind": "tool", "lifecycle": "completed", "branch_id": "b"}),
        (join, {"operation_kind": "handoff", "lifecycle": "completed", "branch_id": "join"}),
    )
    for index, (causal, payload) in enumerate(spans, start=1):
        append_observation(
            conn,
            observation(
                producer="offline_lab",
                event_kind="span",
                causal=causal,
                payload=payload,
                occurred_at=_at(index),
                observed_at=_at(index + 1),
            ),
        )
    meter_causal = replace(model_a, source_sequence=10, idempotency_key=f"lab-{seed}-meter-a")
    meter = observation(
        producer="offline_lab",
        event_kind="meter",
        causal=meter_causal,
        payload={
            "meter_name": "tokens.output",
            "unit": "token",
            "quantity_micros": 1_250_000_000,
            "aggregation": "delta",
            "dimensions": {"model_class": "synthetic"},
            "finality": "final",
        },
        occurred_at=_at(10),
        observed_at=_at(11),
    )
    append_observation(conn, meter)
    fact_id = opaque_id("fact", meter.observation_id)
    for sequence, authority, amount in (
        (11, "list_rate", 125_000),
        (12, "gateway_estimate", 121_000),
    ):
        charge_causal = replace(
            model_a,
            source_sequence=sequence,
            idempotency_key=f"lab-{seed}-charge-{authority}",
        )
        append_observation(
            conn,
            observation(
                producer="offline_lab",
                event_kind="charge",
                causal=charge_causal,
                payload={
                    "fact_id": fact_id,
                    "amount_micros": amount,
                    "currency": "USD",
                    "authority": authority,
                    "line_item": "model_inference",
                    "tariff": {"rate_snapshot": "synthetic-v1"},
                    "finality": "final",
                },
                occurred_at=_at(sequence),
                observed_at=_at(sequence + 1),
            ),
        )
    outcome_causal = replace(root, source_sequence=20, idempotency_key=f"lab-{seed}-outcome")
    append_observation(
        conn,
        observation(
            producer="offline_lab",
            event_kind="outcome",
            causal=outcome_causal,
            payload={
                "outcome_status": "partial",
                "reason_code": "synthetic_fixture",
                "evidence_type": "test_exit",
                "confidence": "observed",
            },
            occurred_at=_at(20),
            observed_at=_at(21),
        ),
    )
    return root.normalized().run_id


def seed_chaos(conn: sqlite3.Connection, seed: int, branches: int) -> str:
    """Generate a seed-replayable graph with fan-out, waits, cancellation, and retries."""
    if branches < 1 or branches > 128:
        raise ValueError("branches must be between 1 and 128")
    rng = random.Random(seed)  # noqa: S311 - deterministic synthetic fixture, never a secret
    root = _causal(seed, "chaos-root", 1)
    append_observation(
        conn,
        observation(
            producer="offline_lab",
            event_kind="span",
            causal=root,
            payload={"operation_kind": "agent", "lifecycle": "running", "branch_id": "root"},
            occurred_at=_at(1),
            observed_at=_at(1),
        ),
    )
    for branch in range(branches):
        state = "cancelled" if rng.randrange(9) == 0 else "completed"
        branch_causal = _causal(seed, f"chaos-{branch}", branch + 2, parent="chaos-root")
        append_observation(
            conn,
            observation(
                producer="offline_lab",
                event_kind="span",
                causal=branch_causal,
                payload={"operation_kind": "model", "lifecycle": state, "branch_id": f"b{branch}"},
                occurred_at=_at(branch + 2),
                observed_at=_at(branch + 3),
            ),
        )
    final_causal = replace(
        root,
        source_sequence=branches + 3,
        idempotency_key=f"chaos-{seed}-end",
    )
    append_observation(
        conn,
        observation(
            producer="offline_lab",
            event_kind="span",
            causal=final_causal,
            payload={"operation_kind": "agent", "lifecycle": "completed", "branch_id": "root"},
            occurred_at=_at(branches + 3),
            observed_at=_at(branches + 4),
        ),
    )
    return root.normalized().run_id
