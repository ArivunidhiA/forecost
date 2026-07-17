"""forecost recover — replay the dead-letter file back into the ledger.

The async writer spills batches it couldn't commit to $FORECOST_HOME/recovery.jsonl
so nothing is lost on a transient DB failure. Until now nothing replayed it — the
file was durability theater (both audits flagged this). This command re-emits each
spilled event through the synchronous sink (which re-resolves ids and re-prices),
idempotently via INSERT OR IGNORE on event_uid, then archives the file so it is
never replayed twice.
"""

from __future__ import annotations

import json
from datetime import datetime

import click

from forecost.adapters.base import Money, UsageEvent
from forecost.core.errlog import log_error
from forecost.core.paths import forecost_home
from forecost.ledger.sink import SyncLedgerSink


def _row_to_event(row: dict) -> UsageEvent:
    reported = row.get("reported_cost")
    money = Money(**reported) if isinstance(reported, dict) else None
    return UsageEvent(
        event_uid=row["event_uid"],
        ts=datetime.fromisoformat(row["ts"]),
        source=row["source"],
        model=row["model"],
        provider=row.get("provider"),
        session_uid=row.get("session_uid"),
        run_id=row.get("run_id"),
        agent=row.get("agent"),
        workspace_path=row.get("workspace_path"),
        tokens_in=row.get("tokens_in", 0) or 0,
        tokens_out=row.get("tokens_out", 0) or 0,
        tokens_cache_read=row.get("tokens_cache_read", 0) or 0,
        tokens_cache_write=row.get("tokens_cache_write", 0) or 0,
        reported_cost=money,
        metadata=row.get("metadata") or {},
    )


@click.command()
def recover() -> None:
    """Replay $FORECOST_HOME/recovery.jsonl into the ledger, then archive it."""
    recovery = forecost_home() / "recovery.jsonl"
    if not recovery.exists() or recovery.stat().st_size == 0:
        click.echo("No recovery file to replay — nothing was ever spilled. Good.")
        return

    sink = SyncLedgerSink()  # shares the cached ledger connection
    replayed = failed = duplicate = 0
    for line in recovery.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            inserted = sink.emit(_row_to_event(json.loads(line)))
            if inserted:
                replayed += 1
            else:
                duplicate += 1
        except Exception as exc:  # nosec B110 - a bad recovery line must not abort the rest
            failed += 1
            log_error("commands.recover", f"could not replay a recovery line: {exc!r}")
    sink.flush()

    # Archive so a second run doesn't re-process the same lines.
    archive = recovery.with_name("recovery.replayed.jsonl")
    try:
        recovery.replace(archive)
    except OSError as exc:
        log_error("commands.recover", f"could not archive recovery file: {exc!r}")

    click.echo(
        f"Recovered {replayed} event(s) ({duplicate} already present, {failed} unparseable). "
        f"Archived the dead-letter file to {archive.name}."
    )
