import json
import os
from pathlib import Path

import pytest

from forecost.adapters import claude_code as claude_adapter
from forecost.adapters.base import LedgerSink, UsageEvent, content_free_identifier
from forecost.adapters.claude_code import (
    ClaudeCodeAdapter,
    _cursor_key,
    ingest_causal_paths,
)
from forecost.core.local_identity import installation_key
from forecost.ledger.state_store import LedgerIngestStateStore


@pytest.fixture(autouse=True)
def _isolated_identity_home(tmp_path, monkeypatch):
    """Cursor HMAC keys must never escape a test's temporary installation."""
    monkeypatch.setenv("FORECOST_HOME", str(tmp_path / "forecost-home"))


class _CollectingSink(LedgerSink):
    def __init__(self):
        self.events: list[UsageEvent] = []

    def emit(self, event: UsageEvent) -> None:
        self.events.append(event)

    def flush(self, timeout: float = 2.0) -> None:
        pass


def _write_session(path, records):
    with open(path, "w", encoding="utf-8") as f:
        for rec in records:
            f.write(json.dumps(rec) + "\n")


def test_adapter_ingests_assistant_usage_records(tmp_path, ledger_conn):
    project_dir = tmp_path / "-Users-x-proj"
    project_dir.mkdir()
    session_file = project_dir / "sess-1.jsonl"
    _write_session(
        session_file,
        [
            {
                "type": "user",
                "promptId": "p1",
                "isMeta": False,
                "sessionId": "sess-1",
                "cwd": "/Users/x/proj",
                "timestamp": "2026-07-01T00:00:00Z",
                "message": {"content": "do a thing"},
            },
            {
                "type": "assistant",
                "requestId": "req-1",
                "uuid": "u1",
                "sessionId": "sess-1",
                "cwd": "/Users/x/proj",
                "timestamp": "2026-07-01T00:00:05Z",
                "message": {
                    "model": "claude-sonnet-4-20250514",
                    "usage": {"input_tokens": 1000, "output_tokens": 200},
                },
            },
        ],
    )

    adapter = ClaudeCodeAdapter(claude_dir=tmp_path)
    sink = _CollectingSink()
    state = LedgerIngestStateStore(ledger_conn)
    n = adapter.poll(state, sink)

    assert n == 1
    assert len(sink.events) == 1
    ev = sink.events[0]
    assert ev.model == "claude-sonnet-4-20250514"
    assert ev.tokens_in == 1000
    assert ev.tokens_out == 200
    assert ev.run_id == "p1"
    assert ev.workspace_path == "/Users/x/proj"


def test_adapter_skips_records_without_usage(tmp_path, ledger_conn):
    project_dir = tmp_path / "-proj"
    project_dir.mkdir()
    session_file = project_dir / "sess-2.jsonl"
    _write_session(
        session_file,
        [
            {
                "type": "assistant",
                "requestId": "r1",
                "uuid": "u1",
                "sessionId": "sess-2",
                "timestamp": "2026-07-01T00:00:00Z",
                "message": {"model": "<synthetic>"},
            },
            {
                "type": "assistant",
                "requestId": "r2",
                "uuid": "u2",
                "sessionId": "sess-2",
                "timestamp": "2026-07-01T00:00:00Z",
                "message": {"model": "claude-sonnet-4-20250514"},
            },
        ],
    )
    adapter = ClaudeCodeAdapter(claude_dir=tmp_path)
    sink = _CollectingSink()
    state = LedgerIngestStateStore(ledger_conn)
    n = adapter.poll(state, sink)
    assert n == 0


def test_adapter_tolerates_corrupt_lines(tmp_path, ledger_conn):
    project_dir = tmp_path / "-proj"
    project_dir.mkdir()
    session_file = project_dir / "sess-3.jsonl"
    with open(session_file, "w") as f:
        f.write("not valid json {{{\n")
        f.write(
            json.dumps(
                {
                    "type": "assistant",
                    "requestId": "r1",
                    "uuid": "u1",
                    "sessionId": "sess-3",
                    "timestamp": "2026-07-01T00:00:00Z",
                    "message": {
                        "model": "claude-sonnet-4-20250514",
                        "usage": {"input_tokens": 10, "output_tokens": 5},
                    },
                }
            )
            + "\n"
        )
    adapter = ClaudeCodeAdapter(claude_dir=tmp_path)
    sink = _CollectingSink()
    state = LedgerIngestStateStore(ledger_conn)
    n = adapter.poll(state, sink)
    assert n == 1  # the corrupt line was skipped, not fatal


@pytest.mark.parametrize(
    "invalid_message",
    [
        "prompt-shaped string",
        {"model": "claude-sonnet-4-20250514", "usage": "not-an-object"},
        {
            "model": "claude-sonnet-4-20250514",
            "usage": {"input_tokens": "many", "output_tokens": 5},
        },
        {
            "model": "secret prompt text with spaces",
            "usage": {"input_tokens": 10, "output_tokens": 5},
        },
    ],
)
def test_schema_invalid_record_is_skipped_without_pinning_cursor(
    tmp_path, ledger_conn, invalid_message
):
    project_dir = tmp_path / "-invalid-shape"
    project_dir.mkdir()
    session_file = project_dir / "sess-invalid.jsonl"
    valid = {
        "type": "assistant",
        "requestId": "valid-after-invalid",
        "sessionId": "sess-invalid",
        "cwd": "/synthetic/project",
        "timestamp": "2026-07-01T00:00:01Z",
        "message": {
            "model": "claude-sonnet-4-20250514",
            "usage": {"input_tokens": 10, "output_tokens": 5},
        },
    }
    _write_session(
        session_file,
        [
            {
                "type": "assistant",
                "requestId": "invalid",
                "sessionId": "sess-invalid",
                "cwd": "/synthetic/project",
                "timestamp": "2026-07-01T00:00:00Z",
                "message": invalid_message,
            },
            valid,
        ],
    )

    adapter = ClaudeCodeAdapter(claude_dir=tmp_path)
    sink = _CollectingSink()
    state = LedgerIngestStateStore(ledger_conn)

    assert adapter.poll(state, sink) == 1
    assert [event.event_uid for event in sink.events] == ["cc:valid-after-invalid"]
    assert adapter.poll(state, sink) == 0


def test_adapter_resume_is_idempotent(tmp_path, ledger_conn):
    project_dir = tmp_path / "-proj"
    project_dir.mkdir()
    session_file = project_dir / "sess-4.jsonl"
    _write_session(
        session_file,
        [
            {
                "type": "assistant",
                "requestId": "r1",
                "uuid": "u1",
                "sessionId": "sess-4",
                "timestamp": "2026-07-01T00:00:00Z",
                "message": {
                    "model": "claude-sonnet-4-20250514",
                    "usage": {"input_tokens": 10, "output_tokens": 5},
                },
            },
        ],
    )
    adapter = ClaudeCodeAdapter(claude_dir=tmp_path)
    sink = _CollectingSink()
    state = LedgerIngestStateStore(ledger_conn)

    n1 = adapter.poll(state, sink)
    n2 = adapter.poll(state, sink)  # nothing new appended
    assert n1 == 1
    assert n2 == 0


def test_multi_block_response_counts_once(tmp_path, ledger_conn):
    """One API response is written as several content-block records that repeat
    the identical usage. They must collapse to ONE usage_event (the fix for the
    ~2.25x inflation), keyed by requestId — not one event per block."""
    from forecost.ledger.sink import SyncLedgerSink

    project_dir = tmp_path / "-proj"
    project_dir.mkdir()
    blocks = [
        {
            "type": "assistant",
            "requestId": "req-multi",
            "uuid": f"u{i}",  # distinct per block — the old key would split these
            "sessionId": "sess-mb",
            "cwd": "/x",
            "timestamp": "2026-07-01T00:00:00Z",
            "message": {
                "model": "claude-sonnet-4-20250514",
                "usage": {"input_tokens": 1000, "output_tokens": 200},
            },
        }
        for i in range(3)
    ]
    _write_session(project_dir / "sess-mb.jsonl", blocks)

    adapter = ClaudeCodeAdapter(claude_dir=tmp_path)
    sink = SyncLedgerSink(ledger_path=None)
    sink._conn = ledger_conn
    state = LedgerIngestStateStore(ledger_conn)
    n = adapter.poll(state, sink)

    assert n == 1, "three content-block records of one request must count once"
    rows = ledger_conn.execute("SELECT COUNT(*) FROM usage_events").fetchone()[0]
    assert rows == 1
    # And the single event carries the (non-doubled) usage, priced once.
    posts = ledger_conn.execute(
        "SELECT COUNT(*) FROM postings WHERE basis='pricing_table'"
    ).fetchone()[0]
    assert posts == 1


def test_torn_final_line_is_not_lost(tmp_path, ledger_conn):
    """A partially-written final line (no trailing newline) must not advance the
    cursor past it; when the writer completes the line, the next poll ingests it."""
    from forecost.ledger.sink import SyncLedgerSink

    project_dir = tmp_path / "-proj"
    project_dir.mkdir()
    session_file = project_dir / "sess-torn.jsonl"
    complete = json.dumps(
        {
            "type": "assistant",
            "requestId": "req-a",
            "uuid": "ua",
            "sessionId": "sess-torn",
            "timestamp": "2026-07-01T00:00:00Z",
            "message": {
                "model": "claude-sonnet-4-20250514",
                "usage": {"input_tokens": 10, "output_tokens": 5},
            },
        }
    )
    torn = json.dumps(
        {
            "type": "assistant",
            "requestId": "req-b",
            "uuid": "ub",
            "sessionId": "sess-torn",
            "timestamp": "2026-07-01T00:00:01Z",
            "message": {
                "model": "claude-sonnet-4-20250514",
                "usage": {"input_tokens": 20, "output_tokens": 8},
            },
        }
    )
    # Write the complete line + a torn (newline-less) tail.
    with open(session_file, "w", encoding="utf-8") as f:
        f.write(complete + "\n")
        f.write(torn)  # no trailing newline yet — writer is mid-append

    adapter = ClaudeCodeAdapter(claude_dir=tmp_path)
    sink = SyncLedgerSink(ledger_path=None)
    sink._conn = ledger_conn
    state = LedgerIngestStateStore(ledger_conn)

    assert adapter.poll(state, sink) == 1  # only the complete line
    # Writer finishes the torn line.
    with open(session_file, "a", encoding="utf-8") as f:
        f.write("\n")
    assert adapter.poll(state, sink) == 1  # the once-torn line is now ingested, not lost
    assert ledger_conn.execute("SELECT COUNT(*) FROM usage_events").fetchone()[0] == 2


def test_failed_emit_does_not_advance_cursor(tmp_path, ledger_conn):
    """A transient emit failure must leave the cursor before the record so it is
    retried (idempotently) on the next poll — no silent undercount."""
    from forecost.adapters.base import LedgerSink

    project_dir = tmp_path / "-proj"
    project_dir.mkdir()
    session_file = project_dir / "sess-fail.jsonl"
    _write_session(
        session_file,
        [
            {
                "type": "assistant",
                "requestId": "req-f",
                "uuid": "uf",
                "sessionId": "sess-fail",
                "timestamp": "2026-07-01T00:00:00Z",
                "message": {
                    "model": "claude-sonnet-4-20250514",
                    "usage": {"input_tokens": 10, "output_tokens": 5},
                },
            }
        ],
    )

    class _FlakySink(LedgerSink):
        def __init__(self):
            self.calls = 0

        def emit(self, event):
            self.calls += 1
            if self.calls == 1:
                raise RuntimeError("transient DB lock")
            return True

        def flush(self, timeout=2.0):
            pass

    adapter = ClaudeCodeAdapter(claude_dir=tmp_path)
    state = LedgerIngestStateStore(ledger_conn)
    flaky = _FlakySink()

    assert adapter.poll(state, flaky) == 0  # emit failed; nothing counted
    # Cursor did NOT advance past the failed record, so the retry re-reads it.
    assert adapter.poll(state, flaky) == 1


def test_adapter_ingests_subagent_files_too(tmp_path, ledger_conn):
    """Subagent transcripts (<session>/subagents/agent-*.jsonl) are matched by the
    same recursive glob and ingested as their own raw events — the ledger's
    atomic unit is a usage_event, not an aggregated turn."""
    project_dir = tmp_path / "-proj"
    project_dir.mkdir()
    session_file = project_dir / "sess-5.jsonl"
    _write_session(
        session_file,
        [
            {
                "type": "user",
                "promptId": "p1",
                "isMeta": False,
                "sessionId": "sess-5",
                "cwd": "/x",
                "timestamp": "2026-07-01T00:00:00Z",
                "message": {"content": "go"},
            },
            {
                "type": "assistant",
                "requestId": "r1",
                "uuid": "u1",
                "sessionId": "sess-5",
                "cwd": "/x",
                "timestamp": "2026-07-01T00:00:01Z",
                "message": {
                    "model": "claude-sonnet-4-20250514",
                    "usage": {"input_tokens": 100, "output_tokens": 50},
                },
            },
        ],
    )
    subagent_dir = project_dir / "sess-5" / "subagents"
    subagent_dir.mkdir(parents=True)
    _write_session(
        subagent_dir / "agent-1.jsonl",
        [
            {
                "type": "assistant",
                "promptId": "p1",
                "agentId": "a1",
                "timestamp": "2026-07-01T00:00:02Z",
                "message": {
                    "model": "claude-haiku-4-5-20251001",
                    "usage": {"input_tokens": 500, "output_tokens": 100},
                },
            },
        ],
    )
    adapter = ClaudeCodeAdapter(claude_dir=tmp_path)
    sink = _CollectingSink()
    state = LedgerIngestStateStore(ledger_conn)
    n = adapter.poll(state, sink)
    # the adapter emits per-message events; the subagent message is its own event
    assert n == 2
    models = {e.model for e in sink.events}
    assert "claude-haiku-4-5-20251001" in models


def test_identifier_less_records_get_stable_distinct_ids(tmp_path, ledger_conn):
    """Missing requestId/uuid records must not collapse onto one empty key."""
    from forecost.ledger.sink import SyncLedgerSink

    project_dir = tmp_path / "-proj"
    project_dir.mkdir()
    records = [
        {
            "type": "assistant",
            "sessionId": "sess-anon",
            "agentId": "agent-1",
            "promptId": "prompt-1",
            "timestamp": f"2026-07-01T00:00:0{second}Z",
            "message": {
                "model": "claude-haiku-4-5-20251001",
                "usage": {"input_tokens": 100 + second, "output_tokens": 20},
            },
        }
        for second in (1, 2)
    ]
    _write_session(project_dir / "sess-anon.jsonl", records)
    adapter = ClaudeCodeAdapter(claude_dir=tmp_path)
    sink = SyncLedgerSink(ledger_path=None)
    sink._conn = ledger_conn

    assert adapter.poll(LedgerIngestStateStore(ledger_conn), sink) == 2
    ids = [row["event_uid"] for row in ledger_conn.execute("SELECT event_uid FROM usage_events")]
    assert len(set(ids)) == 2
    assert all(event_id.startswith("event:") for event_id in ids)
    assert all(event_id != content_free_identifier("event", "cc:uuid:") for event_id in ids)


def test_identifier_less_repeated_content_blocks_still_dedupe(tmp_path, ledger_conn):
    from forecost.ledger.sink import SyncLedgerSink

    project_dir = tmp_path / "-proj"
    project_dir.mkdir()
    record = {
        "type": "assistant",
        "sessionId": "sess-anon-blocks",
        "agentId": "agent-1",
        "promptId": "prompt-1",
        "timestamp": "2026-07-01T00:00:01Z",
        "message": {
            "model": "claude-haiku-4-5-20251001",
            "usage": {"input_tokens": 100, "output_tokens": 20},
        },
    }
    _write_session(project_dir / "sess-anon-blocks.jsonl", [record, record])
    adapter = ClaudeCodeAdapter(claude_dir=tmp_path)
    sink = SyncLedgerSink(ledger_path=None)
    sink._conn = ledger_conn

    assert adapter.poll(LedgerIngestStateStore(ledger_conn), sink) == 1
    assert ledger_conn.execute("SELECT COUNT(*) FROM usage_events").fetchone()[0] == 1


def test_prompt_identity_survives_incremental_poll_boundary(tmp_path, ledger_conn):
    """An assistant append inherits the prompt consumed by the previous poll."""
    project_dir = tmp_path / "-proj"
    project_dir.mkdir()
    session_file = project_dir / "sess-incremental.jsonl"
    _write_session(
        session_file,
        [
            {
                "type": "user",
                "promptId": "persisted-prompt",
                "timestamp": "2026-07-01T00:00:00Z",
                "message": {"content": "never persisted"},
            }
        ],
    )
    adapter = ClaudeCodeAdapter(claude_dir=tmp_path)
    state = LedgerIngestStateStore(ledger_conn)
    sink = _CollectingSink()
    assert adapter.poll(state, sink) == 0

    with open(session_file, "a", encoding="utf-8") as transcript:
        transcript.write(
            json.dumps(
                {
                    "type": "assistant",
                    "requestId": "incremental-request",
                    "sessionId": "sess-incremental",
                    "timestamp": "2026-07-01T00:00:01Z",
                    "message": {
                        "model": "claude-sonnet-4-20250514",
                        "usage": {"input_tokens": 10, "output_tokens": 5},
                    },
                }
            )
            + "\n"
        )

    assert adapter.poll(state, sink) == 1
    assert sink.events[0].run_id == content_free_identifier("run", "persisted-prompt")


def test_cursor_keys_are_keyed_distinct_and_cover_usage_and_causal_state(tmp_path, ledger_conn):
    left = tmp_path / "workspace-left"
    right = tmp_path / "workspace-right"
    left.mkdir()
    right.mkdir()
    record = {
        "type": "assistant",
        "requestId": "cursor-key-test",
        "uuid": "cursor-key-test",
        "sessionId": "cursor-session",
        "promptId": "cursor-prompt",
        "timestamp": "2026-07-01T00:00:00Z",
        "message": {
            "model": "claude-sonnet-4-20250514",
            "usage": {"input_tokens": 10, "output_tokens": 5},
        },
    }
    first = left / "same-name.jsonl"
    second = right / "same-name.jsonl"
    _write_session(first, [record])
    _write_session(second, [{**record, "requestId": "cursor-key-test-2"}])
    state = LedgerIngestStateStore(ledger_conn)
    adapter = ClaudeCodeAdapter(claude_dir=tmp_path)

    assert adapter.poll(state, _CollectingSink()) == 2
    assert ingest_causal_paths([first, second], state, ledger_conn) > 0

    rows = ledger_conn.execute(
        "SELECT source, cursor_key, cursor_val FROM ingest_state ORDER BY source, cursor_key"
    ).fetchall()
    assert len(rows) == 4
    assert len({str(row["cursor_key"]) for row in rows}) == 4
    for row in rows:
        assert str(row["cursor_key"]).startswith("cursor-hmac:v1:")
        assert str(first) not in str(row["cursor_key"])
        assert str(second) not in str(row["cursor_key"])
        assert "cursor-prompt" not in str(row["cursor_val"])


def test_boolean_cursor_offset_rewinds_instead_of_skipping_transcript(tmp_path, ledger_conn):
    transcript = tmp_path / "session.jsonl"
    _write_session(
        transcript,
        [
            {
                "type": "assistant",
                "requestId": "boolean-offset",
                "sessionId": "boolean-session",
                "timestamp": "2026-07-01T00:00:00Z",
                "message": {
                    "model": "claude-sonnet-4-20250514",
                    "usage": {"input_tokens": 10, "output_tokens": 5},
                },
            }
        ],
    )
    state = LedgerIngestStateStore(ledger_conn)
    key = _cursor_key("claude_code", str(transcript), installation_key())
    state.set("claude_code", key, json.dumps({"offset": True}))
    sink = _CollectingSink()

    assert ClaudeCodeAdapter(claude_dir=tmp_path).poll(state, sink) == 1
    assert [event.event_uid for event in sink.events] == ["cc:boolean-offset"]


def test_same_path_atomic_replacement_resets_cursor_and_ingests_new_record(tmp_path, ledger_conn):
    transcript = tmp_path / "session.jsonl"

    def record(request_id: str) -> dict[str, object]:
        return {
            "type": "assistant",
            "requestId": request_id,
            "sessionId": "replacement-session",
            "timestamp": "2026-07-01T00:00:00Z",
            "message": {
                "model": "claude-sonnet-4-20250514",
                "usage": {"input_tokens": 10, "output_tokens": 5},
            },
        }

    _write_session(transcript, [record("replacement-first")])
    state = LedgerIngestStateStore(ledger_conn)
    adapter = ClaudeCodeAdapter(claude_dir=tmp_path)
    first_sink = _CollectingSink()
    assert adapter.poll(state, first_sink) == 1

    replacement = tmp_path / "replacement.jsonl"
    _write_session(replacement, [record("replacement-second")])
    replacement.replace(transcript)
    second_sink = _CollectingSink()

    assert adapter.poll(state, second_sink) == 1
    assert [event.event_uid for event in second_sink.events] == ["cc:replacement-second"]


def test_same_inode_prefix_rewrite_resets_cursor(tmp_path, ledger_conn):
    transcript = tmp_path / "session.jsonl"
    first = {
        "type": "assistant",
        "requestId": "same-inode-first",
        "sessionId": "same-inode-session",
        "timestamp": "2026-07-01T00:00:00Z",
        "message": {
            "model": "claude-sonnet-4-20250514",
            "usage": {"input_tokens": 10, "output_tokens": 5},
        },
    }
    second = {**first, "requestId": "same-inode-other"}
    _write_session(transcript, [first])
    state = LedgerIngestStateStore(ledger_conn)
    adapter = ClaudeCodeAdapter(claude_dir=tmp_path)
    assert adapter.poll(state, _CollectingSink()) == 1

    # Rewrite in place to preserve the inode and keep the file at least as long
    # as the old cursor. The keyed prefix/boundary checkpoint must still reset.
    transcript.write_text(json.dumps(second) + "\n " * 20, encoding="utf-8")
    sink = _CollectingSink()

    assert adapter.poll(state, sink) == 1
    assert [event.event_uid for event in sink.events] == ["cc:same-inode-other"]


def test_same_inode_middle_rewrite_resets_full_prefix_cursor(tmp_path, ledger_conn):
    transcript = tmp_path / "long-session.jsonl"

    def record(index: int, label: str = "old") -> dict[str, object]:
        return {
            "type": "assistant",
            "requestId": f"middle-{label}-{index:03d}",
            "sessionId": "middle-rewrite-session",
            "timestamp": f"2026-07-01T00:00:{index % 60:02d}Z",
            "message": {
                "model": "claude-sonnet-4-20250514",
                "usage": {"input_tokens": 10, "output_tokens": 5},
            },
        }

    records = [record(index) for index in range(48)]
    _write_session(transcript, records)
    original_inode = transcript.stat().st_ino
    original_size = transcript.stat().st_size
    state = LedgerIngestStateStore(ledger_conn)
    adapter = ClaudeCodeAdapter(claude_dir=tmp_path)
    assert adapter.poll(state, _CollectingSink()) == 48

    records[24] = record(24, "new")
    _write_session(transcript, records)
    assert transcript.stat().st_ino == original_inode
    assert transcript.stat().st_size == original_size

    replay = _CollectingSink()
    assert adapter.poll(state, replay) == 48
    assert "cc:middle-new-024" in {event.event_uid for event in replay.events}


@pytest.mark.skipif(os.name == "nt", reason="Windows does not replace an open transcript")
def test_atomic_replacement_between_validation_and_usage_read_loses_no_prefix(
    tmp_path, ledger_conn, monkeypatch
):
    transcript = tmp_path / "race-session.jsonl"

    def record(request_id: str, second: int) -> dict[str, object]:
        return {
            "type": "assistant",
            "requestId": request_id,
            "sessionId": "race-session",
            "timestamp": f"2026-07-01T00:00:{second:02d}Z",
            "message": {
                "model": "claude-sonnet-4-20250514",
                "usage": {"input_tokens": 10, "output_tokens": 5},
            },
        }

    _write_session(transcript, [record("race-old", 0)])
    state = LedgerIngestStateStore(ledger_conn)
    adapter = ClaudeCodeAdapter(claude_dir=tmp_path)
    assert adapter.poll_paths([transcript], state, _CollectingSink()) == 1

    replacement = tmp_path / "race-replacement.jsonl"
    _write_session(replacement, [record("race-new-prefix", 1), record("race-new-tail", 2)])
    original_resume = claude_adapter._resume_cursor
    swapped = False

    def swap_after_validation(stream, cursor, identity_key):
        nonlocal swapped
        result = original_resume(stream, cursor, identity_key)
        offset = result[0]
        if result and offset > 0 and not swapped:
            replacement.replace(transcript)
            swapped = True
        return result

    monkeypatch.setattr(claude_adapter, "_resume_cursor", swap_after_validation)

    # The already-open descriptor finishes the old file. The following poll
    # detects the new inode, rewinds, and ingests the complete replacement.
    assert adapter.poll_paths([transcript], state, _CollectingSink()) == 0
    replay = _CollectingSink()
    assert adapter.poll_paths([transcript], state, replay) == 2
    assert [event.event_uid for event in replay.events] == [
        "cc:race-new-prefix",
        "cc:race-new-tail",
    ]


@pytest.mark.skipif(os.name == "nt", reason="Windows does not replace an open transcript")
def test_atomic_replacement_between_validation_and_causal_read_loses_no_prefix(
    tmp_path, ledger_conn, monkeypatch
):
    transcript = tmp_path / "causal-race-session.jsonl"

    def record(request_id: str, second: int) -> dict[str, object]:
        return {
            "type": "assistant",
            "requestId": request_id,
            "uuid": request_id,
            "sessionId": "causal-race-session",
            "promptId": "causal-race-prompt",
            "timestamp": f"2026-07-01T00:00:{second:02d}Z",
            "message": {
                "model": "claude-sonnet-4-20250514",
                "usage": {"input_tokens": 10, "output_tokens": 5},
            },
        }

    _write_session(transcript, [record("causal-race-old", 0)])
    state = LedgerIngestStateStore(ledger_conn)
    assert ingest_causal_paths([transcript], state, ledger_conn) == 3

    replacement = tmp_path / "causal-race-replacement.jsonl"
    _write_session(
        replacement,
        [record("causal-race-new-prefix", 1), record("causal-race-new-tail", 2)],
    )
    original_resume = claude_adapter._resume_cursor
    swapped = False

    def swap_after_validation(stream, cursor, identity_key):
        nonlocal swapped
        result = original_resume(stream, cursor, identity_key)
        offset = result[0]
        if result and offset > 0 and not swapped:
            replacement.replace(transcript)
            swapped = True
        return result

    monkeypatch.setattr(claude_adapter, "_resume_cursor", swap_after_validation)

    assert ingest_causal_paths([transcript], state, ledger_conn) == 0
    assert ingest_causal_paths([transcript], state, ledger_conn) == 6


@pytest.mark.parametrize("causal", [False, True], ids=["usage", "causal"])
def test_fresh_cursor_attests_to_exact_bytes_processed(tmp_path, ledger_conn, monkeypatch, causal):
    transcript = tmp_path / f"fresh-{causal}.jsonl"

    def record(request_id: str) -> dict[str, object]:
        return {
            "type": "assistant",
            "requestId": request_id,
            "uuid": request_id,
            "sessionId": "fresh-attestation-session",
            "promptId": "fresh-attestation-prompt",
            "timestamp": "2026-07-01T00:00:00Z",
            "message": {
                "model": "claude-sonnet-4-20250514",
                "usage": {"input_tokens": 10, "output_tokens": 5},
            },
        }

    old = record("fresh-request-old")
    new = record("fresh-request-new")
    _write_session(transcript, [old])
    original_inode = transcript.stat().st_ino
    original_size = transcript.stat().st_size
    state = LedgerIngestStateStore(ledger_conn)
    adapter = ClaudeCodeAdapter(claude_dir=tmp_path)
    original_verify = claude_adapter._verified_processed_checkpoint
    mutated = False

    def mutate_before_verify(stream, offset, identity_key, processed_digest):
        nonlocal mutated
        if not mutated:
            _write_session(transcript, [new])
            mutated = True
        return original_verify(stream, offset, identity_key, processed_digest)

    monkeypatch.setattr(
        claude_adapter,
        "_verified_processed_checkpoint",
        mutate_before_verify,
    )

    expected = 3 if causal else 1
    if causal:
        first = ingest_causal_paths([transcript], state, ledger_conn)
        second = ingest_causal_paths([transcript], state, ledger_conn)
        third = ingest_causal_paths([transcript], state, ledger_conn)
    else:
        first_sink = _CollectingSink()
        second_sink = _CollectingSink()
        first = adapter.poll_paths([transcript], state, first_sink)
        second = adapter.poll_paths([transcript], state, second_sink)
        third = adapter.poll_paths([transcript], state, _CollectingSink())
        assert [event.event_uid for event in first_sink.events] == ["cc:fresh-request-old"]
        assert [event.event_uid for event in second_sink.events] == ["cc:fresh-request-new"]

    assert (first, second, third) == (expected, expected, 0)
    assert transcript.stat().st_ino == original_inode
    assert transcript.stat().st_size == original_size


@pytest.mark.parametrize("causal", [False, True], ids=["usage", "causal"])
def test_resumed_cursor_attests_to_exact_new_bytes_processed(
    tmp_path, ledger_conn, monkeypatch, causal
):
    transcript = tmp_path / f"resumed-{causal}.jsonl"

    def record(request_id: str, second: int) -> dict[str, object]:
        return {
            "type": "assistant",
            "requestId": request_id,
            "uuid": request_id,
            "sessionId": "resumed-attestation-session",
            "promptId": "resumed-attestation-prompt",
            "timestamp": f"2026-07-01T00:00:{second:02d}Z",
            "message": {
                "model": "claude-sonnet-4-20250514",
                "usage": {"input_tokens": 10, "output_tokens": 5},
            },
        }

    base = record("resumed-base-000", 0)
    old = record("resumed-request-old", 1)
    new = record("resumed-request-new", 1)
    _write_session(transcript, [base])
    state = LedgerIngestStateStore(ledger_conn)
    adapter = ClaudeCodeAdapter(claude_dir=tmp_path)
    if causal:
        assert ingest_causal_paths([transcript], state, ledger_conn) == 3
    else:
        assert adapter.poll_paths([transcript], state, _CollectingSink()) == 1
    _write_session(transcript, [base, old])
    original_inode = transcript.stat().st_ino
    original_size = transcript.stat().st_size
    original_verify = claude_adapter._verified_processed_checkpoint
    mutated = False

    def mutate_before_verify(stream, offset, identity_key, processed_digest):
        nonlocal mutated
        if not mutated:
            _write_session(transcript, [base, new])
            mutated = True
        return original_verify(stream, offset, identity_key, processed_digest)

    monkeypatch.setattr(
        claude_adapter,
        "_verified_processed_checkpoint",
        mutate_before_verify,
    )

    expected = 3 if causal else 1
    if causal:
        first = ingest_causal_paths([transcript], state, ledger_conn)
        second = ingest_causal_paths([transcript], state, ledger_conn)
        third = ingest_causal_paths([transcript], state, ledger_conn)
    else:
        first_sink = _CollectingSink()
        second_sink = _CollectingSink()
        first = adapter.poll_paths([transcript], state, first_sink)
        second = adapter.poll_paths([transcript], state, second_sink)
        third = adapter.poll_paths([transcript], state, _CollectingSink())
        assert [event.event_uid for event in first_sink.events] == ["cc:resumed-request-old"]
        assert [event.event_uid for event in second_sink.events] == ["cc:resumed-request-new"]

    assert (first, second, third) == (expected, expected, 0)
    assert transcript.stat().st_ino == original_inode
    assert transcript.stat().st_size == original_size


def test_legacy_raw_cursor_migration_rewinds_conflict_and_removes_paths(tmp_path, ledger_conn):
    project = tmp_path / "workspace"
    project.mkdir()
    transcript = project / "session.jsonl"
    first = {
        "type": "user",
        "promptId": "legacy-secret-prompt",
        "timestamp": "2026-07-01T00:00:00Z",
        "message": {"content": "not persisted"},
    }
    second = {
        "type": "assistant",
        "requestId": "after-legacy-offset",
        "sessionId": "legacy-session",
        "timestamp": "2026-07-01T00:00:01Z",
        "message": {
            "model": "claude-sonnet-4-20250514",
            "usage": {"input_tokens": 10, "output_tokens": 5},
        },
    }
    first_line = json.dumps(first) + "\n"
    transcript.write_text(first_line + json.dumps(second) + "\n", encoding="utf-8")
    state = LedgerIngestStateStore(ledger_conn)
    source = ClaudeCodeAdapter.name
    opaque = _cursor_key(source, str(transcript), installation_key())
    now = "2026-07-01T00:00:00+00:00"
    ledger_conn.executemany(
        "INSERT INTO ingest_state (source, cursor_key, cursor_val, updated_at) VALUES (?,?,?,?)",
        [
            (
                source,
                str(transcript),
                json.dumps(
                    {"offset": len(first_line.encode()), "prompt_id": "legacy-secret-prompt"}
                ),
                now,
            ),
            (
                source,
                opaque,
                json.dumps({"offset": transcript.stat().st_size, "prompt_id": "newer-prompt"}),
                now,
            ),
        ],
    )
    ledger_conn.commit()

    sink = _CollectingSink()
    assert ClaudeCodeAdapter(claude_dir=tmp_path).poll(state, sink) == 1
    assert [event.event_uid for event in sink.events] == ["cc:after-legacy-offset"]
    rows = ledger_conn.execute(
        "SELECT cursor_key, cursor_val FROM ingest_state WHERE source = ?", (source,)
    ).fetchall()
    assert len(rows) == 1
    assert rows[0]["cursor_key"] == opaque
    assert str(transcript) not in rows[0]["cursor_key"]
    assert "legacy-secret-prompt" not in rows[0]["cursor_val"]
    assert "newer-prompt" not in rows[0]["cursor_val"]
    database_path = next(
        row[2] for row in ledger_conn.execute("PRAGMA database_list") if row[1] == "main"
    )
    for suffix in ("", "-wal", "-shm"):
        candidate = Path(str(database_path) + suffix)
        if candidate.is_file():
            persisted = candidate.read_bytes()
            assert str(transcript).encode() not in persisted
            assert b"legacy-secret-prompt" not in persisted
            assert b"newer-prompt" not in persisted


def test_cursor_migration_collision_rolls_back_without_conflating_rows(ledger_conn):
    state = LedgerIngestStateStore(ledger_conn)
    now = "2026-07-01T00:00:00+00:00"
    ledger_conn.executemany(
        "INSERT INTO ingest_state (source, cursor_key, cursor_val, updated_at) VALUES (?,?,?,?)",
        [
            ("claude_code", "/workspace-a/same.jsonl", '{"offset":10}', now),
            ("claude_code", "/workspace-b/same.jsonl", '{"offset":20}', now),
        ],
    )
    ledger_conn.commit()

    with pytest.raises(RuntimeError, match="identity collision"):
        state.migrate_legacy_keys(
            "claude_code",
            lambda _old: "cursor-hmac:v1:" + "0" * 64,
            lambda current, legacy: current or legacy,
        )

    keys = {
        row["cursor_key"]
        for row in ledger_conn.execute(
            "SELECT cursor_key FROM ingest_state WHERE source='claude_code'"
        )
    }
    assert keys == {"/workspace-a/same.jsonl", "/workspace-b/same.jsonl"}


def test_legacy_cursor_migrates_even_when_transcript_tree_is_missing(tmp_path, ledger_conn):
    state = LedgerIngestStateStore(ledger_conn)
    raw_path = "/deleted/private/workspace/session.jsonl"
    for source in ("claude_code", "claude_code_causal"):
        state.set(
            source,
            raw_path,
            json.dumps({"offset": 123, "prompt_id": "private-run-id"}),
        )

    adapter = ClaudeCodeAdapter(claude_dir=tmp_path / "does-not-exist")
    assert adapter.poll(state, _CollectingSink()) == 0
    assert ingest_causal_paths([], state, ledger_conn) == 0

    rows = ledger_conn.execute(
        "SELECT source, cursor_key, cursor_val FROM ingest_state "
        "WHERE source IN ('claude_code', 'claude_code_causal')"
    ).fetchall()
    assert {row["source"] for row in rows} == {"claude_code", "claude_code_causal"}
    for row in rows:
        assert row["cursor_key"].startswith("cursor-hmac:v1:")
        assert raw_path not in row["cursor_key"]
        assert "private-run-id" not in row["cursor_val"]
        assert json.loads(row["cursor_val"])["offset"] == 123
