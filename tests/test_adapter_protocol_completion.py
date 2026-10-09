from __future__ import annotations

import io
import json
import multiprocessing
import threading
from datetime import datetime, timezone

import pytest
from click.testing import CliRunner

from forecost.adapters import outbox as outbox_mod
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
from forecost.core.paths import UnsafeDataPathError


def _outbox_paused_drain_worker(path, emit_started, release_emit, results):
    queue = DurableEventOutbox(path)

    def pause_emit(event):
        results.put(("drained", event.event_uid))
        emit_started.set()
        if not release_emit.wait(10):
            raise TimeoutError("test did not release outbox drain")

    results.put(("drain_count", queue.drain(pause_emit)))


def _outbox_contending_enqueue_worker(path, attempted, finished, results):
    queue = DurableEventOutbox(path)
    event = UsageEvent(
        event_uid="enqueued-cross-process",
        ts=datetime(2026, 1, 1, tzinfo=timezone.utc),
        source="litellm",
        model="gpt-4o",
    )
    attempted.set()
    results.put(("enqueued", queue.enqueue(event)))
    finished.set()


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


def test_durable_outbox_refuses_symlink_without_clobbering_target(tmp_path):
    target = tmp_path / "operator.txt"
    target.write_text("preserve", encoding="utf-8")
    outbox = tmp_path / "outbox.jsonl"
    outbox.symlink_to(target)
    queue = DurableEventOutbox(outbox)
    event = UsageEvent(
        event_uid="symlink",
        ts=datetime(2026, 1, 1, tzinfo=timezone.utc),
        source="litellm",
        model="gpt-4o",
    )

    with pytest.raises(UnsafeDataPathError, match="refusing symlinked"):
        queue.enqueue(event)

    assert target.read_text(encoding="utf-8") == "preserve"


def test_durable_outbox_fsyncs_new_queue_and_atomic_replacements(tmp_path, monkeypatch):
    queue = DurableEventOutbox(tmp_path / "outbox" / "events.jsonl")
    event = UsageEvent(
        event_uid="durable-publication",
        ts=datetime(2026, 1, 1, tzinfo=timezone.utc),
        source="litellm",
        model="gpt-4o",
    )
    synced: list[object] = []
    monkeypatch.setattr(outbox_mod, "_fsync_directory", synced.append)

    assert queue.enqueue(event) is True
    queue._write_lines([])

    assert tmp_path in synced  # newly created outbox directory name
    assert synced.count(queue.path.parent) >= 3  # queue create, stats replace, queue replace


def test_durable_outbox_reports_new_queue_directory_sync_failure_without_losing_record(
    tmp_path, monkeypatch
):
    parent = tmp_path / "outbox"
    parent.mkdir()
    queue = DurableEventOutbox(parent / "events.jsonl")
    event = UsageEvent(
        event_uid="uncertain-publication",
        ts=datetime(2026, 1, 1, tzinfo=timezone.utc),
        source="litellm",
        model="gpt-4o",
    )

    def fail_directory_sync(_path):
        raise OSError("directory sync failed")

    monkeypatch.setattr(outbox_mod, "_fsync_directory", fail_directory_sync)

    with pytest.raises(OSError, match="directory sync failed"):
        queue.enqueue(event)

    queued = json.loads(queue.path.read_text(encoding="utf-8"))
    assert queued["schema_version"] == outbox_mod.OUTBOX_SCHEMA_VERSION


def test_durable_outbox_fsyncs_new_poison_append(tmp_path, monkeypatch):
    queue = DurableEventOutbox(tmp_path / "events.jsonl")
    queue.path.write_text("not-json\n", encoding="utf-8")
    synced: list[object] = []
    monkeypatch.setattr(outbox_mod, "_fsync_directory", synced.append)

    assert queue.drain(lambda _event: None) == 0

    assert synced.count(tmp_path) >= 3  # poison create, stats replace, queue replace


def test_durable_outbox_thread_lock_prevents_enqueue_during_drain_rewrite(tmp_path, monkeypatch):
    path = tmp_path / "events.jsonl"
    draining_queue = DurableEventOutbox(path)
    enqueueing_queue = DurableEventOutbox(path)
    first = UsageEvent(
        event_uid="drained-first",
        ts=datetime(2026, 1, 1, tzinfo=timezone.utc),
        source="litellm",
        model="gpt-4o",
    )
    second = UsageEvent(
        event_uid="enqueued-during-drain",
        ts=datetime(2026, 1, 1, tzinfo=timezone.utc),
        source="litellm",
        model="gpt-4o",
    )
    assert draining_queue.enqueue(first) is True
    emit_started = threading.Event()
    release_emit = threading.Event()
    enqueue_finished = threading.Event()
    drained: list[str] = []

    # Exercise the shared process lock independently of the platform's file
    # lock. On Windows the descriptor helpers use msvcrt byte-range locking.
    monkeypatch.setattr(outbox_mod, "_lock_descriptor", lambda _descriptor: None)
    monkeypatch.setattr(outbox_mod, "_unlock_descriptor", lambda _descriptor: None)

    def pause_emit(event):
        drained.append(event.event_uid)
        emit_started.set()
        assert release_emit.wait(5)

    def enqueue_second():
        assert enqueueing_queue.enqueue(second) is True
        enqueue_finished.set()

    drain_thread = threading.Thread(target=draining_queue.drain, args=(pause_emit,))
    enqueue_thread = threading.Thread(target=enqueue_second)
    drain_thread.start()
    assert emit_started.wait(5)
    enqueue_thread.start()
    assert not enqueue_finished.wait(0.1)
    release_emit.set()
    drain_thread.join(5)
    enqueue_thread.join(5)

    assert not drain_thread.is_alive()
    assert not enqueue_thread.is_alive()
    remaining: list[str] = []
    assert draining_queue.drain(lambda event: remaining.append(event.event_uid)) == 1
    assert len(remaining) == 1
    assert len(drained) == 1
    assert remaining != drained


def test_durable_outbox_process_lock_preserves_enqueue_during_drain_rewrite(tmp_path):
    path = tmp_path / "events.jsonl"
    queue = DurableEventOutbox(path)
    first = UsageEvent(
        event_uid="drained-cross-process",
        ts=datetime(2026, 1, 1, tzinfo=timezone.utc),
        source="litellm",
        model="gpt-4o",
    )
    assert queue.enqueue(first) is True

    context = multiprocessing.get_context("spawn")
    emit_started = context.Event()
    release_emit = context.Event()
    attempted = context.Event()
    finished = context.Event()
    results = context.Queue()
    drain_process = context.Process(
        target=_outbox_paused_drain_worker,
        args=(path, emit_started, release_emit, results),
    )
    enqueue_process = context.Process(
        target=_outbox_contending_enqueue_worker,
        args=(path, attempted, finished, results),
    )

    drain_process.start()
    assert emit_started.wait(10)
    enqueue_process.start()
    assert attempted.wait(10)
    assert not finished.wait(0.2)
    release_emit.set()
    drain_process.join(10)
    enqueue_process.join(10)

    assert drain_process.exitcode == 0
    assert enqueue_process.exitcode == 0
    messages = [results.get(timeout=2) for _ in range(3)]
    assert ("drain_count", 1) in messages
    assert ("enqueued", True) in messages
    remaining: list[str] = []
    assert queue.drain(lambda event: remaining.append(event.event_uid)) == 1
    assert remaining != [next(value for label, value in messages if label == "drained")]
