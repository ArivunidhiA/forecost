"""Owned-state privacy regression canary for the content-minimizing boundary.

L5 forbids persisting prompt text, completion text, file contents/tool output,
and raw workspace paths. Workspace identity is pseudonymized at persistence
boundaries. This test plants sentinels in genuine content/path fields and then
checks SQL plus every file under a temporary Forecost home after ingestion,
estimation, outbox/spool writing, and hook processing. It cannot prove absence
from host backups, filesystem remnants, or future unexercised integrations.
"""

import json
import sqlite3
import subprocess
import sys
from pathlib import Path

CANARY = "CANARY-9f2e-DO-NOT-PERSIST"
ORDINARY_CWD = "/tmp/canary-test-project"


def _write_canary_session(project_dir: Path):
    project_dir.mkdir(parents=True, exist_ok=True)
    session_file = project_dir / "canary-session.jsonl"
    records = [
        {
            "type": "user",
            "promptId": "p1",
            "isMeta": False,
            "sessionId": "canary-session",
            "cwd": ORDINARY_CWD,
            "timestamp": "2026-07-01T00:00:00Z",
            "message": {
                "content": f"refactor the entire auth module, secret token {CANARY}-abc123"
            },
        },
        {
            "type": "assistant",
            "requestId": "req-1",
            "uuid": "u1",
            "sessionId": "canary-session",
            "cwd": ORDINARY_CWD,
            "timestamp": "2026-07-01T00:00:05Z",
            "message": {
                "model": "claude-sonnet-4-20250514",
                "usage": {"input_tokens": 1000, "output_tokens": 200},
                "content": [
                    {
                        "type": "tool_use",
                        "name": "Edit",
                        "input": {"file_path": f"{ORDINARY_CWD}/src/{CANARY}_secret.py"},
                    }
                ],
            },
        },
        {
            "type": "user",
            "sessionId": "canary-session",
            "timestamp": "2026-07-01T00:00:06Z",
            "message": {
                "content": [
                    {
                        "type": "tool_result",
                        "is_error": True,
                        "content": (
                            f"Error: could not find {CANARY}-file.py, "
                            f"traceback: {CANARY}-stack-trace"
                        ),
                    }
                ]
            },
        },
    ]
    with open(session_file, "w") as f:
        for rec in records:
            f.write(json.dumps(rec) + "\n")
    return session_file


def test_canary_content_never_reaches_disk(tmp_path):
    fc_home = tmp_path / "fc"  # FORECOST_HOME — the .forecost dir itself
    claude_dir = tmp_path / "claude_projects"
    _write_canary_session(claude_dir / "-tmp-canary-project")

    # FORECOST_HOME redirects the ledger on every OS (HOME is POSIX-only for Path.home()).
    env = {**__import__("os").environ, "FORECOST_HOME": str(fc_home)}

    # Run ingestion via the actual ClaudeCodeAdapter, isolated to a tmp forecost
    # home, mirroring what the `stop` hook does after a real session.
    script = f"""
import sys, os
sys.path.insert(0, {str(Path(__file__).resolve().parents[1])!r})
os.environ['FORECOST_HOME'] = {str(fc_home)!r}
from pathlib import Path
from forecost.ledger.db import get_ledger_db
from forecost.ledger.sink import SyncLedgerSink
from forecost.ledger.state_store import LedgerIngestStateStore
from forecost.adapters.claude_code import ClaudeCodeAdapter
from forecost.estimate.taxonomy import classify
from forecost.estimate.flags import scan_prompt
from forecost.estimate.engine import estimate_cost, record_estimate
from forecost.estimate.types import TaskContext
from forecost.adapters.base import PostingSpec, UsageEvent, normalize_usage_event
from forecost.adapters.outbox import DurableEventOutbox
from forecost.core.errlog import log_error
from forecost.hooks.state import append_settlement_marker, record_heartbeat
from forecost.ledger.writer import _spill_batch
from datetime import datetime, timezone

conn = get_ledger_db()
state = LedgerIngestStateStore(conn)
sink = SyncLedgerSink()
adapter = ClaudeCodeAdapter(claude_dir=Path({str(claude_dir)!r}))
n = adapter.poll(state, sink)
print('ingested', n)

# Also exercise the estimator + static flags with the live (in-memory-only) prompt.
prompt_text = "refactor the entire auth module, secret token {CANARY}-abc123"
task = TaskContext(prompt_text=prompt_text, cwd={ORDINARY_CWD!r})
cat = classify(task.prompt_text)
flags = scan_prompt(task.prompt_text)
est = estimate_cost(conn, task, cat)
record_estimate(conn, est, None, None, "canary-run", shadow=True)

# Exercise every Forecost-owned persistence family with hostile-looking path
# and content values.  Each production boundary must normalize/fingerprint
# before it writes.
raw_event = UsageEvent(
    event_uid="{CANARY}-event",
    ts=datetime(2026, 7, 1, tzinfo=timezone.utc),
    source="litellm",
    model="gpt-4o",
    session_uid="{CANARY}-session",
    run_id="{CANARY}-run",
    workspace_path={ORDINARY_CWD!r},
    tokens_in=1,
)
normalized = normalize_usage_event(raw_event)
outbox = DurableEventOutbox(Path({str(fc_home)!r}) / "outbox" / "litellm.jsonl")
assert outbox.enqueue(raw_event)
_spill_batch(
    Path({str(fc_home)!r}) / "recovery.jsonl",
    [(normalized, [PostingSpec("USD", 0.01, "pricing_table", "synthetic-plan/v1")])],
)
record_heartbeat(
    "unknown-{CANARY}",
    state="bad-{CANARY}",
    detail={f"{ORDINARY_CWD}/{CANARY}"!r},
)
append_settlement_marker({{"session_id": "{CANARY}-hook-session"}})
log_error(
    "unknown-{CANARY}",
    "arbitrary exception at {ORDINARY_CWD}/{CANARY}",
)
"""
    proc = subprocess.run(  # noqa: S603 - fixed interpreter + inline script, not user input
        [sys.executable, "-c", script], capture_output=True, text=True, env=env, timeout=15
    )
    assert proc.returncode == 0, proc.stderr

    # Direct SQL catches logical leaks even when SQLite's file encoding changes.
    connection = sqlite3.connect(fc_home / "ledger.db")
    try:
        sql_text = []
        tables = [
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
            )
        ]
        for table in tables:
            quoted = table.replace('"', '""')
            for row in connection.execute(
                f'SELECT * FROM "{quoted}"'  # noqa: S608 - sourced from sqlite_master
            ):
                sql_text.extend(str(value) for value in row if value is not None)
        joined = "\n".join(sql_text)
        assert CANARY not in joined
        assert ORDINARY_CWD not in joined
        cursor_rows = connection.execute(
            "SELECT cursor_key, cursor_val FROM ingest_state "
            "WHERE source IN ('claude_code', 'claude_code_causal')"
        ).fetchall()
        assert cursor_rows
        assert all(str(key).startswith("cursor-hmac:v1:") for key, _value in cursor_rows)
    finally:
        connection.close()

    # Byte-scan every ledger, WAL, log, outbox, recovery spool, key, and hook
    # state file.  This is broader than SQL and guards future owned surfaces.
    forecost_dir = fc_home
    assert forecost_dir.exists(), "ledger directory was not created"
    offenders = []
    for path in forecost_dir.rglob("*"):
        if not path.is_file():
            continue
        try:
            content = path.read_bytes()
        except OSError:
            continue
        if CANARY.encode() in content or ORDINARY_CWD.encode() in content:
            offenders.append(str(path))

    assert offenders == [], f"raw content/path leaked into: {offenders}"
    assert (fc_home / "error.log").is_file()
    assert (fc_home / "hooks" / "heartbeat.json").is_file()
    assert (fc_home / "hooks" / "settlement-required.jsonl").is_file()
    assert (fc_home / "outbox" / "litellm.jsonl").is_file()
    assert list(fc_home.glob("recovery.*.jsonl"))
