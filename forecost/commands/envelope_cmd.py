"""Explicit local resource-envelope controls for offline and CI use."""

from __future__ import annotations

import click

from forecost.ledger.db import get_ledger_db
from forecost.resources import (
    AdmissionMode,
    ResourceDimension,
    create_scope,
    recover,
    release,
    reserve,
    settle,
)


@click.group()
def envelope() -> None:
    """Manage experimental single-host resource envelopes."""


@envelope.command("create")
@click.argument("scope")
@click.option(
    "--dimension", type=click.Choice([item.value for item in ResourceDimension]), required=True
)
@click.option("--capacity-micros", type=click.IntRange(0), required=True)
@click.option("--mode", type=click.Choice([item.value for item in AdmissionMode]), default="shadow")
def create(scope: str, dimension: str, capacity_micros: int, mode: str) -> None:
    """Create a scope. This is local-only, not provider-side enforcement."""
    result = create_scope(
        get_ledger_db(),
        scope,
        ResourceDimension(dimension),
        capacity_micros,
        mode=AdmissionMode(mode),
    )
    click.echo(f"Created {result.scope_id}; available={result.available_micros} micros.")


@envelope.command("reserve")
@click.argument("scope")
@click.option("--amount-micros", type=click.IntRange(0), required=True)
@click.option("--key", "idempotency_key", required=True)
@click.option("--ttl-seconds", type=click.IntRange(0), default=None)
def reserve_capacity(
    scope: str, amount_micros: int, idempotency_key: str, ttl_seconds: int | None
) -> None:
    """Atomically reserve capacity and print its fencing token."""
    result = reserve(
        get_ledger_db(), scope, amount_micros, idempotency_key, ttl_seconds=ttl_seconds
    )
    click.echo(
        f"{result.state}: {result.reservation_id} granted={result.granted_micros} "
        f"fence={result.fencing_token}"
    )


@envelope.command("settle")
@click.argument("reservation_id")
@click.option("--used-micros", type=click.IntRange(0), required=True)
def settle_capacity(reservation_id: str, used_micros: int) -> None:
    """Commit consumption and return unused capacity."""
    result = settle(get_ledger_db(), reservation_id, used_micros)
    click.echo(f"{result.state}: {result.reservation_id} used={used_micros}")


@envelope.command("release")
@click.argument("reservation_id")
def release_capacity(reservation_id: str) -> None:
    """Return a live reservation without spending it."""
    result = release(get_ledger_db(), reservation_id)
    click.echo(f"{result.state}: {result.reservation_id}")


@envelope.command("recover")
def recover_capacity() -> None:
    """Expire leases left live by a crashed process."""
    results = recover(get_ledger_db())
    click.echo(f"Expired {len(results)} reservation(s).")
