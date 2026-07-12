"""Mid-run guard: rule-based stuck/error detection from the transcript tail.

Validated on real data this session: G-R3 passed with 66.7% retrospective
precision at a 2.0% flag rate (experiments/calib/VERDICT.md). Detection of the
present ("N consecutive tool failures"), never prediction of the future
("this will probably fail") — per BASEMENT.md law L6. Ships in shadow mode in
Phase 1 (log flags, no user-facing output); promoted to `ask` in Phase 2.
"""

from __future__ import annotations

from dataclasses import dataclass

CONSEC_ERROR_THRESHOLD = 3
TAIL_ERROR_MIN_COUNT = 2


@dataclass(frozen=True)
class GuardEvidence:
    rule_id: str
    fact: str  # neutral, measured — never "likely to fail"


def check_error_streak(consecutive_errors: int, total_errors_in_tail: int) -> GuardEvidence | None:
    """Same rule validated by the G-R3 backtest: >=3 consecutive tool errors,
    OR a tail error with >=2 total errors in the recent window."""
    if consecutive_errors >= CONSEC_ERROR_THRESHOLD:
        return GuardEvidence(
            "consec_tool_errors",
            f"{consecutive_errors} consecutive tool-call errors",
        )
    if total_errors_in_tail >= TAIL_ERROR_MIN_COUNT:
        return GuardEvidence(
            "tail_errors",
            f"{total_errors_in_tail} tool-call errors in the recent window",
        )
    return None


def check_spend_since_progress(
    usd_since_last_file_change: float, threshold_usd: float = 2.0
) -> GuardEvidence | None:
    """Neutral fact: spend has accumulated without a file change. Not a claim
    that the run will fail — just what the ledger and tool-call history show."""
    if usd_since_last_file_change >= threshold_usd:
        return GuardEvidence(
            "spend_without_progress",
            f"${usd_since_last_file_change:.2f} spent since the last file change",
        )
    return None
