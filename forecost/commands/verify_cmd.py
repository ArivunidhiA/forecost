"""Verify persisted receipt snapshots against their canonical integrity digest."""

from __future__ import annotations

import hashlib
import json

import click

from forecost.ledger.db import get_ledger_db


def _digest(payload: dict[str, object]) -> str:
    material = dict(payload)
    material.pop("integrity", None)
    encoded = json.dumps(material, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


@click.command()
def verify() -> None:
    """Report whether stored receipt snapshots remain byte-integrity intact."""
    rows = get_ledger_db().execute(
        "SELECT receipt_id, payload_json FROM receipt_snapshots ORDER BY receipt_id"
    ).fetchall()
    bad: list[str] = []
    for row in rows:
        try:
            payload = json.loads(row["payload_json"])
            integrity = payload.get("integrity", {})
            if (
                integrity.get("algorithm") != "sha256"
                or integrity.get("payload_digest") != _digest(payload)
            ):
                bad.append(row["receipt_id"])
        except (AttributeError, TypeError, json.JSONDecodeError):
            bad.append(row["receipt_id"])
    if bad:
        raise click.ClickException(
            f"rewritten or malformed receipt snapshot(s): {', '.join(bad[:5])}"
        )
    click.echo(f"Integrity verify: intact ({len(rows)} receipt snapshot(s)).")
