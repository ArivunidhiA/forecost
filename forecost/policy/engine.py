"""Policy evaluation: (rules, ledger aggregates) -> Decision. Fail-open by law."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from forecost.core.errlog import log_error
from forecost.ledger import queries as q
from forecost.policy.rules import Action, PolicyConfig, PolicyRule

_ACTION_RANK: dict[Action, int] = {"allow": 0, "warn": 1, "ask": 2, "deny": 3}

# Rolling-window scopes only. "session" is handled separately via session_id
# (below); "run" is rejected at parse time (rules.py). A scope that is neither a
# window here nor "session" is a bug — _since_iso raises so evaluate() fails open.
_SCOPE_WINDOWS = {
    "day": timedelta(days=1),
    "week": timedelta(weeks=1),
    "month": timedelta(days=30),
}


@dataclass(frozen=True)
class Decision:
    action: Action
    rule_id: str | None
    reason: str
    measured: float | None = None
    limit: float | None = None


def _since_iso(scope: str) -> str:
    window = _SCOPE_WINDOWS.get(scope)
    if window is None:
        # Never the old silent 1970 lifetime window: an unknown scope is a bug,
        # and raising lets evaluate() fail open rather than measure all-time spend.
        raise ValueError(f"unsupported policy scope for time window: {scope!r}")
    return (datetime.now(timezone.utc) - window).isoformat()


def _evaluate_rule(
    conn: sqlite3.Connection, rule: PolicyRule, workspace_id: int | None, session_id: int | None
) -> Decision:
    if rule.scope == "session":
        if session_id is None:
            # No active session to measure against — cannot evaluate a session cap.
            # Fail open (allow) rather than fall through to all-time spend.
            return Decision(
                "allow", rule.rule_id, "session scope: no active session to measure", 0.0
            )
        measured = q.session_spend(conn, session_id, rule.currency)
    else:
        since = _since_iso(rule.scope)
        measured = q.scope_spend(conn, rule.currency, since, workspace_id).total

    if rule.hard_limit is not None and measured >= rule.hard_limit:
        reason = (
            f"{rule.currency} spend {measured:.2f} >= hard limit {rule.hard_limit:.2f} "
            f"(rule {rule.rule_id})"
        )
        return Decision(rule.action, rule.rule_id, reason, measured, rule.hard_limit)
    if rule.soft_limit is not None and measured >= rule.soft_limit:
        reason = (
            f"{rule.currency} spend {measured:.2f} >= soft limit {rule.soft_limit:.2f} "
            f"(rule {rule.rule_id})"
        )
        return Decision("warn", rule.rule_id, reason, measured, rule.soft_limit)
    return Decision("allow", rule.rule_id, "within limits", measured, rule.hard_limit)


def evaluate(
    conn: sqlite3.Connection,
    config: PolicyConfig,
    workspace_id: int | None = None,
    session_id: int | None = None,
    agent: str | None = None,
) -> Decision:
    """Evaluate all applicable rules; the strictest matching action wins.

    On ANY internal exception, returns Decision('allow', ...) — fail-open,
    per BASEMENT.md law L4. This function must never raise.
    """
    try:
        best: Decision | None = None
        for rule in config.rules:
            if rule.applies_to and agent not in rule.applies_to:
                continue
            d = _evaluate_rule(conn, rule, workspace_id, session_id)
            if best is None or _ACTION_RANK[d.action] > _ACTION_RANK[best.action]:
                best = d
        return best if best is not None else Decision("allow", None, "no rules configured")
    except Exception as exc:  # nosec B110 - fail-open is the product law, not a bug
        log_error("policy.engine", f"evaluate failed, failing open: {exc!r}")
        return Decision("allow", None, f"forecost internal error (fail-open): {exc!r}"[:200])
