"""Hook handler implementations: preflight, gate, reconcile, session-start.

Each function takes a parsed stdin payload dict and returns a dict to be
JSON-encoded to stdout. Callers (fastpath.py) are responsible for the
exit-0-on-any-exception contract; handlers here may raise freely and let the
caller enforce fail-open, keeping this module's logic legible and testable.
"""

from __future__ import annotations

import os
from pathlib import Path

from forecost.adapters.claude_code import ClaudeCodeAdapter
from forecost.core.errlog import log_error
from forecost.estimate.engine import estimate_cost, record_estimate
from forecost.estimate.flags import scan_prompt
from forecost.estimate.taxonomy import classify
from forecost.estimate.types import TaskContext
from forecost.ledger.db import get_ledger_db
from forecost.ledger.sink import SyncLedgerSink, _get_or_create_session, _get_or_create_workspace
from forecost.ledger.state_store import LedgerIngestStateStore
from forecost.policy.engine import evaluate
from forecost.policy.rules import load_policy_file


def _policy_path(cwd: str | None) -> Path:
    """Resolve which policy file governs enforcement for this hook.

    A repo-local ``<cwd>/.forecost.toml`` runs against whatever code you point the
    agent at — including untrusted clones — so it is NOT trusted for enforcement
    by default: a hostile repo could ship a rule that blocks your whole session,
    or quietly loosen the budget you set. The home policy always governs; opt in
    per-machine with ``FORECOST_TRUST_PROJECT_POLICY=1`` to honor project files.
    """
    from forecost.core.paths import forecost_home

    home_policy = forecost_home() / "policy.toml"
    if not cwd:
        return home_policy
    candidate = Path(cwd) / ".forecost.toml"
    if not candidate.exists():
        return home_policy
    trust = os.environ.get("FORECOST_TRUST_PROJECT_POLICY", "").strip().lower() in (
        "1",
        "true",
        "yes",
    )
    if trust:
        return candidate
    log_error(
        "hooks.policy",
        f"ignoring repo-local .forecost.toml at {cwd} for enforcement "
        "(set FORECOST_TRUST_PROJECT_POLICY=1 to trust project policy files)",
    )
    return home_policy


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
    # The estimate is associated with its run at reconcile time by session + time
    # window (calibration.py), not by run_id — the UserPromptSubmit payload has no
    # promptId to match the transcript's events. session_id is the real join key;
    # run_id is stored only as a human-readable reference.
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
    adapter = ClaudeCodeAdapter()
    conn = get_ledger_db()
    state = LedgerIngestStateStore(conn)
    # Synchronous sink: it shares this connection and commits each event before we
    # read it back, so reconcile_estimates below sees the just-ingested actuals.
    # (The hook is marked async in hooks.json, so the extra latency is irrelevant.)
    # This replaces the old async DefaultLedgerSink + sleep-based flush race.
    sink = SyncLedgerSink()
    if transcript_path:
        n = adapter.poll_paths(_session_transcript_paths(Path(transcript_path)), state, sink)
    else:
        n = adapter.poll(state, sink)
    sink.flush()
    scored = reconcile_estimates(conn)
    _shadow_guard_scan(conn, payload, transcript_path)
    return {"ingested": n, "estimates_reconciled": scored}


def _session_transcript_paths(primary: Path) -> list[Path]:
    """Return one session transcript plus only its own subagent transcripts."""
    paths = [primary]
    subagents = primary.with_suffix("") / "subagents"
    if subagents.is_dir():
        paths.extend(subagents.rglob("*.jsonl"))
    return paths


def _shadow_guard_scan(conn, payload: dict, transcript_path) -> None:
    """Compute the mid-run guard from the transcript tail and log a shadow flag
    if the backtested rule fires. Shadow-only (never surfaced) and best-effort —
    a guard failure must never affect the ingest/reconcile result."""
    if not transcript_path:
        return
    try:
        from forecost.estimate.guard import record_guard_flag, scan_transcript_errors

        evidence = scan_transcript_errors(str(transcript_path))
        if evidence is None:
            return
        session_id_raw = payload.get("session_id")
        _, session_db_id = _resolve_ids(conn, payload.get("cwd", ""), session_id_raw)
        record_guard_flag(conn, session_db_id, session_id_raw, evidence, shadow=True)
    except Exception as exc:  # nosec B110 - guard is telemetry; never break reconcile
        log_error("hooks.guard", f"shadow guard scan failed: {exc!r}")


def _now_iso() -> str:
    from datetime import datetime, timezone

    return datetime.now(timezone.utc).isoformat()
