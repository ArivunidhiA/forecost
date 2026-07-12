"""Hook handler implementations: preflight, gate, reconcile, session-start.

Each function takes a parsed stdin payload dict and returns a dict to be
JSON-encoded to stdout. Callers (fastpath.py) are responsible for the
exit-0-on-any-exception contract; handlers here may raise freely and let the
caller enforce fail-open, keeping this module's logic legible and testable.
"""

from __future__ import annotations

from pathlib import Path

from forecost.adapters.claude_code import ClaudeCodeAdapter
from forecost.estimate.engine import estimate_cost, record_estimate
from forecost.estimate.flags import scan_prompt
from forecost.estimate.taxonomy import classify
from forecost.estimate.types import TaskContext
from forecost.ledger.db import get_ledger_db
from forecost.ledger.sink import DefaultLedgerSink, _get_or_create_session, _get_or_create_workspace
from forecost.ledger.state_store import LedgerIngestStateStore
from forecost.policy.engine import evaluate
from forecost.policy.rules import load_policy_file


def _policy_path(cwd: str | None) -> Path:
    if cwd:
        candidate = Path(cwd) / ".forecost.toml"
        if candidate.exists():
            return candidate
    from forecost.core.paths import forecost_home

    return forecost_home() / "policy.toml"


def _resolve_ids(conn, cwd: str, session_id_raw: str | None) -> tuple[int | None, int | None]:
    """Resolve (workspace_id, session_id) DB ids, creating rows as needed."""
    workspace_id = _get_or_create_workspace(conn, cwd) if cwd else None
    session_db_id = None
    if session_id_raw:
        session_db_id = _get_or_create_session(
            conn, session_id_raw, workspace_id, "claude-code", _now_iso()
        )
    return workspace_id, session_db_id


def _evaluate_policy(conn, cwd: str, workspace_id, session_db_id):
    policy = load_policy_file(_policy_path(cwd))
    return evaluate(
        conn, policy, workspace_id=workspace_id, session_id=session_db_id, agent="claude-code"
    )


def handle_session_start(payload: dict) -> dict:
    conn = get_ledger_db()
    cwd = payload.get("cwd", "")
    session_id_raw = payload.get("session_id")
    _resolve_ids(conn, cwd, session_id_raw)
    return {}


def _preflight_context(category: str, flags, decision) -> dict:
    """Product law L2 (BASEMENT.md): silence below threshold. Render context only
    when there is something worth saying — a fan-out-class task, a static fact
    (scope maximizer / sensitive path), or a budget warning — never on every
    cheap interactive turn (the 93%-approval-rate habituation finding)."""
    render_threshold_met = (
        category == "fanout-batch" or bool(flags) or decision.action in ("warn", "ask")
    )
    if not render_threshold_met:
        return {}

    context_lines = [f"forecost: task class '{category}'"]
    if flags:
        context_lines.append("facts: " + "; ".join(f.fact for f in flags))
    if decision.action in ("warn", "ask"):
        context_lines.append(f"budget: {decision.reason}")
    return {
        "hookSpecificOutput": {
            "hookEventName": "UserPromptSubmit",
            "additionalContext": " | ".join(context_lines),
        }
    }


def handle_preflight(payload: dict) -> dict:
    """UserPromptSubmit: classify, featurize, estimate (shadow), evaluate policy."""
    prompt = payload.get("prompt", "")
    cwd = payload.get("cwd", "")
    session_id_raw = payload.get("session_id")

    category = classify(prompt)
    flags = scan_prompt(prompt)

    conn = get_ledger_db()
    task = TaskContext(prompt_text=prompt, cwd=cwd)
    estimate = estimate_cost(conn, task, category)

    workspace_id, session_db_id = _resolve_ids(conn, cwd, session_id_raw)
    run_id = payload.get("prompt_id") or session_id_raw
    record_estimate(conn, estimate, session_db_id, workspace_id, run_id, shadow=True)

    decision = _evaluate_policy(conn, cwd, workspace_id, session_db_id)
    if decision.action == "deny":
        return {"decision": "block", "reason": decision.reason}

    return _preflight_context(category, flags, decision)


def handle_gate(payload: dict) -> dict:
    """PreToolUse: cheap budget check against cached ledger aggregates."""
    cwd = payload.get("cwd", "")
    session_id_raw = payload.get("session_id")
    conn = get_ledger_db()
    workspace_id, session_db_id = _resolve_ids(conn, cwd, session_id_raw)
    decision = _evaluate_policy(conn, cwd, workspace_id, session_db_id)

    if decision.action in ("deny", "ask"):
        return {
            "hookSpecificOutput": {
                "hookEventName": "PreToolUse",
                "permissionDecision": decision.action,
                "permissionDecisionReason": decision.reason,
            }
        }
    return {}


def handle_reconcile(payload: dict) -> dict:
    """Stop/SessionEnd: ingest the transcript delta, then score pending estimates.

    Runs async (hooks.json marks it async) so latency is irrelevant here; this is
    where the calibration record accrues without the user doing anything.
    """
    from forecost.estimate.calibration import reconcile_estimates

    transcript_path = payload.get("transcript_path")
    claude_dir = Path(transcript_path).parent.parent if transcript_path else None
    adapter = ClaudeCodeAdapter(claude_dir=claude_dir) if claude_dir else ClaudeCodeAdapter()
    conn = get_ledger_db()
    state = LedgerIngestStateStore(conn)
    sink = DefaultLedgerSink()
    n = adapter.poll(state, sink)
    sink.flush(timeout=1.0)
    scored = reconcile_estimates(conn)
    return {"ingested": n, "estimates_reconciled": scored}


def _now_iso() -> str:
    from datetime import datetime, timezone

    return datetime.now(timezone.utc).isoformat()
