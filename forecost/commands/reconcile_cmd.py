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
the table rate effective at the event timestamp.
"""

from __future__ import annotations

from pathlib import Path

import click

from forecost.ledger.db import get_ledger_db
from forecost.pricing import calculate_cost
from forecost.reconciliation import import_bill_file, reconcile_run


def _percent_difference(actual: float, reference: float) -> float:
    if reference == 0:
        return 0.0 if actual == 0 else float("inf")
    return abs(actual - reference) / abs(reference) * 100


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
            as_of=r["ts"],
        )
        stored = r["amount"]
        pct_diff = _percent_difference(recomputed, stored)
        if pct_diff > tolerance_pct:
            drift_events.append((r["id"], r["model"], stored, recomputed, pct_diff))
        version = r["pricing_version"] or "unknown"
        pricing_versions_by_model.setdefault(r["model"], set()).add(version)
    return drift_events, pricing_versions_by_model


def _print_drift_report(drift_events, tolerance_pct):
    if not drift_events:
        click.echo(
            f"No drift beyond {tolerance_pct}% — every stored posting matches what the "
            "pricing table effective at its event timestamp would compute."
        )
        return
    click.echo(
        f"FLAGS ({len(drift_events)}) — stored amount vs. event-effective pricing disagrees "
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


def _print_source_vs_table_report(conn, currency, tolerance_pct):
    """The genuinely non-tautological check: for events that carry BOTH a
    source-reported cost (from a gateway) and forecost's own pricing_table cost,
    compare the two independent valuations of the same event. This is the meter
    audit the product exists to provide — forecost's number vs the gateway's."""
    rows = conn.execute(
        """
        SELECT e.model AS model,
               pt.amount AS table_amount,
               sr.amount AS source_amount
        FROM usage_events e
        JOIN postings pt ON pt.event_id = e.id
             AND pt.currency = ? AND pt.basis = 'pricing_table'
        JOIN postings sr ON sr.event_id = e.id
             AND sr.currency = ? AND sr.basis = 'source_reported'
        """,
        (currency, currency),
    ).fetchall()
    if not rows:
        click.echo(
            "\nNo events carry both a source-reported and a pricing_table cost yet "
            "(this cross-check activates for gateway sources like LiteLLM)."
        )
        return
    table_total = sum(r["table_amount"] for r in rows)
    source_total = sum(r["source_amount"] for r in rows)
    disagreements = [
        r
        for r in rows
        if _percent_difference(r["table_amount"], r["source_amount"]) > tolerance_pct
    ]
    click.echo(
        f"\nSource-reported vs forecost pricing_table on {len(rows)} shared events: "
        f"gateway {currency} {source_total:.2f} vs forecost {currency} {table_total:.2f} "
        f"({len(disagreements)} disagree by >{tolerance_pct}%)."
    )
    for r in disagreements[:20]:
        click.echo(
            f"  {r['model']}: gateway={r['source_amount']:.4f} vs forecost={r['table_amount']:.4f}"
        )


@click.group(invoke_without_command=True)
@click.option("--currency", default="USD")
@click.option("--tolerance-pct", default=3.0, help="Yellow-flag threshold, percent")
@click.pass_context
def reconcile(ctx: click.Context, currency: str, tolerance_pct: float) -> None:
    """Cross-check internal valuations, or import/reconcile independent evidence."""
    if ctx.invoked_subcommand is not None:
        return
    conn = get_ledger_db()
    rows = conn.execute(
        """
        SELECT e.id, e.ts, e.model, e.tokens_in, e.tokens_out, e.tokens_cache_read,
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
    _print_source_vs_table_report(conn, currency, tolerance_pct)

    click.echo(
        "\nFor independent offline evidence, use `forecost reconcile import` then "
        "`forecost reconcile run`. Live HTTP/API ingestion remains deliberately deferred."
    )


@reconcile.command("import")
@click.option(
    "--source", type=click.Choice(["openai", "anthropic", "gateway", "otel"]), required=True
)
@click.option("--file", "file_path", type=click.Path(exists=True, dir_okay=False), required=True)
@click.option("--run", "run_id", default=None, help="Attach aggregate evidence to an existing run.")
def import_export(source: str, file_path: str, run_id: str | None) -> None:
    """Import a representative local provider/gateway/OTel JSON or CSV export."""
    try:
        imported_run, imported = import_bill_file(
            get_ledger_db(),
            Path(file_path),
            source,
            run_id=run_id,
        )
    except ValueError as error:
        raise click.ClickException(str(error)) from error
    click.echo(f"Imported {imported} {source} billing record(s) into {imported_run}.")


@reconcile.command("run")
@click.option(
    "--run", "run_id", default=None, help="Run to reconcile; omit for all imported evidence."
)
@click.option("--tolerance-micros", default=1_000, show_default=True, type=click.IntRange(0))
@click.option("--json-output", "json_output", is_flag=True)
def reconcile_evidence(run_id: str | None, tolerance_micros: int, json_output: bool) -> None:
    """Compare local valuations with provider-billed aggregate evidence."""
    try:
        result = reconcile_run(get_ledger_db(), run_id, tolerance_micros=tolerance_micros)
    except ValueError as error:
        raise click.ClickException(str(error)) from error
    if json_output:
        import json

        click.echo(json.dumps(result, sort_keys=True, separators=(",", ":")))
        return
    click.echo(
        f"Reconciliation {result['state']}: local={result['local_total']} micros, "
        f"provider={result['provider_total']} micros, residual={result['residual']} micros."
    )
    click.echo(
        f"Evidence: {result['observed']} of {result['expected']} source roles; "
        f"finality={result['finality']}."
    )
