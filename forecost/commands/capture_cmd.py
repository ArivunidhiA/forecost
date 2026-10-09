"""Run a local verification command and record bounded exit evidence."""

from __future__ import annotations

import hashlib
import subprocess  # nosec B404 - explicit local command runner; shell is never used
from datetime import datetime, timezone

import click

from forecost.ledger.contracts import CausalIdentity, opaque_id
from forecost.ledger.db import get_ledger_db
from forecost.ledger.evidence import append_observation, observation


def _append_outcome(
    *,
    run_id: str,
    status: str,
    reason: str,
    evidence_type: str,
    nonce: str,
) -> None:
    conn = get_ledger_db()
    normalized_run = opaque_id("run", run_id)
    row = conn.execute(
        "SELECT * FROM causal_spans WHERE run_id = ? ORDER BY source_order LIMIT 1",
        (normalized_run,),
    ).fetchone()
    if row is None:
        raise click.ClickException("run not found")
    producer = opaque_id("producer", "local_verification")
    sequence = conn.execute(
        "SELECT COALESCE(MAX(source_sequence), 0) + 1 FROM journal_observations WHERE producer = ?",
        (producer,),
    ).fetchone()[0]
    causal = CausalIdentity(
        conversation_id=row["conversation_id"],
        trace_id=row["trace_id"],
        run_id=normalized_run,
        span_id=row["span_id"],
        source_sequence=sequence,
        idempotency_key=f"local-verification-{nonce}-{sequence}",
    )
    append_observation(
        conn,
        observation(
            producer="local_verification",
            event_kind="outcome",
            causal=causal,
            payload={
                "outcome_status": status,
                "reason_code": reason,
                "evidence_type": evidence_type,
                "confidence": "observed",
            },
            occurred_at=datetime.now(timezone.utc),
        ),
    )


def _git_head() -> str | None:
    result = subprocess.run(  # nosec B603 - fixed absolute git command
        ["/usr/bin/git", "rev-parse", "--verify", "HEAD"],
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        return None
    value = result.stdout.strip()
    return value if value else None


@click.command(context_settings={"ignore_unknown_options": True})
@click.argument("run_id")
@click.option("--kind", type=click.Choice(["test", "build"]), required=True)
@click.argument("command", nargs=-1, type=click.UNPROCESSED)
def capture(run_id: str, kind: str, command: tuple[str, ...]) -> None:
    """Run COMMAND and attach its exit status to RUN_ID without storing output.

    COMMAND is executed directly (never through a shell). Its output remains on
    the terminal; Forecost persists only the kind, exit class, time, and an
    irreversible identity for the observed Git HEAD when available.
    """
    if not command:
        raise click.UsageError("missing COMMAND")
    try:
        result = subprocess.run(  # noqa: S603  # nosec B603 - explicit user command, no shell
            command, check=False
        )
    except OSError as error:
        raise click.ClickException(f"could not execute command: {error.strerror}") from error
    status = "good" if result.returncode == 0 else "bad"
    reason = f"{kind}_{'passed' if result.returncode == 0 else 'failed'}"
    digest = hashlib.sha256("\0".join(command).encode("utf-8", errors="replace")).hexdigest()
    _append_outcome(
        run_id=run_id,
        status=status,
        reason=reason,
        evidence_type=f"{kind}_exit",
        nonce=f"{kind}-{result.returncode}-{digest}",
    )
    head = _git_head()
    if head is not None:
        _append_outcome(
            run_id=run_id,
            status="unknown",
            reason="git_head_observed",
            evidence_type="git_fact",
            nonce=f"git-{head}",
        )
    click.echo(f"Recorded {kind} exit {result.returncode} for {opaque_id('run', run_id)}.")
    if result.returncode != 0:
        raise click.exceptions.Exit(result.returncode)
