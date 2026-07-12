"""forecost calibration — the public accuracy record (BASEMENT.md law L8)."""

from __future__ import annotations

import click

from forecost.estimate.calibration import calibration_by_category, reconcile_estimates
from forecost.ledger import queries as q
from forecost.ledger.db import get_ledger_db


def _print_by_category(conn, currency: str) -> None:
    by_cat = calibration_by_category(conn, currency=currency)
    if not by_cat:
        return
    click.echo("\nBy task class:")
    for row in by_cat:
        cov = f"{row['coverage']:.0%}" if row["coverage"] is not None else "-"
        click.echo(f"  {row['category']:<20} n={row['n']:<5} coverage={cov}")


@click.command()
@click.option("--currency", default="USD")
def calibration(currency):
    """Reconcile pending estimates against actuals and show the accuracy record."""
    conn = get_ledger_db()
    newly = reconcile_estimates(conn)
    if newly:
        click.echo(f"Reconciled {newly} new estimate(s) against actuals.\n")

    summary = q.calibration_summary(conn, currency=currency)
    if not summary["n"]:
        click.echo(
            "No reconciled estimates yet. Estimates accumulate as the preflight hook "
            "runs and actuals are ingested; the record starts building automatically."
        )
        return

    coverage = summary["coverage"]
    mape = summary["mape"]
    click.echo(f"Calibration record ({currency}, n={summary['n']} reconciled estimates):")
    if coverage is not None:
        click.echo(f"  P10-P90 band coverage: {coverage:.1%}")
    if mape is not None:
        click.echo(f"  Mean abs. pct error vs P50: {mape:.1%}")

    _print_by_category(conn, currency)

    click.echo(
        "\nEstimates remain shadow-mode (never displayed in the brief) until this "
        "record clears gate G-A — see BASEMENT.md §8."
    )
