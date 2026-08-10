"""forecost doctor — one-glance setup check and known-gaps report."""

from __future__ import annotations

import os
import re
from pathlib import Path

import click

from forecost import __version__
from forecost.core.paths import forecost_home
from forecost.ledger import queries as q
from forecost.ledger.db import get_ledger_db
from forecost.ledger.sink import PRICING_SNAPSHOT_VERSION

_ALL_TIME = "1970-01-01T00:00:00+00:00"
_SPOOL_NAME = re.compile(r"(?:legacy-)?recovery\.\d+\.\d+\.[0-9a-f]{32}\.jsonl")


def _doctor_payload(home: Path, conn) -> dict[str, object]:
    spend = q.scope_spend(conn, "USD", _ALL_TIME)
    claude_observations = conn.execute(
        "SELECT COUNT(*) FROM usage_events WHERE source LIKE 'claude%'"
    ).fetchone()[0]
    resource_scopes = conn.execute("SELECT COUNT(*) FROM resource_scopes").fetchone()[0]
    billed_charges = conn.execute(
        "SELECT COUNT(*) FROM charges WHERE authority = 'billed'"
    ).fetchone()[0]
    return {
        "schema_version": 1,
        "version": __version__,
        "home": str(home),
        "home_exists": home.exists(),
        "stores": {
            "canonical": {
                "path": str(home / "ledger.db"),
                "role": "supported receipt ledger",
            },
            "legacy": {
                "path": str(home / "costs.db"),
                "role": "unsupported v0.2 compatibility",
                "present": (home / "costs.db").exists(),
            },
        },
        "pricing_table": PRICING_SNAPSHOT_VERSION,
        "ledger": {
            "usage_events": conn.execute("SELECT COUNT(*) FROM usage_events").fetchone()[0],
            "canonical_usd_spend": spend.total,
            "unpriced_events": spend.n_unpriced_events,
            "receipt_runs": conn.execute("SELECT COUNT(*) FROM causal_runs").fetchone()[0],
            "receipt_snapshots": conn.execute("SELECT COUNT(*) FROM receipt_snapshots").fetchone()[
                0
            ],
        },
        "readiness": {
            "claude_code": "OBSERVED" if claude_observations else "NOT OBSERVED",
            "resource_envelope": "OBSERVED" if resource_scopes else "NOT OBSERVED",
            "provider_billing": "OBSERVED" if billed_charges else "NOT OBSERVED",
            "distributed_enforcement": "NOT OBSERVED",
        },
        "limitations": [
            "Claude Code hooks are fail-open local observation, not provider-side containment.",
            "Provider-billed authority requires an imported local export.",
            "Legacy costs.db is never read by current receipt or MCP queries.",
        ],
    }


def _echo_home(home: Path) -> None:
    override = os.environ.get("FORECOST_HOME")
    click.echo(f"forecost {__version__}")
    click.echo(f"  home: {home}" + (" (via FORECOST_HOME)" if override else " (default)"))
    click.echo(f"  home exists: {home.exists()}")
    click.echo(f"  pricing table: {PRICING_SNAPSHOT_VERSION}")


def _echo_ledger(conn) -> None:
    n_events = conn.execute("SELECT COUNT(*) FROM usage_events").fetchone()[0]
    spend = q.scope_spend(conn, "USD", _ALL_TIME)
    n_recon = conn.execute("SELECT COUNT(*) FROM reconciliations").fetchone()[0]
    click.echo(
        f"  canonical ledger.db: {n_events} events, USD {spend.total:.2f} valuation, "
        f"{n_recon} reconciled"
    )
    if spend.n_unpriced_events:
        click.echo(
            f"  ⚠ includes USD {spend.unpriced_total:.2f} guessed across "
            f"{spend.n_unpriced_events} event(s); guesses never trigger hard denials"
        )


def _pending_lines(path) -> int:
    if not path.exists() or path.stat().st_size == 0:
        return 0
    with path.open(encoding="utf-8") as recovery_file:
        return sum(1 for line in recovery_file if line.strip())


def _echo_recovery(home) -> None:
    recovery_files = {home / "recovery.jsonl", home / "legacy-recovery.jsonl"}
    recovery_files.update(home.glob("recovery.*.jsonl"))
    recovery_files.update(home.glob("legacy-recovery.*.jsonl"))
    recovery_files = {
        path
        for path in recovery_files
        if path.name in {"recovery.jsonl", "legacy-recovery.jsonl"}
        or _SPOOL_NAME.fullmatch(path.name)
    }
    pending = sum(_pending_lines(path) for path in recovery_files)
    if pending:
        click.echo(f"  ⚠ recovery queues have {pending} pending record(s) — run `forecost recover`")
    else:
        click.echo("  recovery: clean (no pending spills)")

    legacy = home / "costs.db"
    if legacy.exists():
        click.echo(
            "  legacy costs.db: present (unsupported v0.2 store; never queried by receipts/MCP)"
        )
    else:
        click.echo("  legacy costs.db: absent")


def _echo_limitations() -> None:
    click.echo("\nKnown limitations:")
    click.echo("  - Marketplace plugin bootstrap is currently supported on macOS/Linux.")
    click.echo("  - Estimator stays in shadow mode until calibration gates pass (see")
    click.echo("    `forecost calibration`).")
    click.echo(
        "  - Repo-local .forecost.toml is ignored for enforcement unless "
        "FORECOST_TRUST_PROJECT_POLICY=1."
    )
    click.echo("  - Local controls do not bound provider-side or distributed overrun.")


@click.command()
@click.option("--json", "json_output", is_flag=True, help="Emit stable machine-readable readiness.")
def doctor(json_output: bool) -> None:
    """Report where forecost keeps data, what's ingested, and known gaps."""
    if json_output:
        import json

        home = forecost_home()
        click.echo(
            json.dumps(
                _doctor_payload(home, get_ledger_db()), sort_keys=True, separators=(",", ":")
            )
        )
        return
    home = forecost_home()
    _echo_home(home)
    _echo_ledger(get_ledger_db())
    _echo_recovery(home)
    _echo_limitations()
