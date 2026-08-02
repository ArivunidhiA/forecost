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


def _confirmed_hard_decision(rule: PolicyRule, spend: q.ScopeSpend) -> Decision | None:
    if rule.hard_limit is None:
        return None
    if spend.n_confident_events == 0:
        return None
    if spend.confident_total < rule.hard_limit:
        return None
    estimate_note = ""
    if spend.n_unpriced_events:
        estimate_note = (
            f"; excluded {rule.currency} {spend.unpriced_total:.2f} from unpriced models"
        )
    reason = (
        f"{rule.currency} confirmed spend {spend.confident_total:.2f} >= hard limit "
        f"{rule.hard_limit:.2f} (rule {rule.rule_id}{estimate_note})"
    )
    return Decision(rule.action, rule.rule_id, reason, spend.confident_total, rule.hard_limit)


def _unpriced_hard_warning(rule: PolicyRule, spend: q.ScopeSpend) -> Decision | None:
    if rule.hard_limit is None or spend.total < rule.hard_limit:
        return None
    # The configured hard boundary is crossed only when guessed prices are
    # counted. Surface the risk, but never block an agent on an invented rate.
    reason = (
        f"{rule.currency} estimated spend {spend.total:.2f} >= hard limit "
        f"{rule.hard_limit:.2f}, but {spend.unpriced_total:.2f} is based on "
        f"unpriced models; hard action suppressed (rule {rule.rule_id})"
    )
    return Decision("warn", rule.rule_id, reason, spend.total, rule.hard_limit)


def _soft_warning(rule: PolicyRule, spend: q.ScopeSpend) -> Decision | None:
    if rule.soft_limit is None or spend.total < rule.soft_limit:
        return None
    estimate_note = ""
    if spend.n_unpriced_events:
        estimate_note = f"; includes {spend.unpriced_total:.2f} from unpriced models"
    reason = (
        f"{rule.currency} estimated spend {spend.total:.2f} >= soft limit "
        f"{rule.soft_limit:.2f} (rule {rule.rule_id}{estimate_note})"
    )
    return Decision("warn", rule.rule_id, reason, spend.total, rule.soft_limit)


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
        spend = q.session_spend_breakdown(conn, session_id, rule.currency)
    else:
        since = _since_iso(rule.scope)
        spend = q.scope_spend(conn, rule.currency, since, workspace_id)

    for threshold_check in (_confirmed_hard_decision, _unpriced_hard_warning, _soft_warning):
        decision = threshold_check(rule, spend)
        if decision is not None:
            return decision
    return Decision("allow", rule.rule_id, "within limits", spend.total, rule.hard_limit)


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
