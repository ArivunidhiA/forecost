"""End-to-end smoke test of an INSTALLED forecost wheel using only the public CLI.

Run after `pip install dist/*.whl`:  python scripts/e2e_wheel_smoke.py
Uses a throwaway FORECOST_HOME, synthetic transcripts, and a planted privacy canary.
"""

# ruff: noqa: T201, S108, S607
from __future__ import annotations

import json
import os
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import time
from pathlib import Path

CANARY = "CANARY-SMOKE-9d41-DO-NOT-PERSIST"
CWD_CANARY = "smoke-secret-client"


def run(args: list[str], env: dict[str, str], expect: int = 0, stdin: str | None = None) -> str:
    done = subprocess.run(  # noqa: S603 - fixed argv, no shell
        args, env=env, input=stdin, capture_output=True, text=True, timeout=120, check=False
    )
    out = done.stdout + done.stderr
    if done.returncode != expect:
        sys.exit(f"FAIL {' '.join(args)} exit={done.returncode} (want {expect})\n{out}")
    return out


def check(condition: bool, message: str) -> None:
    if not condition:
        sys.exit(f"FAIL {message}")
    print(f"ok   {message}")


def transcript(root: Path) -> None:
    project = root / "projects" / "p1"
    project.mkdir(parents=True)
    records = [
        {
            "type": "user",
            "promptId": "p1",
            "isMeta": False,
            "sessionId": "s1",
            "cwd": f"/tmp/{CWD_CANARY}",
            "timestamp": "2026-10-01T00:00:00Z",
            "message": {"content": f"please do the thing {CANARY}"},
        },
        {
            "type": "assistant",
            "requestId": "r1",
            "uuid": "u1",
            "sessionId": "s1",
            "cwd": f"/tmp/{CWD_CANARY}",
            "timestamp": "2026-10-01T00:00:05Z",
            "message": {
                "model": "claude-sonnet-4-5",
                "content": [{"type": "text", "text": f"reply {CANARY}"}],
                "usage": {"input_tokens": 1200, "output_tokens": 340},
            },
        },
    ]
    (project / "s1.jsonl").write_text("\n".join(json.dumps(r) for r in records) + "\n")


def main() -> None:
    base = Path(tempfile.mkdtemp(prefix="forecost-smoke-"))
    home = base / "home"
    env = {**os.environ, "FORECOST_HOME": str(home), "CLAUDE_CONFIG_DIR": str(base / "claude")}
    try:
        transcript(base / "claude")
        check("forecost" in run(["forecost", "--version"], env), "version")
        run(["forecost", "doctor"], env)
        run(["forecost", "lab", "demo", "--ledger-path", str(base / "lab.db")], env)
        out = run(["forecost", "ingest", "--claude-dir", str(base / "claude" / "projects")], env)
        check("Ingested 1 new" in out, "ingest records one event")
        out = run(["forecost", "ingest", "--claude-dir", str(base / "claude" / "projects")], env)
        check("Ingested 0 new" in out, "ingest is idempotent")
        check("USD" in run(["forecost", "ledger", "status"], env), "ledger status")
        out = run(["forecost", "pricing-audit"], env)
        check("No unpriced models" in out, "mainstream Claude model is priced, not guessed")
        run(["forecost", "reconcile"], env)
        run(["forecost", "burn"], env)
        run(["forecost-hook", "prompt-submit"], env, stdin="garbage{")
        check(True, "hook fails open on malformed input")
        out = run(["forecost", "privacy", "verify"], env)
        check("canary absent" in out.lower(), "privacy verify")
        for path in home.rglob("*"):
            if path.is_file():
                blob = path.read_bytes()
                check(CANARY.encode() not in blob, f"no content canary in {path.name}")
                check(CWD_CANARY.encode() not in blob, f"no raw path canary in {path.name}")
        # Legacy store: SDK write must not persist raw path/metadata; migrate must work.
        proj = base / CWD_CANARY
        proj.mkdir()
        code = (
            "import os, forecost.tracker as t;"
            f"os.chdir({str(proj)!r});"
            "t.log_call('gpt-4o', 10, 5, metadata={'note': 'free form private text'})"
        )
        subprocess.run(
            ["forecost", "legacy", "init", "--days", "5", "--budget", "10"],
            env=env,
            cwd=proj,
            capture_output=True,
            text=True,
            timeout=120,
            check=True,
        )
        subprocess.run(  # noqa: S603
            [sys.executable, "-c", code], env=env, capture_output=True, timeout=120, check=True
        )
        time.sleep(3)
        db = sqlite3.connect(home / "costs.db")
        dump = "\n".join(db.iterdump())
        db.close()
        check("free form private text" not in dump, "legacy metadata content not persisted")
        check(str(proj) not in dump, "legacy raw project path not persisted")
        out = run(["forecost", "migrate"], env)
        check("Migrated" in out, "migrate succeeds with pseudonymized paths")
        out = run(["forecost", "migrate"], env)
        check("Migrated 0" in out, "migrate is idempotent")
        run(["forecost", "legacy", "scrub", "--check", "--yes"], env)
        print("E2E SMOKE PASSED")
    finally:
        shutil.rmtree(base, ignore_errors=True)


if __name__ == "__main__":
    main()
