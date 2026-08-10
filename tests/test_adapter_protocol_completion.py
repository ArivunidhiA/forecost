from __future__ import annotations

import io
import json
from datetime import datetime, timezone

from click.testing import CliRunner

from forecost.adapters.base import UsageEvent
from forecost.adapters.claude_code import (
    claude_lifecycle_observation,
    claude_record_observations,
)
from forecost.adapters.frameworks import langgraph_observations, openai_agents_observations
from forecost.adapters.otel import load_records, otel_observations
from forecost.adapters.outbox import DurableEventOutbox
from forecost.adapters.protocol import ADAPTER_CAPABILITIES, conformance_report
from forecost.commands.adapters_cmd import adapters


def _span(**updates):
    value = {
        "conversation_id": "conversation-1",
        "trace_id": "0123456789abcdef0123456789abcdef",
        "run_id": "run-1",
        "span_id": "0123456789abcdef",
        "idempotency_key": "event-1",
        "source_sequence": 1,
        "span_type": "generation",
        "lifecycle": "completed",
        "occurred_at": "2026-01-01T00:00:00Z",
    }
    value.update(updates)
    return value


def test_capability_protocol_and_cli_report_are_versioned():
    report = conformance_report()
    assert report["conformant"] is True
    assert {item.name for item in ADAPTER_CAPABILITIES} == {
        "claude_jsonl",
        "litellm",
        "otel_genai",
        "openai_agents",
        "langgraph",
    }
    result = CliRunner().invoke(adapters, ["check", "--json"])
    assert result.exit_code == 0
    assert json.loads(result.output)["protocol_version"] == 1


def test_openai_agents_mapping_selects_fields_and_distinguishes_usage_scope():
    items = openai_agents_observations(
        _span(
            input_tokens=7,
            output_tokens=3,
            usage_scope="generation",
            input="NEVER-PERSIST",
            output="NEVER-PERSIST",
            span_data={"content": "NEVER-PERSIST"},
        )
    )
    assert [item.event_kind for item in items] == ["span", "meter", "meter"]
    encoded = json.dumps([item.normalized().payload for item in items])
    assert "NEVER-PERSIST" not in encoded
    assert all(item.normalized().payload.get("finality") == "final" for item in items[1:])


def test_langgraph_mapping_preserves_checkpoint_parallel_and_replay_identity():
    first = langgraph_observations(
        _span(
            span_type="checkpoint",
            checkpoint_id="checkpoint-7",
            branch_id="parallel-a",
            links=["fedcba9876543210"],
        )
    )[0].normalized()
    replay = langgraph_observations(
        _span(
            idempotency_key="event-2",
            lifecycle="replayed",
            attempt_of_span_id="fedcba9876543210",
        )
    )[0].normalized()
    assert first.payload["operation_kind"] == "checkpoint"
    assert first.payload["checkpoint_id"] is not None
    assert first.causal.links == ("fedcba9876543210",)
    assert replay.payload["lifecycle"] == "replayed"


def test_otel_accepts_jsonl_spans_and_metrics_and_ignores_attributes():
    records = load_records(
        io.StringIO(
            json.dumps(_span(kind="span", attributes={"prompt": "NEVER"}))
            + "\n"
            + json.dumps(
                _span(
                    kind="metric",
                    idempotency_key="metric-1",
                    meter_name="tokens.input",
                    quantity_micros=4_000_000,
                    finality="final",
                )
            )
        )
    )
    items = otel_observations(records)
    assert [item.event_kind for item in items] == ["span", "meter"]
    assert "NEVER" not in json.dumps([item.normalized().payload for item in items])


def test_claude_lifecycle_mapping_covers_current_events_without_content():
    events = {
        "ExitPlanMode",
        "Agent",
        "SubagentStart",
        "SubagentStop",
        "PostToolUse",
        "PostToolBatch",
        "PostToolUseFailure",
        "StopFailure",
        "TaskCreated",
        "TaskCompleted",
        "Interrupt",
        "BackgroundAgentSettled",
    }
    for sequence, name in enumerate(sorted(events), start=1):
        item = claude_lifecycle_observation(
            {
                "session_id": "session-1",
                "prompt_id": "turn-1",
                "hook_id": f"hook-{sequence}",
                "tool_input": "NEVER-PERSIST",
                "tool_output": "NEVER-PERSIST",
            },
            name,
            source_sequence=sequence,
            occurred_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        ).normalized()
        assert "NEVER-PERSIST" not in json.dumps(item.payload)
        assert item.causal.run_id.startswith("run:")


def test_claude_assistant_mapping_deduplicates_blocks_and_emits_final_meters(ledger_conn):
    from forecost.ledger.evidence import append_observation

    record = {
        "type": "assistant",
        "requestId": "request-1",
        "uuid": "block-1",
        "sessionId": "session-1",
        "timestamp": "2026-01-01T00:00:00Z",
        "message": {
            "model": "claude-sonnet-4-20250514",
            "usage": {"input_tokens": 7, "output_tokens": 3},
            "content": "NEVER-PERSIST",
        },
    }
    first = claude_record_observations(record, "turn-1")
    repeated = claude_record_observations({**record, "uuid": "block-2"}, "turn-1")
    assert sum(append_observation(ledger_conn, item) for item in first) == 3
    assert sum(append_observation(ledger_conn, item) for item in repeated) == 0
    assert ledger_conn.execute("SELECT COUNT(*) FROM causal_spans").fetchone()[0] == 1
    assert ledger_conn.execute("SELECT COUNT(*) FROM meter_facts").fetchone()[0] == 2
    blob = "".join(
        row[0]
        for row in ledger_conn.execute(
            "SELECT causal_json || payload_json FROM journal_observations"
        )
    )
    assert "NEVER-PERSIST" not in blob


def test_durable_outbox_replays_idempotently_and_quarantines_poison(tmp_path):
    queue = DurableEventOutbox(tmp_path / "outbox" / "events.jsonl", batch_size=10)
    event = UsageEvent(
        event_uid="callback-1",
        ts=datetime(2026, 1, 1, tzinfo=timezone.utc),
        source="litellm",
        model="gpt-4o",
        tokens_in=1,
    )
    assert queue.enqueue(event) is True
    attempts = 0

    def transient(_event):
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise RuntimeError("locked")

    assert queue.drain(transient) == 0
    assert queue.status()["depth"] == 1
    assert queue.drain(transient) == 1
    assert queue.status()["replayed"] == 1

    queue.path.write_text("not-json\n", encoding="utf-8")
    assert queue.drain(lambda _event: None) == 0
    status = queue.status()
    assert status["poison"] == 1
    assert queue.poison_path.exists()
    assert "not-json" not in queue.poison_path.read_text(encoding="utf-8")


def test_durable_outbox_has_an_explicit_bounded_fail_open_state(tmp_path):
    queue = DurableEventOutbox(tmp_path / "outbox.jsonl", max_records=1)
    event = UsageEvent(
        event_uid="one",
        ts=datetime(2026, 1, 1, tzinfo=timezone.utc),
        source="litellm",
        model="gpt-4o",
    )
    assert queue.enqueue(event) is True
    assert queue.enqueue(event) is False
    assert queue.status()["dropped"] == 1
