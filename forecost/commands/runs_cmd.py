"""Public views over graph-aware runs in the canonical evidence ledger."""

from __future__ import annotations

from typing import cast

import click

from forecost.ledger.db import get_ledger_db
from forecost.ledger.receipts import build_receipt


@click.group()
def runs() -> None:
    """List and inspect content-free agent runs."""


@runs.command("list")
@click.option("--limit", default=20, show_default=True, type=click.IntRange(1, 200))
def list_runs(limit: int) -> None:
    """Show lifecycle, evidence, outcome, and economic authority by run."""
    conn = get_ledger_db()
    rows = conn.execute(
        "SELECT run_id, lifecycle, created_at, observed_at FROM causal_runs "
        "ORDER BY observed_at DESC, run_id ASC LIMIT ?",
        (limit,),
    ).fetchall()
    if not rows:
        click.echo("No graph-aware runs yet. Try `forecost lab demo`.")
        return
    for row in rows:
        receipt = build_receipt(conn, row["run_id"])
        evidence = cast(dict[str, object], receipt["evidence"])
        outcome = cast(dict[str, object], receipt["outcome"])
        totals = cast(dict[str, dict[str, int]], receipt["economic_totals_micros"])
        authorities = (
            ",".join(
                sorted(authority for by_authority in totals.values() for authority in by_authority)
            )
            or "none"
        )
        click.echo(
            f"{row['run_id']}  {row['lifecycle']}  evidence={evidence['state']} "
            f"outcome={outcome['status']} authorities={authorities}"
        )


@runs.command("show")
@click.argument("run_id")
def show_run(run_id: str) -> None:
    """Show a compact DAG with branch/retry and timing information."""
    conn = get_ledger_db()
    try:
        receipt = build_receipt(conn, run_id)
    except ValueError as error:
        raise click.ClickException(str(error)) from error
    graph = receipt["causal_graph"]
    if not isinstance(graph, list):  # pragma: no cover - receipt contract
        raise click.ClickException("invalid receipt graph")
    by_parent: dict[str | None, list[dict[str, object]]] = {}
    for span in graph:
        if not isinstance(span, dict):
            raise click.ClickException("invalid receipt graph")
        by_parent.setdefault(span.get("parent_span_id"), []).append(span)

    def render(parent: str | None, depth: int) -> None:
        for span in by_parent.get(parent, []):
            retry = f" retry-of={span['attempt_of_span_id']}" if span["attempt_of_span_id"] else ""
            click.echo(
                f"{'  ' * depth}- {span['operation_kind']} {span['lifecycle']} "
                f"branch={span['branch_id']}{retry} [{span['span_id']}]"
            )
            render(str(span["span_id"]), depth + 1)

    click.echo(f"Run: {receipt['run_id']}")
    render(None, 0)
    timing = receipt["timing_micros"]
    click.echo(
        f"Critical path: {timing['critical_path']}us; service: {timing['service']}us; "  # type: ignore[index]
        f"wait: {timing['wait']}us"  # type: ignore[index]
    )
