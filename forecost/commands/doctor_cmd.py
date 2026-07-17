"""forecost doctor — one-glance setup check and known-gaps report."""

from __future__ import annotations

import os

import click

from forecost import __version__
from forecost.core.paths import forecost_home
from forecost.ledger import queries as q
from forecost.ledger.db import get_ledger_db
from forecost.ledger.sink import PRICING_SNAPSHOT_VERSION

_ALL_TIME = "1970-01-01T00:00:00+00:00"


@click.command()
def doctor() -> None:
    """Report where forecost keeps data, what's ingested, and known gaps."""
    home = forecost_home()
    override = os.environ.get("FORECOST_HOME")
    click.echo(f"forecost {__version__}")
    click.echo(f"  home: {home}" + (" (via FORECOST_HOME)" if override else " (default)"))
    click.echo(f"  home exists: {home.exists()}")
    click.echo(f"  pricing table: {PRICING_SNAPSHOT_VERSION}")

    conn = get_ledger_db()
    n_events = conn.execute("SELECT COUNT(*) FROM usage_events").fetchone()[0]
    spend = q.scope_spend(conn, "USD", _ALL_TIME)
    n_recon = conn.execute("SELECT COUNT(*) FROM reconciliations").fetchone()[0]
    click.echo(
        f"  ledger: {n_events} events, USD {spend.total:.2f} (canonical), {n_recon} reconciled"
    )

    recovery = home / "recovery.jsonl"
    if recovery.exists() and recovery.stat().st_size > 0:
        pending = len(recovery.read_text(encoding="utf-8").splitlines())
        click.echo(
            f"  ⚠ recovery.jsonl has {pending} un-replayed event(s) — run `forecost recover`"
        )
    else:
        click.echo("  recovery: clean (no spilled events)")

    legacy = home / "costs.db"
    if legacy.exists():
        click.echo("  note: legacy costs.db present (the old forecaster's data; not migrated)")

    click.echo("\nKnown gaps (not yet done):")
    click.echo("  - Not published to PyPI: install from a git clone (`pip install -e .`).")
    click.echo("  - Claude Code hooks plugin is not auto-installed; wiring is a follow-up.")
    click.echo("  - Estimator stays in shadow mode until calibration gates pass (see")
    click.echo("    `forecost calibration`).")
    click.echo(
        "  - Repo-local .forecost.toml is ignored for enforcement unless "
        "FORECOST_TRUST_PROJECT_POLICY=1."
    )
