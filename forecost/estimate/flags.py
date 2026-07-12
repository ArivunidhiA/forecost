"""Static, verifiable risk flags — never predictions, never risk verdicts.

BASEMENT.md law L6: the guard reports measured/verifiable facts in neutral
language ("plan touches auth/session.py"), never predictions ("may refactor
authentication") or coverage claims ("Risk: low"). This module is the
BUILDABLE-NOW half of round5-risk.md §2.4(b) — no LLM, no ML, pure static
analysis of the prompt text (which is used in-process only and never
persisted, per the content-free ledger invariant).
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from forecost.estimate.taxonomy import SCOPE_MAXIMIZER_RE, SENSITIVE_PATH_RE

FILE_MENTION_RE = re.compile(
    r"[\w./-]+\.(?:py|ts|tsx|js|jsx|md|json|toml|yaml|yml|sql|go|rs|java|rb|sh)\b"
)
NO_TEST_STEP_HINT_RE = re.compile(r"\btests?\b", re.IGNORECASE)


@dataclass(frozen=True)
class StaticFlag:
    flag_id: str
    fact: str  # neutral, verifiable statement — never a prediction or verdict


def scan_prompt(prompt: str) -> list[StaticFlag]:
    """Scan a live prompt (in-memory only) for statically-verifiable facts.

    Returns neutral facts, not risk verdicts: "mentions all/entire/every" is a
    fact about the text; it is not a claim that the task will fail or is risky.
    """
    flags: list[StaticFlag] = []

    if SCOPE_MAXIMIZER_RE.search(prompt):
        flags.append(
            StaticFlag(
                "scope_maximizer",
                "prompt contains a scope-broadening word (all/entire/every/throughout)",
            )
        )

    sensitive_matches = {m.group(0).lower() for m in SENSITIVE_PATH_RE.finditer(prompt)}
    if sensitive_matches:
        keywords = ", ".join(sorted(sensitive_matches))
        flags.append(
            StaticFlag(
                "sensitive_path_mention",
                f"prompt mentions sensitive-surface keyword(s): {keywords}",
            )
        )

    mentioned_files = FILE_MENTION_RE.findall(prompt)
    if len(mentioned_files) >= 5:
        flags.append(
            StaticFlag(
                "many_files_mentioned",
                f"prompt names {len(mentioned_files)} files explicitly",
            )
        )

    return flags


def plan_missing_test_step(plan_text: str) -> bool:
    """Deterministic check on a plan-mode artifact: does it mention testing at all?

    A fact about the plan's text, not a prediction about the outcome.
    """
    return not NO_TEST_STEP_HINT_RE.search(plan_text)
