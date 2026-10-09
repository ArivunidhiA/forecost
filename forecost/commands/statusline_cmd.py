"""Field-allowlisted, fail-open Claude statusline renderer."""

from __future__ import annotations

from datetime import datetime, timezone

import click

from forecost.hooks.state import pending_settlements, read_heartbeat, read_summary
from forecost.ledger.db import get_ledger_db


def _age_seconds(value: object) -> int | None:
    if not isinstance(value, str):
        return None
    try:
        observed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if observed.tzinfo is None:
        return None
    return max(0, int((datetime.now(timezone.utc) - observed).total_seconds()))


def render_statusline() -> str:
    heartbeat = read_heartbeat()
    pending = pending_settlements()
    if heartbeat is None:
        protection = "NOT OBSERVED"
        freshness = "never"
    else:
        age = _age_seconds(heartbeat.get("observed_at"))
        freshness = "unknown" if age is None else f"{age}s"
        protection = "degraded" if age is None or age > 300 else str(heartbeat.get("readiness"))
    conn = get_ledger_db()
    settled = conn.execute(
        "SELECT COALESCE(SUM(settled_micros), 0) FROM resource_scopes"
    ).fetchone()[0]
    reserved = conn.execute(
        "SELECT COALESCE(SUM(reserved_micros), 0) FROM resource_scopes"
    ).fetchone()[0]
    runs = conn.execute("SELECT COUNT(*) FROM causal_runs").fetchone()[0]
    summary = read_summary() or {}
    progress = summary.get("estimates_reconciled", 0)
    return (
        f"forecost {protection} · evidence {freshness} · runs {runs} · "
        f"settled/reserved {settled}/{reserved}µ · verified {progress} · pending {pending}"
    )


@click.command()
def statusline() -> None:
    """Render one bounded status line; blank on internal failure."""
    try:
        click.echo(render_statusline())
    except Exception:  # nosec B110 - statusline must never disturb the host
        return
