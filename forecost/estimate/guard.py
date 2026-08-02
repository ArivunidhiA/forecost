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
from collections import deque
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from forecost.ledger.db import ledger_write_lock

CONSEC_ERROR_THRESHOLD = 3
TAIL_ERROR_MIN_COUNT = 2
_TAIL_WINDOW = 5  # size of the "recent window" the tail-error rule looks at
_MAX_SCAN_BYTES = 4 * 1024 * 1024
_READ_CHUNK_BYTES = 64 * 1024


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


def _tool_result_errors(record: object) -> list[bool]:
    if not isinstance(record, dict) or record.get("type") != "user":
        return []
    message = record.get("message")
    if not isinstance(message, dict):
        return []
    content = message.get("content")
    if not isinstance(content, list):
        return []
    return [
        bool(block.get("is_error"))
        for block in content
        if isinstance(block, dict) and block.get("type") == "tool_result"
    ]


def _recent_error_tail(raw_lines: list[bytes]) -> list[bool]:
    tail: deque[bool] = deque(maxlen=_TAIL_WINDOW)
    for raw in raw_lines:
        try:
            record = json.loads(raw)
        except (json.JSONDecodeError, UnicodeDecodeError, ValueError, TypeError):
            continue
        tail.extend(_tool_result_errors(record))
    return list(tail)


def _current_error_streak(tail: list[bool]) -> int:
    streak = 0
    for is_error in reversed(tail):
        if not is_error:
            break
        streak += 1
    return streak


def _bounded_tail_lines(path: Path, max_records: int) -> list[bytes]:
    """Read complete lines from a bounded suffix, independent of file size."""
    if max_records <= 0:
        return []
    with path.open("rb") as stream:
        stream.seek(0, 2)
        position = stream.tell()
        chunks: list[bytes] = []
        scanned = 0
        line_breaks = 0
        while position > 0 and scanned < _MAX_SCAN_BYTES and line_breaks <= max_records:
            size = min(_READ_CHUNK_BYTES, position, _MAX_SCAN_BYTES - scanned)
            position -= size
            stream.seek(position)
            chunk = stream.read(size)
            chunks.append(chunk)
            scanned += len(chunk)
            line_breaks += chunk.count(b"\n")
    data = b"".join(reversed(chunks))
    if position > 0:
        _partial, separator, data = data.partition(b"\n")
        if not separator:
            return []
    return data.splitlines()[-max_records:]


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
        lines = _bounded_tail_lines(p, max_records)
        tail = _recent_error_tail(lines)
        return check_error_streak(
            _current_error_streak(tail),
            sum(tail),
            tail_has_error=bool(tail and tail[-1]),
        )
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
    with ledger_write_lock:
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
