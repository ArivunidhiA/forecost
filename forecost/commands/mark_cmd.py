"""Explicit, bounded outcome marks for a completed or incomplete run."""

from __future__ import annotations

from datetime import datetime, timezone

import click

from forecost.ledger.contracts import CausalIdentity, opaque_id
from forecost.ledger.db import get_ledger_db
from forecost.ledger.evidence import append_observation, observation

_REASONS = click.Choice(
    ["human_assessment", "tests_passed", "tests_failed", "build_passed", "build_failed", "reverted"]
)


@click.command()
@click.argument("run_id")
@click.argument("status", type=click.Choice(["good", "bad", "partial"]))
@click.option("--reason", type=_REASONS, default=None)
def mark(run_id: str, status: str, reason: str | None) -> None:
    """Attach an explicit outcome observation; it never rewrites prior evidence."""
    conn = get_ledger_db()
    normalized_run = opaque_id("run", run_id)
    row = conn.execute(
        "SELECT * FROM causal_spans WHERE run_id = ? ORDER BY source_order LIMIT 1",
        (normalized_run,),
    ).fetchone()
    if row is None:
        raise click.ClickException("run not found")
    sequence = conn.execute(
        "SELECT COALESCE(MAX(source_sequence), 0) + 1 FROM journal_observations WHERE producer = ?",
        (opaque_id("producer", "manual_mark"),),
    ).fetchone()[0]
    causal = CausalIdentity(
        conversation_id=row["conversation_id"],
        trace_id=row["trace_id"],
        run_id=normalized_run,
        span_id=row["span_id"],
        source_sequence=sequence,
        idempotency_key=f"manual-mark-{status}-{reason or 'none'}-{sequence}",
    )
    append_observation(
        conn,
        observation(
            producer="manual_mark",
            event_kind="outcome",
            causal=causal,
            payload={
                "outcome_status": status,
                "reason_code": reason,
                "evidence_type": "explicit_mark",
                "confidence": "explicit",
            },
            occurred_at=datetime.now(timezone.utc),
        ),
    )
    click.echo(f"Recorded {status} outcome evidence for {normalized_run}.")
