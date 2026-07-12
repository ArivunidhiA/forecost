import click

from forecost.adapters.claude_code import ClaudeCodeAdapter
from forecost.ledger.db import get_ledger_db
from forecost.ledger.sink import SyncLedgerSink
from forecost.ledger.state_store import LedgerIngestStateStore


@click.command()
@click.option("--claude-dir", default=None, help="Override ~/.claude/projects")
def ingest(claude_dir):
    """Pull new usage events from Claude Code transcripts into the ledger."""
    conn = get_ledger_db()
    state = LedgerIngestStateStore(conn)
    sink = SyncLedgerSink()

    from pathlib import Path

    adapter = ClaudeCodeAdapter(claude_dir=Path(claude_dir) if claude_dir else None)
    n = adapter.poll(state, sink)
    sink.flush()
    click.echo(f"Ingested {n} new usage events.")

    from forecost.estimate.calibration import reconcile_estimates

    scored = reconcile_estimates(conn)
    if scored:
        click.echo(f"Reconciled {scored} pending estimate(s) against actuals.")
