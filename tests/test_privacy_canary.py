"""The canary test: proves the content-free ledger invariant (BASEMENT.md L5).

L5 forbids persisting PROMPT TEXT, COMPLETION TEXT, and FILE CONTENTS/tool
output. It does NOT forbid storing workspace/project paths locally — a
workspace's root_path is legitimate operational metadata (needed to scope
budgets and reports per project) and is stored directly by design; only its
HMAC leaves the machine in the team-sync tier (round3-architecture.md §3.3,
§8.3). So this test uses an ordinary cwd and plants the sentinel ONLY in
genuine content fields — the user's prompt text, a tool_use file_path
argument, and tool_result output — then asserts the sentinel appears NOWHERE
under ~/.forecost/ after ingestion, estimation, and hook processing. This is
the single test the product's entire trust story rests on — it must run in CI
forever and must never be weakened.
"""

import json
import subprocess
import sys
from pathlib import Path

CANARY = "CANARY-9f2e-DO-NOT-PERSIST"
ORDINARY_CWD = "/tmp/canary-test-project"  # a path is expected metadata, not "content"


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
"""
    proc = subprocess.run(  # noqa: S603 - fixed interpreter + inline script, not user input
        [sys.executable, "-c", script], capture_output=True, text=True, env=env, timeout=15
    )
    assert proc.returncode == 0, proc.stderr

    # The canary check: grep every file under the forecost home for the sentinel.
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
        if CANARY.encode() in content:
            offenders.append(str(path))

    assert offenders == [], f"CANARY content leaked into: {offenders}"
