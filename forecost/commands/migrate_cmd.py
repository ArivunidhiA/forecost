"""forecost migrate — port the legacy costs.db into the ledger.

The old calendar-spend product wrote ~/.forecost/costs.db (usage_logs + projects).
This re-emits each legacy usage row into the ledger as a usage_event + a
pricing_table posting computed with the *current* pricing table (the legacy
cost_usd was computed with the old, since-corrected prices, so it is not carried
over — the tokens are the source of truth). Idempotent: each row keys on
`legacy:{id}`, so re-running migrates only new rows. The legacy costs.db is left
untouched.
"""

from __future__ import annotations

import sqlite3
from datetime import datetime, timezone

import click

from forecost.adapters.base import UsageEvent
from forecost.core.paths import forecost_home
from forecost.ledger.sink import SyncLedgerSink


def _parse_ts(raw: str):
    try:
        return datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
    except (ValueError, TypeError):
        return datetime.now(timezone.utc)


def _legacy_rows(costs_db):
    conn = sqlite3.connect(str(costs_db))
    conn.row_factory = sqlite3.Row
    try:
        projects = {
            r["id"]: r["path"] for r in conn.execute("SELECT id, path FROM projects").fetchall()
        }
    except sqlite3.Error:
        projects = {}
    rows = conn.execute(
        "SELECT id, project_id, timestamp, model, provider, tokens_in, tokens_out FROM usage_logs"
    ).fetchall()
    conn.close()
    return rows, projects


@click.command()
def migrate() -> None:
    """Port legacy costs.db usage into the ledger (re-priced, idempotent)."""
    costs_db = forecost_home() / "costs.db"
    if not costs_db.exists():
        click.echo("No legacy costs.db found — nothing to migrate.")
        return

    try:
        rows, projects = _legacy_rows(costs_db)
    except sqlite3.Error as exc:
        click.echo(f"Could not read legacy costs.db: {exc}")
        return
    if not rows:
        click.echo("Legacy costs.db has no usage rows — nothing to migrate.")
        return

    sink = SyncLedgerSink()  # re-prices via the current table; INSERT OR IGNORE dedups
    migrated = duplicate = 0
    for r in rows:
        event = UsageEvent(
            event_uid=f"legacy:{r['id']}",
            ts=_parse_ts(r["timestamp"]),
            source="legacy-costs-db",
            model=r["model"],
            provider=r["provider"],
            workspace_path=projects.get(r["project_id"]),
            tokens_in=int(r["tokens_in"] or 0),
            tokens_out=int(r["tokens_out"] or 0),
            metadata={"migrated_from": "costs.db"},
        )
        if sink.emit(event):
            migrated += 1
        else:
            duplicate += 1
    sink.flush()

    click.echo(
        f"Migrated {migrated} legacy usage row(s) into the ledger "
        f"({duplicate} already present). Legacy costs.db left untouched; re-priced "
        "with the current table (run `forecost ledger status` to see the result)."
    )
