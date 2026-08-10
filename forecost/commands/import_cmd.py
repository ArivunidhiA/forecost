"""Offline content-free runtime imports, beginning with OTel-style span fixtures."""

from __future__ import annotations

import click

from forecost.adapters.otel import load_records, otel_observations
from forecost.ledger.db import get_ledger_db
from forecost.ledger.evidence import append_observation


@click.group(name="import")
def import_data() -> None:
    """Import content-free runtime evidence from local files only."""


@import_data.command("otel")
@click.option(
    "--file",
    "input_file",
    type=click.File("r", encoding="utf-8"),
    default="-",
    show_default="stdin",
)
@click.option("--producer", default="otel", show_default=True)
def import_otel(input_file, producer: str) -> None:
    """Import structural OTel/GenAI spans and metrics from JSON/JSONL/stdin.

    Each item needs conversation_id, trace_id, run_id, span_id,
    idempotency_key, and occurred_at. Attributes and payload-shaped fields are
    deliberately ignored by the mapper.
    """
    try:
        observations = otel_observations(load_records(input_file), producer=producer)
    except (OSError, ValueError) as error:
        raise click.ClickException(f"cannot import OTel evidence: {error}") from error
    conn = get_ledger_db()
    inserted = 0
    for index, item in enumerate(observations, start=1):
        try:
            if append_observation(conn, item):
                inserted += 1
        except ValueError as error:
            raise click.ClickException(f"invalid OTel observation {index}: {error}") from error
    click.echo(f"Imported {inserted} OTel observation(s).")
