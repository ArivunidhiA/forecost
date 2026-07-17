"""forecost pricing-audit — surface where the ledger's dollars are a guess.

The product's whole pitch is a meter you can trust, so it must be honest about
the parts it can't price. This reports (a) the bundled pricing table's freshness,
and (b) every model in the ledger whose USD posting was computed with the
DEFAULT_COST fallback (an unknown/stale model), with how much guessed spend that
accounts for. Read-only. (Deep-audit P0-2.)
"""

from __future__ import annotations

import click

from forecost.ledger.db import get_ledger_db
from forecost.ledger.sink import PRICING_SNAPSHOT_VERSION, UNPRICED_SUFFIX
from forecost.pricing import DEFAULT_COST


@click.command("pricing-audit")
@click.option("--currency", default="USD")
def pricing_audit(currency):
    """Report unknown/guessed-price models in the ledger and table freshness."""
    conn = get_ledger_db()
    click.echo(f"Pricing table: {PRICING_SNAPSHOT_VERSION}")
    click.echo(
        "  Anthropic rows verified 2026-07-17; OpenAI/Gemini/others last verified "
        "March 2026 (not re-verified)."
    )
    click.echo(
        f"  Unknown models fall back to a DEFAULT_COST guess of "
        f"${DEFAULT_COST['input']:.2f}/${DEFAULT_COST['output']:.2f} per MTok.\n"
    )

    rows = conn.execute(
        """
        SELECT e.model AS model, COUNT(DISTINCT e.id) AS n,
               COALESCE(SUM(p.amount), 0) AS guessed_usd
        FROM usage_events e
        JOIN postings p ON p.event_id = e.id
        WHERE p.currency = ? AND p.basis = 'pricing_table'
          AND p.pricing_version LIKE ?
        GROUP BY e.model ORDER BY guessed_usd DESC
        """,
        (currency, f"%{UNPRICED_SUFFIX}"),
    ).fetchall()

    if not rows:
        click.echo(
            "No unpriced models in the ledger — every posting used a real table rate. "
            "(Empty ledger? Run `forecost ingest` first.)"
        )
        return

    total = sum(r["guessed_usd"] for r in rows)
    click.echo(
        f"{len(rows)} model(s) priced by GUESS "
        f"({currency} {total:.2f} of spend is not from a real rate):"
    )
    for r in rows:
        click.echo(f"  {r['model']:<40} n={r['n']:<6} {currency} {r['guessed_usd']:.2f} (guessed)")
    click.echo(
        "\nAdd real rates for these to forecost/pricing.py, or treat this spend as "
        "low-confidence. Budget rules should not hard-deny on guessed prices."
    )
