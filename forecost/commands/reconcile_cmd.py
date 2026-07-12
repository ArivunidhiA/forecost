"""forecost reconcile — the trust credential (BASEMENT.md §3).

v0 scope (honest about what's implemented vs. deferred): cross-checking the
ledger against external sources (Anthropic Admin API, LiteLLM Postgres,
OpenRouter's /api/v1/generation) requires those adapters and real API
credentials — that is Phase 3 scope (round3-architecture.md §3.4, adapters
2-3) and cannot be built or tested without a live account. What v0 CAN do
honestly, with data already on this machine: verify internal consistency of
the ledger itself — flag any model whose pricing_version varies across its
own postings (evidence of a pricing snapshot change mid-history, which is
exactly the kind of drift that makes numbers hard to trust) and recompute
each posting from its event's raw tokens to confirm the stored amount matches
what the current pricing table would produce for it right now.
"""

from __future__ import annotations

import click

from forecost.ledger.db import get_ledger_db
from forecost.pricing import calculate_cost


def _analyze_rows(rows, tolerance_pct):
    """Recompute each stored posting from its raw tokens; return (drift_events,
    pricing_versions_by_model)."""
    drift_events = []
    pricing_versions_by_model: dict[str, set[str]] = {}
    for r in rows:
        recomputed = calculate_cost(
            r["model"],
            r["tokens_in"],
            r["tokens_out"],
            r["tokens_cache_read"],
            r["tokens_cache_write"],
        )
        stored = r["amount"]
        if stored > 0:
            pct_diff = abs(recomputed - stored) / stored * 100
        else:
            pct_diff = 0.0 if recomputed == 0 else 100.0
        if pct_diff > tolerance_pct:
            drift_events.append((r["id"], r["model"], stored, recomputed, pct_diff))
        version = r["pricing_version"] or "unknown"
        pricing_versions_by_model.setdefault(r["model"], set()).add(version)
    return drift_events, pricing_versions_by_model


def _print_drift_report(drift_events, tolerance_pct):
    if not drift_events:
        click.echo(
            f"No drift beyond {tolerance_pct}% — every stored posting matches what the "
            "current pricing table would compute today."
        )
        return
    click.echo(
        f"FLAGS ({len(drift_events)}) — stored amount vs. current pricing table disagrees "
        f"by more than {tolerance_pct}%:"
    )
    for event_id, model, stored, recomputed, pct in drift_events[:20]:
        click.echo(
            f"  event {event_id} ({model}): stored={stored:.4f} "
            f"vs current-table={recomputed:.4f} ({pct:.1f}% drift)"
        )
    if len(drift_events) > 20:
        click.echo(f"  ... and {len(drift_events) - 20} more")
    click.echo(
        "\n  Likely cause: the pricing table changed since these events were ingested. "
        "This is exactly the kind of provenance question `pricing_version` exists to answer."
    )


def _print_multi_version_report(pricing_versions_by_model):
    multi_version = {m: v for m, v in pricing_versions_by_model.items() if len(v) > 1}
    if not multi_version:
        return
    click.echo(
        f"\n{len(multi_version)} model(s) priced under more than one pricing_version "
        "(their price changed mid-history):"
    )
    for model, versions in multi_version.items():
        click.echo(f"  {model}: {sorted(versions)}")


@click.command()
@click.option("--currency", default="USD")
@click.option("--tolerance-pct", default=3.0, help="Yellow-flag threshold, percent")
def reconcile(currency, tolerance_pct):
    """Cross-check the ledger's internal consistency (external sources: Phase 3)."""
    conn = get_ledger_db()
    rows = conn.execute(
        """
        SELECT e.id, e.model, e.tokens_in, e.tokens_out, e.tokens_cache_read,
               e.tokens_cache_write, p.amount, p.pricing_version, p.basis
        FROM usage_events e
        JOIN postings p ON p.event_id = e.id
        WHERE p.currency = ? AND p.basis = 'pricing_table'
        """,
        (currency,),
    ).fetchall()

    if not rows:
        click.echo(
            f"No {currency} pricing_table postings to reconcile yet. Run `forecost ingest` first."
        )
        return

    drift_events, pricing_versions_by_model = _analyze_rows(rows, tolerance_pct)

    total_stored = sum(r["amount"] for r in rows)
    click.echo(
        f"Reconciling {len(rows)} {currency} pricing_table postings "
        f"(stored total: {currency} {total_stored:.2f})\n"
    )
    _print_drift_report(drift_events, tolerance_pct)
    _print_multi_version_report(pricing_versions_by_model)

    click.echo(
        "\nExternal cross-checks (Anthropic Admin API, LiteLLM, OpenRouter) are not wired up "
        "yet — that requires per-source adapters and real credentials (Phase 3)."
    )
