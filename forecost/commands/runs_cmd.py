"""Public views over graph-aware runs in the canonical evidence ledger."""

from __future__ import annotations

import sqlite3
from typing import cast

import click

from forecost.ledger.db import get_ledger_db
from forecost.ledger.receipts import build_receipt


@click.group()
def runs() -> None:
    """List and inspect graph-aware agent runs in the local ledger."""


def _claim_states(evidence: dict[str, object]) -> str:
    profiles = evidence.get("claim_profiles", {})
    if not isinstance(profiles, dict):
        return "none"
    return ",".join(
        f"{profile_id}:{value.get('state', 'unknown')}"
        for profile_id, value in sorted(profiles.items())
        if isinstance(value, dict)
    )


def _blind_spot_count(evidence: dict[str, object]) -> int:
    blind_spots = evidence.get("known_blind_spots", [])
    return len(blind_spots) if isinstance(blind_spots, list) else 0


def _economic_authorities(receipt: dict[str, object]) -> str:
    totals = cast(dict[str, dict[str, int]], receipt["economic_totals_micros"])
    return (
        ",".join(sorted(authority for values in totals.values() for authority in values)) or "none"
    )


def _run_line(row: sqlite3.Row, receipt: dict[str, object]) -> str:
    evidence = cast(dict[str, object], receipt["evidence"])
    outcome = cast(dict[str, object], receipt["outcome"])
    return (
        f"{row['run_id']}  {row['lifecycle']} claims={_claim_states(evidence)} "
        f"(blind_spots={_blind_spot_count(evidence)}) "
        f"outcome={outcome['status']} authorities={_economic_authorities(receipt)}"
    )


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
        click.echo(_run_line(row, receipt))


def _validated_graph(receipt: dict[str, object]) -> list[dict[str, object]]:
    graph = receipt["causal_graph"]
    if not isinstance(graph, list):  # pragma: no cover - receipt contract
        raise click.ClickException("invalid receipt graph")
    if any(not isinstance(span, dict) for span in graph):
        raise click.ClickException("invalid receipt graph")
    return cast(list[dict[str, object]], graph)


def _spans_by_parent(
    graph: list[dict[str, object]],
) -> dict[str | None, list[dict[str, object]]]:
    by_parent: dict[str | None, list[dict[str, object]]] = {}
    for span in graph:
        parent = cast(str | None, span.get("parent_span_key"))
        by_parent.setdefault(parent, []).append(span)
    return by_parent


def _render_graph(
    by_parent: dict[str | None, list[dict[str, object]]],
    parent: str | None,
    depth: int,
) -> None:
    for span in by_parent.get(parent, []):
        retry = f" retry-of={span['attempt_of_span_id']}" if span["attempt_of_span_id"] else ""
        click.echo(
            f"{'  ' * depth}- {span['operation_kind']} {span['lifecycle']} "
            f"branch={span['branch_id']}{retry} [{span['span_id']}]"
        )
        _render_graph(by_parent, str(span["span_key"]), depth + 1)


def _timing_line(timing: object) -> str:
    if isinstance(timing, dict) and all(
        timing.get(key) is not None for key in ("service", "wait", "elapsed")
    ):
        critical_path = timing.get("critical_path")
        basis = str(timing.get("basis", ""))
        if critical_path is not None:
            critical_text = f"{critical_path}us (trivial one-span case)"
        elif "causal_cycle" in basis:
            critical_text = "withheld (causal cycle)"
        else:
            critical_text = "withheld (untyped scheduling dependencies)"
        return (
            "Timing (explicit interval unions; service/wait are not additive): "
            f"service {timing['service']}us; wait {timing['wait']}us; "
            f"elapsed {timing['elapsed']}us; critical path {critical_text}."
        )
    state = timing.get("state", "unknown") if isinstance(timing, dict) else "unknown"
    return (
        f"Timing: {state}; critical path/service/wait/elapsed are not claimed without "
        "complete explicit span intervals."
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
    by_parent = _spans_by_parent(_validated_graph(receipt))
    click.echo(f"Run: {receipt['run_id']}")
    _render_graph(by_parent, None, 0)
    click.echo(_timing_line(receipt["timing_micros"]))
