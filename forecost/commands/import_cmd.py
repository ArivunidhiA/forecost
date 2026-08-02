"""Offline content-free runtime imports, beginning with OTel-style span fixtures."""

from __future__ import annotations

import json
from collections.abc import Mapping
from pathlib import Path

import click

from forecost.adapters.causal import runtime_span_observation
from forecost.ledger.db import get_ledger_db
from forecost.ledger.evidence import append_observation


@click.group(name="import")
def import_data() -> None:
    """Import content-free runtime evidence from local files only."""


@import_data.command("otel")
@click.option("--file", "file_path", type=click.Path(exists=True, dir_okay=False), required=True)
@click.option("--producer", default="otel", show_default=True)
def import_otel(file_path: str, producer: str) -> None:
    """Import a JSON array of structural OTel/GenAI span fixtures.

    Each item needs conversation_id, trace_id, run_id, span_id,
    idempotency_key, and occurred_at. Attributes and payload-shaped fields are
    deliberately ignored by the mapper.
    """
    try:
        decoded = json.loads(Path(file_path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise click.ClickException("cannot read OTel JSON fixture") from error
    if not isinstance(decoded, list) or not all(isinstance(item, Mapping) for item in decoded):
        raise click.ClickException("OTel fixture must be a JSON array of objects")
    conn = get_ledger_db()
    inserted = 0
    for index, item in enumerate(decoded, start=1):
        try:
            if append_observation(conn, runtime_span_observation(item, producer=producer)):
                inserted += 1
        except ValueError as error:
            raise click.ClickException(f"invalid OTel fixture record {index}: {error}") from error
    click.echo(f"Imported {inserted} OTel span observation(s).")
