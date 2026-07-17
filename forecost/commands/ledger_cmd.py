import click

from forecost.ledger import queries as q
from forecost.ledger.db import get_ledger_db

_BASIS_CHOICE = click.Choice(["canonical", "pricing_table", "source_reported"])
_ALL_TIME = "1970-01-01T00:00:00+00:00"


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
    if n_events == 0:
        click.echo("\nLedger is empty. Run `forecost ingest` to pull your Claude Code history.")
        return

    rows = q.spend_by_model(conn, currency, basis=basis, limit=10)
    if rows:
        click.echo("\nTop models by spend:")
        for r in rows:
            click.echo(f"  {r['model']:<40} n={r['n']:<6} {currency} {r['total']:.2f}")


@ledger.command("by-workspace")
@click.option("--currency", default="USD")
@click.option("--basis", type=_BASIS_CHOICE, default="canonical", help="Valuation to sum.")
def ledger_by_workspace(currency, basis):
    """Show spend broken down by workspace."""
    conn = get_ledger_db()
    rows = q.spend_by_workspace(conn, currency, basis=basis)
    if not rows:
        click.echo("No workspaces recorded yet. Run `forecost ingest` first.")
        return
    for r in rows:
        click.echo(
            f"{r['name']:<30} {currency} {r['total']:>10.2f}  ({r['n']} events)  {r['root_path']}"
        )
