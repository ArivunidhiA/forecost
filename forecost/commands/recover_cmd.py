"""Replay the dead-letter queue without discarding records that did not replay."""

from __future__ import annotations

import hashlib
import json
import math
import os
import re
import tempfile
from contextlib import suppress
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

import click

from forecost.adapters.base import Money, PostingSpec, UsageEvent
from forecost.core.errlog import log_error
from forecost.core.paths import chmod_private, forecost_home
from forecost.ledger.sink import SyncLedgerSink

_RECOVERY_FILES = ("recovery.jsonl", "legacy-recovery.jsonl")
_RECOVERY_GLOBS = ("recovery.*.jsonl", "legacy-recovery.*.jsonl")
_POSTING_BASES = frozenset({"pricing_table", "source_reported", "plan_model"})
_MAX_RECOVERY_BYTES = 64 * 1024 * 1024
_SPOOL_NAME = re.compile(r"(?:legacy-)?recovery\.\d+\.\d+\.[0-9a-f]{32}\.jsonl")


@dataclass(frozen=True)
class ReplayResult:
    path: Path
    replayed: int
    duplicate: int
    pending: int
    archive: Path | None = None
    error: str | None = None


def _legacy_event_uid(row: dict) -> str:
    payload = json.dumps(row, sort_keys=True, separators=(",", ":"), default=str).encode()
    return f"legacy-recovery:{hashlib.sha256(payload).hexdigest()}"


def _metadata(row: dict) -> dict:
    value = row.get("metadata") or {}
    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        parsed = json.loads(value)
        if isinstance(parsed, dict):
            return parsed
    raise ValueError("metadata must be a JSON object")


def _reported_cost(row: dict) -> Money | None:
    reported = row.get("reported_cost")
    if isinstance(reported, dict):
        return Money(amount=float(reported["amount"]), currency=str(reported["currency"]))
    # Pre-ledger WriteQueue recovery rows used cost_usd instead.
    if row.get("cost_usd") is not None:
        return Money(amount=float(row["cost_usd"]), currency="USD")
    return None


def _timestamp(row: dict) -> datetime:
    raw_ts = row.get("ts", row.get("timestamp"))
    if raw_ts is None:
        raise ValueError("missing timestamp")
    ts = datetime.fromisoformat(str(raw_ts).replace("Z", "+00:00"))
    return ts.replace(tzinfo=timezone.utc) if ts.tzinfo is None else ts.astimezone(timezone.utc)


def _row_to_event(row: dict) -> UsageEvent:
    """Accept both the ledger and live legacy WriteQueue recovery schemas."""
    event_uid = str(row.get("event_uid") or _legacy_event_uid(row))
    return UsageEvent(
        event_uid=event_uid,
        ts=_timestamp(row),
        source=str(row.get("source") or "legacy-recovery"),
        model=str(row["model"]),
        provider=row.get("provider"),
        session_uid=row.get("session_uid"),
        run_id=row.get("run_id"),
        agent=row.get("agent"),
        workspace_path=row.get("workspace_path"),
        tokens_in=int(row.get("tokens_in", 0) or 0),
        tokens_out=int(row.get("tokens_out", 0) or 0),
        tokens_cache_read=int(row.get("tokens_cache_read", 0) or 0),
        tokens_cache_write=int(row.get("tokens_cache_write", 0) or 0),
        reported_cost=_reported_cost(row),
        metadata=_metadata(row),
    )


def _posting_currency(raw: dict) -> str:
    currency = raw.get("currency")
    if not isinstance(currency, str) or not currency or len(currency) > 200:
        raise ValueError("posting currency is invalid")
    return currency


def _posting_basis(raw: dict) -> str:
    basis = raw.get("basis")
    if basis not in _POSTING_BASES:
        raise ValueError("posting basis is invalid")
    return basis


def _posting_amount(raw: dict) -> float:
    amount = raw.get("amount")
    if isinstance(amount, bool) or not isinstance(amount, (int, float)):
        raise ValueError("posting amount must be numeric")
    numeric_amount = float(amount)
    if not math.isfinite(numeric_amount) or numeric_amount < 0:
        raise ValueError("posting amount must be finite and nonnegative")
    return numeric_amount


def _posting_version(raw: dict) -> str | None:
    version = raw.get("pricing_version")
    if version is not None and (not isinstance(version, str) or len(version) > 256):
        raise ValueError("posting pricing version is invalid")
    return version


def _serialized_posting(raw: object) -> PostingSpec:
    if not isinstance(raw, dict):
        raise ValueError("each posting must be a JSON object")
    return PostingSpec(
        _posting_currency(raw),
        _posting_amount(raw),
        _posting_basis(raw),
        _posting_version(raw),
    )


def _serialized_postings(row: dict) -> list[PostingSpec] | None:
    """Return exact durable postings, or None for legacy rows that need pricing."""
    raw_postings = row.get("postings")
    if raw_postings is None:
        return None
    if not isinstance(raw_postings, list) or not raw_postings:
        raise ValueError("postings must be a non-empty JSON array")
    return [_serialized_posting(raw) for raw in raw_postings]


def _rewrite_failed_lines(recovery: Path, failed_lines: list[str]) -> None:
    """Atomically replace the queue with only records that still need replay."""
    temp_name: str | None = None
    try:
        with tempfile.NamedTemporaryFile(
            "w",
            encoding="utf-8",
            dir=recovery.parent,
            prefix=".recovery-",
            suffix=".tmp",
            delete=False,
        ) as temp:
            temp_name = temp.name
            for line in failed_lines:
                temp.write(line)
                temp.write("\n")
            temp.flush()
            os.fsync(temp.fileno())
        temp_path = Path(temp_name)
        chmod_private(temp_path)
        os.replace(temp_path, recovery)
        chmod_private(recovery)
    except OSError:
        if temp_name is not None:
            with suppress(OSError):
                Path(temp_name).unlink(missing_ok=True)
        raise


def _next_archive_path(recovery: Path) -> Path:
    first = recovery.with_name(f"{recovery.stem}.replayed.jsonl")
    if not first.exists():
        return first
    index = 1
    while True:
        candidate = recovery.with_name(f"{recovery.stem}.replayed.{index}.jsonl")
        if not candidate.exists():
            return candidate
        index += 1


def _replay_lines(sink: SyncLedgerSink, lines: list[str]) -> tuple[int, int, list[str]]:
    replayed = duplicate = 0
    failed_lines: list[str] = []
    for raw_line in lines:
        line = raw_line.strip()
        if not line:
            continue
        try:
            row = json.loads(line)
            if not isinstance(row, dict):
                raise ValueError("recovery line must be a JSON object")
            event = _row_to_event(row)
            postings = _serialized_postings(row)
            inserted = (
                sink.emit(event) if postings is None else sink.emit_with_postings(event, postings)
            )
            if inserted:
                replayed += 1
            else:
                duplicate += 1
        except Exception as exc:  # one bad record must not block independent records
            failed_lines.append(raw_line)
            log_error("commands.recover", f"could not replay a recovery line: {exc!r}")
    return replayed, duplicate, failed_lines


def _flush_or_retain_all(
    sink: SyncLedgerSink, lines: list[str], failed_lines: list[str]
) -> list[str]:
    try:
        sink.flush()
        return failed_lines
    except Exception as exc:
        # The durable outcome is uncertain. Retaining every record is safe
        # because event_uid makes replay idempotent.
        log_error("commands.recover", f"could not flush replayed records: {exc!r}")
        return [line for line in lines if line.strip()]


def _recover_file(recovery: Path) -> ReplayResult:
    try:
        if recovery.stat().st_size > _MAX_RECOVERY_BYTES:
            return ReplayResult(
                recovery,
                0,
                0,
                0,
                error=f"queue exceeds {_MAX_RECOVERY_BYTES} bytes; split it before replay",
            )
        lines = recovery.read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeError) as exc:
        return ReplayResult(recovery, 0, 0, 0, error=f"could not read queue: {exc!r}")
    sink = SyncLedgerSink()
    replayed, duplicate, failed_lines = _replay_lines(sink, lines)
    failed_lines = _flush_or_retain_all(sink, lines, failed_lines)

    if failed_lines:
        return _retain_failed(recovery, replayed, duplicate, failed_lines)
    return _archive_replayed(recovery, replayed, duplicate)


def _pending_recovery_paths(home: Path) -> list[Path]:
    """Find legacy shared queues and every immutable per-batch spool."""
    candidates = {home / name for name in _RECOVERY_FILES}
    for pattern in _RECOVERY_GLOBS:
        candidates.update(path for path in home.glob(pattern) if _SPOOL_NAME.fullmatch(path.name))
    return sorted(
        path
        for path in candidates
        if ".replayed" not in path.name and path.is_file() and path.stat().st_size > 0
    )


def _retain_failed(
    recovery: Path, replayed: int, duplicate: int, failed_lines: list[str]
) -> ReplayResult:
    try:
        _rewrite_failed_lines(recovery, failed_lines)
    except OSError as exc:
        log_error("commands.recover", f"could not retain failed recovery lines: {exc!r}")
        return ReplayResult(
            recovery,
            replayed,
            duplicate,
            len(failed_lines),
            error="partial replay; original queue was left in place because rewrite failed",
        )
    return ReplayResult(recovery, replayed, duplicate, len(failed_lines))


def _archive_replayed(recovery: Path, replayed: int, duplicate: int) -> ReplayResult:
    archive = _next_archive_path(recovery)
    try:
        recovery.replace(archive)
    except OSError as exc:
        log_error("commands.recover", f"could not archive recovery file: {exc!r}")
        return ReplayResult(
            recovery,
            replayed,
            duplicate,
            0,
            error="replay succeeded, but the queue could not be archived and remains for retry",
        )
    return ReplayResult(recovery, replayed, duplicate, 0, archive=archive)


def _report_result(result: ReplayResult) -> None:
    summary = (
        f"{result.path.name}: Recovered {result.replayed} event(s) "
        f"({result.duplicate} already present, {result.pending} still pending)."
    )
    if result.error:
        click.echo(f"{summary} ERROR: {result.error}.")
    elif result.archive:
        click.echo(f"{summary} Archived to {result.archive.name}.")
    else:
        click.echo(f"{summary} Kept failed records in {result.path.name}.")


@click.command()
def recover() -> None:
    """Replay current and legacy $FORECOST_HOME dead-letter queues safely."""
    pending_paths = _pending_recovery_paths(forecost_home())
    if not pending_paths:
        click.echo("No recovery file to replay — nothing was ever spilled. Good.")
        return

    results = [_recover_file(path) for path in pending_paths]
    for result in results:
        _report_result(result)
    if any(result.error for result in results):
        raise click.ClickException("One or more recovery queues need an idempotent retry.")
