import click

from forecost.ledger.db import get_ledger_db


@click.group()
def ledger():
    """Inspect the local ledger."""


@ledger.command("status")
@click.option("--currency", default="USD")
def ledger_status(currency):
    """Show total events, spend, and workspace/session counts."""
    conn = get_ledger_db()
    n_events = conn.execute("SELECT COUNT(*) FROM usage_events").fetchone()[0]
    total = conn.execute(
        "SELECT COALESCE(SUM(amount), 0) FROM postings WHERE currency = ?", (currency,)
    ).fetchone()[0]
    n_ws = conn.execute("SELECT COUNT(*) FROM workspaces").fetchone()[0]
    n_sessions = conn.execute("SELECT COUNT(*) FROM sessions").fetchone()[0]

    click.echo(f"Ledger: {n_events} usage events, {n_ws} workspaces, {n_sessions} sessions")
    click.echo(f"Total {currency} spend (pricing_table + source_reported): {total:.2f}")

    rows = conn.execute(
        """
        SELECT e.model, COUNT(*) AS n, SUM(p.amount) AS total
        FROM postings p JOIN usage_events e ON e.id = p.event_id
        WHERE p.currency = ?
        GROUP BY e.model ORDER BY total DESC LIMIT 10
        """,
        (currency,),
    ).fetchall()
    if rows:
        click.echo("\nTop models by spend:")
        for r in rows:
            click.echo(f"  {r['model']:<40} n={r['n']:<6} {currency} {r['total']:.2f}")


@ledger.command("by-workspace")
@click.option("--currency", default="USD")
def ledger_by_workspace(currency):
    """Show spend broken down by workspace."""
    conn = get_ledger_db()
    rows = conn.execute(
        """
        SELECT w.name, w.root_path, COUNT(*) AS n, SUM(p.amount) AS total
        FROM postings p
        JOIN usage_events e ON e.id = p.event_id
        JOIN workspaces w ON w.id = e.workspace_id
        WHERE p.currency = ?
        GROUP BY w.id ORDER BY total DESC
        """,
        (currency,),
    ).fetchall()
    for r in rows:
        click.echo(
            f"{r['name']:<30} {currency} {r['total']:>10.2f}  ({r['n']} events)  {r['root_path']}"
        )
