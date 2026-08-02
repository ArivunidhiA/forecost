from __future__ import annotations

import pytest

from forecost.adapters.causal import runtime_span_observation
from forecost.ledger.evidence import append_observation


def test_runtime_mapper_keeps_structural_identity_and_drops_content(ledger_conn):
    item = runtime_span_observation(
        {
            "conversation_id": "conversation-raw",
            "trace_id": "0123456789abcdef0123456789abcdef",
            "run_id": "run-raw",
            "span_id": "0123456789abcdef",
            "idempotency_key": "runtime-event-1",
            "source_sequence": 1,
            "operation_kind": "agent",
            "lifecycle": "completed",
            "occurred_at": "2026-01-01T00:00:00Z",
            "attributes": {"prompt": "DO-NOT-PERSIST"},
            "baggage": "DO-NOT-PERSIST",
            "tracestate": "DO-NOT-PERSIST",
        },
        producer="openai_agents",
    )
    append_observation(ledger_conn, item)
    blob = "\n".join(
        row[0]
        for row in ledger_conn.execute(
            "SELECT causal_json || payload_json FROM journal_observations"
        ).fetchall()
    )

    assert "DO-NOT-PERSIST" not in blob
    assert "conversation-raw" not in blob


def test_runtime_mapper_requires_trace_context_not_payload_text():
    with pytest.raises(ValueError, match="trace_id"):
        runtime_span_observation(
            {
                "conversation_id": "c",
                "run_id": "r",
                "span_id": "0123456789abcdef",
                "idempotency_key": "i",
                "occurred_at": "2026-01-01T00:00:00Z",
            },
            producer="otel",
        )
