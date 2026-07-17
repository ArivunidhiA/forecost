"""Mid-run guard: rule-based stuck/error detection from the transcript tail.

Validated on real data this session: G-R3 passed with 66.7% retrospective
precision at a 2.0% flag rate (experiments/calib/VERDICT.md). Detection of the
present ("N consecutive tool failures"), never prediction of the future
("this will probably fail") — per BASEMENT.md law L6. Ships in shadow mode in
Phase 1 (log flags, no user-facing output); promoted to `ask` in Phase 2.
"""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

CONSEC_ERROR_THRESHOLD = 3
TAIL_ERROR_MIN_COUNT = 2
_TAIL_WINDOW = 5  # size of the "recent window" the tail-error rule looks at


@dataclass(frozen=True)
class GuardEvidence:
    rule_id: str
    fact: str  # neutral, measured — never "likely to fail"


def check_error_streak(
    consecutive_errors: int,
    total_errors_in_tail: int,
    tail_has_error: bool = False,
) -> GuardEvidence | None:
    """The exact rule the G-R3 backtest validated (experiments/calib/backtest.py):
    flag if >=3 consecutive tool errors, OR the most recent window ends on an
    error AND has >=2 total errors. The ``tail_has_error`` conjunct is
    load-bearing — without it (the old bug) two early errors followed by clean
    progress would flag, inflating the flag rate above the measured 2%."""
    if consecutive_errors >= CONSEC_ERROR_THRESHOLD:
        return GuardEvidence(
            "consec_tool_errors",
            f"{consecutive_errors} consecutive tool-call errors",
        )
    if tail_has_error and total_errors_in_tail >= TAIL_ERROR_MIN_COUNT:
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


def scan_transcript_errors(transcript_path: str, max_records: int = 4000) -> GuardEvidence | None:
    """Compute the error-streak evidence from a Claude Code transcript's tool
    results, content-free. Reads only the boolean ``is_error`` on each tool_result
    (never the result text), so nothing about what the tools did reaches the guard.

    Returns the GuardEvidence if the backtested rule fires, else None. Never
    raises — a malformed transcript yields None."""
    try:
        p = Path(transcript_path)
        if not p.is_file():
            return None
        errors: list[bool] = []
        consec = 0
        max_consec = 0
        total = 0
        with open(p, "rb") as f:
            lines = f.readlines()[-max_records:]
        for raw in lines:
            try:
                rec = json.loads(raw)
            except (json.JSONDecodeError, ValueError):
                continue
            if rec.get("type") != "user":
                continue
            content = (rec.get("message") or {}).get("content")
            if not isinstance(content, list):
                continue
            for block in content:
                if not isinstance(block, dict) or block.get("type") != "tool_result":
                    continue
                is_error = bool(block.get("is_error"))
                errors.append(is_error)
                if is_error:
                    total += 1
                    consec += 1
                    max_consec = max(max_consec, consec)
                else:
                    consec = 0
        tail_has_error = any(errors[-_TAIL_WINDOW:]) if errors else False
        return check_error_streak(max_consec, total, tail_has_error=tail_has_error)
    except OSError:
        return None


def record_guard_flag(
    conn: sqlite3.Connection,
    session_id: int | None,
    run_id: str | None,
    evidence: GuardEvidence,
    shadow: bool = True,
) -> None:
    """Persist one guard flag. Defaults to shadow=1 (computed, never surfaced) —
    the guard stays shadow-only until it can be scored against real user marks
    (the published 'precision' is label-circular; see README)."""
    conn.execute(
        """
        INSERT INTO guard_flags (session_id, run_id, ts, rule_id, evidence, shadow)
        VALUES (?,?,?,?,?,?)
        """,
        (
            session_id,
            run_id,
            datetime.now(timezone.utc).isoformat(),
            evidence.rule_id,
            evidence.fact,
            int(shadow),
        ),
    )
    conn.commit()
