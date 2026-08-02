"""TOML policy rule schema: [[policy.rules]] blocks parsed into PolicyRule objects."""

from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Literal, cast

if sys.version_info >= (3, 11):
    import tomllib
else:  # pragma: no cover - py3.10 fallback
    import tomli as tomllib

Action = Literal["allow", "warn", "ask", "deny"]

# "run" is intentionally NOT supported: there is no reliable per-run spend key at
# policy-evaluation time (the preflight hook has no run/prompt id — see the
# calibration association note), so a run-scoped rule used to silently measure
# ALL-TIME spend and over-deny. Reject it at parse time instead. Use "session"
# for per-session caps; "day"/"week"/"month" for rolling windows.
VALID_SCOPES = {"session", "day", "week", "month"}
VALID_ACTIONS = {"warn", "ask", "deny"}


@dataclass(frozen=True)
class PolicyRule:
    rule_id: str
    scope: str
    currency: str
    soft_limit: float | None
    hard_limit: float | None
    action: Action
    applies_to: tuple[str, ...] = ()


@dataclass(frozen=True)
class PolicyConfig:
    rules: tuple[PolicyRule, ...]
    on_internal_error: str = "allow"
    decision_log: bool = True


def _validate_rule(raw: dict) -> PolicyRule:
    scope = raw.get("scope", "session")
    if scope not in VALID_SCOPES:
        raise ValueError(f"invalid policy scope: {scope!r}")
    action = raw.get("action", "warn")
    if action not in VALID_ACTIONS:
        raise ValueError(f"invalid policy action: {action!r}")
    return PolicyRule(
        rule_id=raw["id"],
        scope=scope,
        currency=raw.get("currency", "USD"),
        soft_limit=raw.get("soft_limit"),
        hard_limit=raw.get("hard_limit"),
        action=cast(Action, action),  # narrowed by the VALID_ACTIONS check above
        applies_to=tuple(raw.get("applies_to", ())),
    )


def parse_policy_toml(text: str) -> PolicyConfig:
    """Parse a .forecost.toml [[policy.rules]] block into a PolicyConfig.

    Raises ValueError on a malformed rule. The parser itself rejects
    on_internal_error='deny' outside CI mode, per BASEMENT.md law L4 — fail-open
    is opinionated by construction, not just a runtime default.
    """
    data = tomllib.loads(text)
    policy = data.get("policy", {})
    raw_rules = policy.get("rules", [])
    rules = tuple(_validate_rule(r) for r in raw_rules)

    on_internal_error = policy.get("on_internal_error", "allow")
    mode = policy.get("mode", "interactive")
    if on_internal_error == "deny" and mode != "ci":
        raise ValueError(
            "on_internal_error='deny' is only permitted when policy.mode='ci' "
            "(fail-open is required on interactive surfaces — BASEMENT.md law L4)"
        )

    return PolicyConfig(
        rules=rules,
        on_internal_error=on_internal_error,
        decision_log=policy.get("decision_log", True),
    )


def load_policy_file(path: Path) -> PolicyConfig:
    if not path.exists():
        return PolicyConfig(rules=())
    return parse_policy_toml(path.read_text(encoding="utf-8"))
