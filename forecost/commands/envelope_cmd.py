"""Explicit local resource-envelope controls for offline and CI use."""

from __future__ import annotations

import click

from forecost.ledger.db import get_ledger_db
from forecost.resources import (
    AdmissionMode,
    ResourceDimension,
    balance,
    containment_claim,
    create_scope,
    finalize_child,
    recover,
    release,
    reserve,
    settle,
    split_scope,
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
@click.option(
    "--authority",
    type=click.Choice(
        [
            "billed",
            "provider_estimate",
            "gateway_estimate",
            "list_rate",
            "contract_allocation",
            "subscription_quota",
            "unknown",
        ]
    ),
)
@click.option("--finalization-reserve-micros", type=click.IntRange(0), default=0)
@click.option("--max-overrun-micros", type=click.IntRange(0), default=0)
def create(
    scope: str,
    dimension: str,
    capacity_micros: int,
    mode: str,
    authority: str | None,
    finalization_reserve_micros: int,
    max_overrun_micros: int,
) -> None:
    """Create a scope. This is local-only, not provider-side enforcement."""
    result = create_scope(
        get_ledger_db(),
        scope,
        ResourceDimension(dimension),
        capacity_micros,
        mode=AdmissionMode(mode),
        authority=authority,
        finalization_reserve_micros=finalization_reserve_micros,
        max_overrun_micros=max_overrun_micros,
    )
    click.echo(f"Created {result.scope_id}; available={result.available_micros} micros.")
    _print_claim(scope)


@envelope.command("reserve")
@click.argument("scope")
@click.option("--amount-micros", type=click.IntRange(0), required=True)
@click.option("--key", "idempotency_key", required=True)
@click.option("--ttl-seconds", type=click.IntRange(0), default=None)
@click.option("--purpose", type=click.Choice(["normal", "finalization"]), default="normal")
def reserve_capacity(
    scope: str,
    amount_micros: int,
    idempotency_key: str,
    ttl_seconds: int | None,
    purpose: str,
) -> None:
    """Atomically reserve capacity and print its fencing token."""
    result = reserve(
        get_ledger_db(),
        scope,
        amount_micros,
        idempotency_key,
        ttl_seconds=ttl_seconds,
        purpose=purpose,
    )
    click.echo(
        f"{result.state}: {result.reservation_id} granted={result.granted_micros} "
        f"fence={result.fencing_token}"
    )
    _print_claim(scope)


@envelope.command("split")
@click.argument("parent_scope")
@click.argument("child_scope")
@click.option("--capacity-micros", type=click.IntRange(0), required=True)
@click.option("--key", "idempotency_key", required=True)
@click.option("--finalization-reserve-micros", type=click.IntRange(0), default=0)
def split_capacity(
    parent_scope: str,
    child_scope: str,
    capacity_micros: int,
    idempotency_key: str,
    finalization_reserve_micros: int,
) -> None:
    """Atomically fund a child cap from a parent scope."""
    result = split_scope(
        get_ledger_db(),
        parent_scope,
        child_scope,
        capacity_micros,
        idempotency_key,
        finalization_reserve_micros=finalization_reserve_micros,
    )
    click.echo(
        f"Transferred {capacity_micros} micros to {result.child_balance.scope_id}; "
        f"fence={result.parent_reservation.fencing_token}."
    )
    _print_claim(child_scope)


@envelope.command("finalize-child")
@click.argument("child_scope")
def finalize_child_capacity(child_scope: str) -> None:
    """Settle child consumption into its parent and return unused capacity."""
    result = finalize_child(get_ledger_db(), child_scope)
    click.echo(f"{result.state}: parent funding {result.reservation_id} finalized.")


@envelope.command("balance")
@click.argument("scope")
def show_balance(scope: str) -> None:
    """Show O(1) settled, reserved, and available counters."""
    result = balance(get_ledger_db(), scope)
    click.echo(
        f"capacity={result.capacity_micros} settled={result.settled_micros} "
        f"reserved={result.reserved_micros} available={result.available_micros} "
        f"normal_available={result.normal_available_micros} "
        f"conserved={str(result.conserved).lower()}"
    )
    _print_claim(scope)


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


def _print_claim(scope: str) -> None:
    claim = containment_claim(get_ledger_db(), scope)
    click.echo(
        f"Protection: {claim.readiness}; mode={claim.mode}; "
        f"max declared adapter overrun={claim.max_overrun_micros} micros."
    )
    click.echo(
        "Threat boundary: single-host transactional admission; the same OS user or an "
        "unbound provider/runtime can bypass local controls."
    )
