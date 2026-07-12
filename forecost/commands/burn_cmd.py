"""forecost burn — trailing burn rate and time-to-budget-limit."""

from __future__ import annotations

import click

from forecost.estimate.trajectory import burn_report
from forecost.ledger.db import get_ledger_db


def _eta(hours_to_limit) -> str:
    if hours_to_limit is None:
        return "no active burn"
    if hours_to_limit == 0:
        return "LIMIT REACHED"
    return f"~{hours_to_limit:.1f}h at current rate"


@click.command()
@click.option("--currency", default="USD")
@click.option("--window-hours", default=24.0, help="Trailing window for the rate")
def burn(currency, window_hours):
    """Show measured trailing burn rate, projected against active budgets."""
    conn = get_ledger_db()
    reports = burn_report(conn, currency=currency, window_hours=window_hours)

    head = reports[0]
    click.echo(
        f"Trailing {window_hours:.0f}h: {currency} {head.spent_in_window:.2f} "
        f"({currency} {head.hourly_rate:.2f}/hour)"
    )

    budgeted = [r for r in reports if r.budget_name]
    if not budgeted:
        click.echo(
            "No active budgets configured — add [[policy.rules]] to .forecost.toml "
            "or budget rows to see time-to-limit projections."
        )
        return

    for r in budgeted:
        click.echo(
            f"  budget '{r.budget_name}' ({r.currency} {r.budget_limit:.2f}): "
            f"spent {r.spent_toward_budget:.2f}, {_eta(r.hours_to_limit)}"
        )
