"""Stable receipt renderers and evidence diff."""

from __future__ import annotations

import json
from typing import cast

import click

from forecost.ledger.db import get_ledger_db
from forecost.ledger.receipts import build_receipt, receipt_text, save_receipt

_RECEIPT_FLAGS = frozenset({"--json-output", "--markdown", "--no-color"})


def _reorder_receipt_args(args: list[str]) -> list[str]:
    flags = [arg for arg in args[1:] if arg in _RECEIPT_FLAGS]
    remainder = [arg for arg in args[1:] if arg not in _RECEIPT_FLAGS]
    return [*flags, args[0], *remainder]


class ReceiptGroup(click.Group):
    """Permit the ergonomic ``receipt RUN_ID --json-output`` spelling.

    Click otherwise switches into subcommand parsing after the positional run
    argument and treats a trailing group option as a command name.
    """

    def parse_args(self, ctx: click.Context, args: list[str]) -> list[str]:
        if args and args[0] != "diff" and not args[0].startswith("-"):
            args[:] = _reorder_receipt_args(args)
        return super().parse_args(ctx, args)


def _validated_run_id(run_id: str | None, json_output: bool, markdown: bool) -> str:
    if run_id is None:
        raise click.UsageError("missing RUN_ID")
    if json_output and markdown:
        raise click.UsageError("--json-output and --markdown cannot be used together")
    return run_id


def _load_receipt(run_id: str) -> dict[str, object]:
    conn = get_ledger_db()
    try:
        result = build_receipt(conn, run_id)
    except ValueError as error:
        raise click.ClickException(str(error)) from error
    save_receipt(conn, result)
    return result


def _render_receipt(result: dict[str, object], json_output: bool, markdown: bool) -> None:
    if json_output:
        click.echo(json.dumps(result, sort_keys=True, separators=(",", ":")))
    else:
        click.echo(receipt_text(result, markdown=markdown), nl=False)


@click.group(cls=ReceiptGroup, invoke_without_command=True)
@click.argument("run_id", required=False)
@click.option("--json-output", "json_output", is_flag=True, help="Emit stable JSON.")
@click.option("--markdown", is_flag=True, help="Render a Markdown artifact.")
@click.option(
    "--no-color",
    is_flag=True,
    help="Compatibility flag; receipt output is always deterministic plain text.",
)
@click.pass_context
def receipt(
    ctx: click.Context,
    run_id: str | None,
    json_output: bool,
    markdown: bool,
    no_color: bool,
) -> None:
    """Render a versioned economic receipt, or compare two receipts."""
    if ctx.invoked_subcommand is not None:
        return
    del no_color  # output is intentionally never ANSI-colored
    selected_run = _validated_run_id(run_id, json_output, markdown)
    _render_receipt(_load_receipt(selected_run), json_output, markdown)


@receipt.command("diff")
@click.argument("run_a")
@click.argument("run_b")
@click.option("--json-output", "json_output", is_flag=True)
def diff(run_a: str, run_b: str, json_output: bool) -> None:
    """Compare graph shape, selected valuations, and outcome evidence."""
    conn = get_ledger_db()
    try:
        left = build_receipt(conn, run_a)
        right = build_receipt(conn, run_b)
    except ValueError as error:
        raise click.ClickException(str(error)) from error
    left_graph = cast(list[object], left["causal_graph"])
    right_graph = cast(list[object], right["causal_graph"])
    left_outcome = cast(dict[str, object], left["outcome"])
    right_outcome = cast(dict[str, object], right["outcome"])
    result = {
        "schema_version": 1,
        "run_a": run_a,
        "run_b": run_b,
        "span_count": {"a": len(left_graph), "b": len(right_graph)},
        "timing_micros": {"a": left["timing_micros"], "b": right["timing_micros"]},
        "economic_totals_micros": {
            "a": left["economic_totals_micros"],
            "b": right["economic_totals_micros"],
        },
        "outcome": {"a": left_outcome, "b": right_outcome},
    }
    if json_output:
        click.echo(json.dumps(result, sort_keys=True, separators=(",", ":")))
        return
    click.echo(f"Spans: {len(left_graph)} -> {len(right_graph)}")
    click.echo(f"Outcome: {left_outcome['status']} -> {right_outcome['status']}")
    click.echo("Economic totals are expressed in integer micros; use --json-output for full diff.")
