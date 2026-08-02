"""forecost doctor — one-glance setup check and known-gaps report."""

from __future__ import annotations

import os
import re

import click

from forecost import __version__
from forecost.core.paths import forecost_home
from forecost.ledger import queries as q
from forecost.ledger.db import get_ledger_db
from forecost.ledger.sink import PRICING_SNAPSHOT_VERSION

_ALL_TIME = "1970-01-01T00:00:00+00:00"
_SPOOL_NAME = re.compile(r"(?:legacy-)?recovery\.\d+\.\d+\.[0-9a-f]{32}\.jsonl")


def _echo_home(home) -> None:
    override = os.environ.get("FORECOST_HOME")
    click.echo(f"forecost {__version__}")
    click.echo(f"  home: {home}" + (" (via FORECOST_HOME)" if override else " (default)"))
    click.echo(f"  home exists: {home.exists()}")
    click.echo(f"  pricing table: {PRICING_SNAPSHOT_VERSION}")


def _echo_ledger(conn) -> None:
    n_events = conn.execute("SELECT COUNT(*) FROM usage_events").fetchone()[0]
    spend = q.scope_spend(conn, "USD", _ALL_TIME)
    n_recon = conn.execute("SELECT COUNT(*) FROM reconciliations").fetchone()[0]
    click.echo(
        f"  ledger: {n_events} events, USD {spend.total:.2f} (canonical), {n_recon} reconciled"
    )
    if spend.n_unpriced_events:
        click.echo(
            f"  ⚠ includes USD {spend.unpriced_total:.2f} guessed across "
            f"{spend.n_unpriced_events} event(s); guesses never trigger hard denials"
        )


def _pending_lines(path) -> int:
    if not path.exists() or path.stat().st_size == 0:
        return 0
    with path.open(encoding="utf-8") as recovery_file:
        return sum(1 for line in recovery_file if line.strip())


def _echo_recovery(home) -> None:
    recovery_files = {home / "recovery.jsonl", home / "legacy-recovery.jsonl"}
    recovery_files.update(home.glob("recovery.*.jsonl"))
    recovery_files.update(home.glob("legacy-recovery.*.jsonl"))
    recovery_files = {
        path
        for path in recovery_files
        if path.name in {"recovery.jsonl", "legacy-recovery.jsonl"}
        or _SPOOL_NAME.fullmatch(path.name)
    }
    pending = sum(_pending_lines(path) for path in recovery_files)
    if pending:
        click.echo(f"  ⚠ recovery queues have {pending} pending record(s) — run `forecost recover`")
    else:
        click.echo("  recovery: clean (no pending spills)")

    legacy = home / "costs.db"
    if legacy.exists():
        click.echo("  note: legacy costs.db present (the old forecaster's data; not migrated)")


def _echo_limitations() -> None:
    click.echo("\nKnown limitations:")
    click.echo("  - Marketplace plugin bootstrap is currently supported on macOS/Linux.")
    click.echo("  - Estimator stays in shadow mode until calibration gates pass (see")
    click.echo("    `forecost calibration`).")
    click.echo(
        "  - Repo-local .forecost.toml is ignored for enforcement unless "
        "FORECOST_TRUST_PROJECT_POLICY=1."
    )


@click.command()
def doctor() -> None:
    """Report where forecost keeps data, what's ingested, and known gaps."""
    home = forecost_home()
    _echo_home(home)
    _echo_ledger(get_ledger_db())
    _echo_recovery(home)
    _echo_limitations()
