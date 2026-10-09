import sqlite3
from collections.abc import Callable
from datetime import datetime, timezone
from pathlib import Path

import click

from forecost.core.paths import chmod_private
from forecost.ledger import queries as q
from forecost.ledger.db import (
    LEDGER_PATH,
    _apply_pragmas,
    _ensure_dir,
    create_verified_snapshot,
    get_ledger_db,
)
from forecost.ledger.schema import SCHEMA_VERSION, apply_schema

_BASIS_CHOICE = click.Choice(["canonical", "pricing_table", "source_reported"])
_ALL_TIME = "1970-01-01T00:00:00+00:00"


def _verified_integrity(conn: sqlite3.Connection, *, label: str) -> None:
    """Reject a SQLite image unless a full page/index integrity check passes."""
    findings = [str(row[0]) for row in conn.execute("PRAGMA integrity_check")]
    if findings != ["ok"]:
        detail = "; ".join(findings[:3]) or "no result"
        raise sqlite3.DatabaseError(f"{label} failed SQLite integrity_check: {detail}")


def _discard_backup_files(path: Path) -> None:
    """Remove only the exact failed backup and its SQLite sidecars."""
    for candidate in (
        path,
        Path(f"{path}-journal"),
        Path(f"{path}-wal"),
        Path(f"{path}-shm"),
    ):
        candidate.unlink(missing_ok=True)


def _create_verified_backup(
    source: sqlite3.Connection,
    backup_path: Path,
    *,
    connect: Callable[[str], sqlite3.Connection] = sqlite3.connect,
) -> None:
    """Create a transactionally consistent, standalone SQLite backup.

    ``Connection.backup`` reads the logical database, including committed WAL
    pages.  Copying only the main file can silently omit those pages.  The
    destination uses FULL synchronous mode, is checked before migration starts,
    and is deleted if backup or verification fails.
    """
    if backup_path.exists() or backup_path.is_symlink():
        raise FileExistsError(f"refusing to overwrite migration backup: {backup_path}")
    destination: sqlite3.Connection | None = None
    try:
        if connect is sqlite3.connect:
            create_verified_snapshot(source, backup_path)
        else:
            # Dependency seam used only to exercise cleanup after a partial
            # backup failure; production goes through create_verified_snapshot.
            destination = connect(str(backup_path))
            destination.execute("PRAGMA synchronous=FULL")
            source.backup(destination)
            _verified_integrity(destination, label="migration backup")
            destination.commit()
    except BaseException:
        if destination is not None:
            destination.close()
            destination = None
        _discard_backup_files(backup_path)
        raise
    finally:
        if destination is not None:
            destination.close()
    chmod_private(backup_path)


@click.group()
def ledger():
    """Inspect the local ledger."""


@ledger.command("status")
@click.option("--currency", default="USD")
@click.option(
    "--basis",
    type=_BASIS_CHOICE,
    default="canonical",
    help="Which valuation to sum. 'canonical' picks one posting per event "
    "(source_reported over pricing_table); the others show a single valuation.",
)
def ledger_status(currency, basis):
    """Show total events, spend, and workspace/session counts."""
    conn = get_ledger_db()
    n_events = conn.execute("SELECT COUNT(*) FROM usage_events").fetchone()[0]
    spend = q.scope_spend(conn, currency, _ALL_TIME, basis=basis)
    n_ws = conn.execute("SELECT COUNT(*) FROM workspaces").fetchone()[0]
    n_sessions = conn.execute("SELECT COUNT(*) FROM sessions").fetchone()[0]

    click.echo(f"Ledger: {n_events} usage events, {n_ws} workspaces, {n_sessions} sessions")
    click.echo(f"Total {currency} spend ({basis}): {spend.total:.2f}")
    if spend.n_unpriced_events:
        click.echo(
            f"  Includes {currency} {spend.unpriced_total:.2f} guessed across "
            f"{spend.n_unpriced_events} event(s); not safe for hard budget decisions."
        )
    if n_events == 0:
        click.echo("\nLedger is empty. Run `forecost ingest` to pull your Claude Code history.")
        return

    rows = q.spend_by_model(conn, currency, basis=basis, limit=10)
    if rows:
        click.echo("\nTop models by spend:")
        for r in rows:
            guessed = (
                f" (includes {currency} {r['unpriced_total']:.2f} guessed across "
                f"{r['n_unpriced']} event(s))"
                if r["n_unpriced"]
                else ""
            )
            click.echo(f"  {r['model']:<40} n={r['n']:<6} {currency} {r['total']:.2f}{guessed}")


@ledger.command("by-workspace")
@click.option("--currency", default="USD")
@click.option("--basis", type=_BASIS_CHOICE, default="canonical", help="Valuation to sum.")
def ledger_by_workspace(currency, basis):
    """Show spend broken down by workspace."""
    conn = get_ledger_db()
    rows = q.spend_by_workspace(conn, currency, basis=basis)
    if not rows:
        workspace_count = conn.execute("SELECT COUNT(*) FROM workspaces").fetchone()[0]
        if workspace_count == 0:
            click.echo("No workspaces recorded yet. Run `forecost ingest` first.")
        else:
            click.echo(
                f"No {currency} {basis} postings are associated with the "
                f"{workspace_count} recorded workspace(s)."
            )
        return
    for r in rows:
        guessed = (
            f"; includes {currency} {r['unpriced_total']:.2f} guessed across "
            f"{r['n_unpriced']} event(s)"
            if r["n_unpriced"]
            else ""
        )
        click.echo(
            f"{r['name']:<30} {currency} {r['total']:>10.2f}  "
            f"({r['n']} events{guessed})  {r['root_path']}"
        )


@ledger.command("migrate-schema")
@click.option("--ledger-path", type=click.Path(path_type=Path), default=None)
@click.option("--dry-run", is_flag=True, help="Report pending migration without changing files.")
def migrate_schema(ledger_path: Path | None, dry_run: bool) -> None:
    """Apply forward-only migrations after a verified SQLite snapshot."""
    path = (ledger_path or LEDGER_PATH).expanduser().resolve()
    if dry_run:
        if not path.exists():
            click.echo(f"Would create a new ledger at {path} with schema v{SCHEMA_VERSION}.")
            return
        conn = sqlite3.connect(path)
        try:
            current = conn.execute("PRAGMA user_version").fetchone()[0]
        finally:
            conn.close()
        click.echo(f"Ledger schema v{current}; target v{SCHEMA_VERSION}; no changes made.")
        return
    backup: Path | None = None
    _ensure_dir(path)
    existed = path.exists()
    conn = sqlite3.connect(str(path))
    try:
        _apply_pragmas(conn)
        if existed:
            # Microseconds avoid overwriting two backups produced in one second.
            stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
            backup = path.with_name(f"{path.name}.pre-v{SCHEMA_VERSION}-{stamp}.bak")
            _create_verified_backup(conn, backup)
        apply_schema(conn)
        _verified_integrity(conn, label="migrated ledger")
    except (OSError, RuntimeError, sqlite3.Error) as error:
        retained = f" Verified backup retained at {backup}." if backup and backup.exists() else ""
        raise click.ClickException(f"Ledger migration failed: {error}.{retained}") from error
    finally:
        conn.close()
    if backup is None:
        click.echo(f"Created ledger schema v{SCHEMA_VERSION} at {path}.")
    else:
        click.echo(f"Migrated ledger to schema v{SCHEMA_VERSION}; backup: {backup}")
