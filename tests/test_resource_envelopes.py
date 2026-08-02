from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone

from forecost.ledger.db import get_ledger_db
from forecost.resources import (
    ReservationState,
    balance,
    create_scope,
    expire,
    release,
    reserve,
    settle,
)


def test_reservation_settlement_preserves_capacity_invariant(ledger_conn):
    created = create_scope(ledger_conn, "run-cap", "money_usd", 1_000)
    first = reserve(ledger_conn, "run-cap", 700, "first")
    settled = settle(ledger_conn, first.reservation_id, 400)
    denied = reserve(ledger_conn, "run-cap", 700, "second")
    after = balance(ledger_conn, "run-cap")

    assert created.available_micros == 1_000
    assert settled.state == ReservationState.SETTLED.value
    assert denied.state == ReservationState.DENIED.value
    assert after.settled_micros == 400
    assert after.reserved_micros == 0
    assert after.returned_micros == 300
    assert after.available_micros == 600
    assert after.conserved


def test_reservation_is_idempotent_and_leases_recover(ledger_conn):
    create_scope(ledger_conn, "lease", "tokens", 100)
    first = reserve(ledger_conn, "lease", 80, "same", ttl_seconds=1)
    duplicate = reserve(ledger_conn, "lease", 80, "same", ttl_seconds=1)
    expired = expire(ledger_conn, datetime.now(timezone.utc) + timedelta(seconds=2))

    assert duplicate.reservation_id == first.reservation_id
    assert len(expired) == 1
    assert expired[0].state == ReservationState.EXPIRED.value
    assert balance(ledger_conn, "lease").available_micros == 100


def test_concurrent_admission_never_overspends(tmp_path):
    path = tmp_path / "ledger.db"
    setup = get_ledger_db(path)
    create_scope(setup, "parallel", "calls", 10)

    def admit(index: int):
        return reserve(get_ledger_db(path), "parallel", 1, f"request-{index}")

    with ThreadPoolExecutor(max_workers=12) as pool:
        results = list(pool.map(admit, range(12)))

    assert sum(result.state == ReservationState.LIVE.value for result in results) == 10
    assert sum(result.state == ReservationState.DENIED.value for result in results) == 2
    final = balance(setup, "parallel")
    assert final.reserved_micros == 10
    assert final.available_micros == 0
    assert final.conserved


def test_release_is_safe_to_repeat(ledger_conn):
    create_scope(ledger_conn, "release", "steps", 4)
    item = reserve(ledger_conn, "release", 3, "release-once")
    first = release(ledger_conn, item.reservation_id)
    second = release(ledger_conn, item.reservation_id)

    assert first.state == second.state == ReservationState.RELEASED.value
    assert balance(ledger_conn, "release").available_micros == 4
