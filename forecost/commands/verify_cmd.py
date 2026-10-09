"""Verify the causal journal chain and persisted receipt snapshots."""

from __future__ import annotations

import hashlib
import json
import sqlite3
from typing import TypedDict

import click

from forecost.ledger.db import get_ledger_db
from forecost.ledger.integrity import verify_journal_chain


def _digest(payload: dict[str, object]) -> str:
    material = dict(payload)
    material.pop("integrity", None)
    encoded = json.dumps(material, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


class ReceiptVerification(TypedDict):
    state: str
    snapshot_count: int
    bad_receipt_ids: list[str]


def _verify_receipts(conn: sqlite3.Connection) -> ReceiptVerification:
    rows = conn.execute(
        "SELECT receipt_id, payload_json FROM receipt_snapshots ORDER BY receipt_id"
    ).fetchall()
    bad: list[str] = []
    for row in rows:
        try:
            payload = json.loads(row["payload_json"])
            integrity = payload.get("integrity", {})
            if integrity.get("algorithm") != "sha256" or integrity.get("payload_digest") != _digest(
                payload
            ):
                bad.append(row["receipt_id"])
        except (AttributeError, TypeError, json.JSONDecodeError):
            bad.append(row["receipt_id"])
    return {
        "state": "intact" if not bad else "rewritten",
        "snapshot_count": len(rows),
        "bad_receipt_ids": bad[:5],
    }


@click.command()
@click.option(
    "--json-output", "--json", "as_json", is_flag=True, help="Emit stable machine-readable JSON."
)
@click.pass_context
def verify(ctx: click.Context, as_json: bool) -> None:
    """Classify journal mutations and verify canonical receipt snapshots."""
    conn = get_ledger_db()
    journal = verify_journal_chain(conn)
    receipts = _verify_receipts(conn)
    result = {
        "journal": journal.to_dict(),
        "receipts": receipts,
        "overall_state": (
            "intact"
            if journal.state == "intact" and receipts["state"] == "intact"
            else journal.state
            if journal.state != "intact"
            else "rewritten"
        ),
    }
    if as_json:
        click.echo(json.dumps(result, sort_keys=True, separators=(",", ":")))
    else:
        click.echo(
            f"Integrity verify: {result['overall_state']} "
            f"(journal={journal.state}, events={journal.event_count}; "
            f"receipts={receipts['state']}, snapshots={receipts['snapshot_count']})."
        )
        click.echo(f"Threat boundary: {journal.threat_boundary}.")
    if result["overall_state"] != "intact":
        bad = receipts["bad_receipt_ids"]
        if bad:
            detail = f"rewritten or malformed receipt snapshot(s): {', '.join(bad)}"
        else:
            detail = f"journal {journal.state}: {journal.detail}"
        if as_json:
            ctx.exit(1)
        raise click.ClickException(detail)
