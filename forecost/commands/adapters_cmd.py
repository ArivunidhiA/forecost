"""Adapter protocol diagnostics."""

from __future__ import annotations

import json

import click

from forecost.adapters.protocol import conformance_report


@click.group()
def adapters() -> None:
    """Inspect ingestion and enforcement adapter capabilities."""


@adapters.command("check")
@click.option("--json", "json_output", is_flag=True)
def check(json_output: bool) -> None:
    """Run deterministic offline adapter protocol conformance checks."""
    report = conformance_report()
    if json_output:
        click.echo(json.dumps(report, sort_keys=True, separators=(",", ":")))
        return
    for item in report["adapters"]:
        state = "PASS" if item["conformant"] else "FAIL"
        click.echo(
            f"{state} {item['name']}: {item['transport']}, "
            f"ceiling={item['readiness_ceiling']}, enforcement={item['enforcement_point']}"
        )
    click.echo(str(report["claim_boundary"]))
    if not report["conformant"]:
        raise click.ClickException("adapter protocol conformance failed")
