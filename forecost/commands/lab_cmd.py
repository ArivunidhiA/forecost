"""Offline Run Lab commands.  They always use an isolated ledger path."""

from __future__ import annotations

import tempfile
from pathlib import Path

import click

from forecost.lab import seed_chaos, seed_demo
from forecost.ledger.db import get_ledger_db
from forecost.ledger.receipts import build_receipt, receipt_text


def _lab_path(path: Path | None) -> Path:
    if path is not None:
        return path.expanduser().resolve()
    return Path(tempfile.mkdtemp(prefix="forecost-lab-")) / "ledger.db"


@click.group()
def lab() -> None:
    """Run deterministic synthetic scenarios with allowlisted receipt fields."""


@lab.command("demo")
@click.option("--seed", default=7, show_default=True, type=click.IntRange(0, 2**31 - 1))
@click.option("--ledger-path", type=click.Path(path_type=Path), default=None)
def demo(seed: int, ledger_path: Path | None) -> None:
    """Create a meaningful synthetic receipt without touching your Forecost home."""
    path = _lab_path(ledger_path)
    conn = get_ledger_db(path)
    run_id = seed_demo(conn, seed)
    click.echo(f"Run Lab ledger: {path}")
    click.echo(receipt_text(build_receipt(conn, run_id)), nl=False)


@lab.command("chaos")
@click.option("--seed", default=7, show_default=True, type=click.IntRange(0, 2**31 - 1))
@click.option("--branches", default=12, show_default=True, type=click.IntRange(1, 128))
@click.option("--ledger-path", type=click.Path(path_type=Path), default=None)
def chaos(seed: int, branches: int, ledger_path: Path | None) -> None:
    """Generate a deterministic fan-out/cancellation topology for replay tests."""
    path = _lab_path(ledger_path)
    conn = get_ledger_db(path)
    run_id = seed_chaos(conn, seed, branches)
    click.echo(f"Run Lab ledger: {path}")
    click.echo(f"Seed: {seed}; branches: {branches}; run: {run_id}")
