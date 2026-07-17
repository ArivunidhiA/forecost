import json

from forecost.adapters.base import LedgerSink, UsageEvent
from forecost.adapters.claude_code import ClaudeCodeAdapter
from forecost.ledger.state_store import LedgerIngestStateStore


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
