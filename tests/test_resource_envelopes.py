from __future__ import annotations

from concurrent.futures import ProcessPoolExecutor, ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from forecost.ledger.db import get_ledger_db
from forecost.resources import (
    ReservationState,
    balance,
    containment_claim,
    create_scope,
    expire,
    finalize_child,
    release,
    reserve,
    settle,
    split_scope,
    structural_loop_facts,
)


def _process_admit(arguments: tuple[str, int]) -> str:
    path, index = arguments
    conn = get_ledger_db(Path(path))
    try:
        return reserve(conn, "process-parallel", 1, f"request-{index}").state
    finally:
        conn.close()


def _process_split(arguments: tuple[str, int]) -> bool:
    path, index = arguments
    conn = get_ledger_db(Path(path))
    try:
        split_scope(conn, "split-parent", f"branch-{index}", 1, f"branch-{index}")
        return True
    except ValueError as exc:
        if "insufficient transferable capacity" not in str(exc):
            raise
        return False
    finally:
        conn.close()


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


def test_retry_identity_rejects_a_different_request_contract(ledger_conn):
    create_scope(ledger_conn, "stable-retry", "retries", 5)
    reserve(ledger_conn, "stable-retry", 1, "attempt-1")
    with pytest.raises(ValueError, match="different reservation"):
        reserve(ledger_conn, "stable-retry", 2, "attempt-1")
    assert balance(ledger_conn, "stable-retry").reserved_micros == 1


def test_money_scopes_are_typed_by_economic_authority(ledger_conn):
    billed = create_scope(ledger_conn, "billed-money", "money_usd", 100, authority="billed")
    estimated = create_scope(
        ledger_conn,
        "estimated-money",
        "money_usd",
        100,
        authority="provider_estimate",
    )
    assert billed.dimension == "money_usd:billed"
    assert estimated.dimension == "money_usd:provider_estimate"


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


def test_parent_child_split_settle_and_finalize_preserves_both_scopes(ledger_conn):
    create_scope(ledger_conn, "parent", "tokens", 1_000)
    transfer = split_scope(
        ledger_conn,
        "parent",
        "branch-a",
        400,
        "stable-branch-a",
        finalization_reserve_micros=50,
    )
    duplicate = split_scope(
        ledger_conn,
        "parent",
        "branch-a",
        400,
        "stable-branch-a",
        finalization_reserve_micros=50,
    )
    normal = reserve(ledger_conn, "branch-a", 350, "work")
    denied = reserve(ledger_conn, "branch-a", 1, "protected")
    final = reserve(ledger_conn, "branch-a", 50, "finish", purpose="finalization")
    settle(ledger_conn, normal.reservation_id, 275)
    settle(ledger_conn, final.reservation_id, 40)
    funding = finalize_child(ledger_conn, "branch-a")

    assert duplicate.parent_reservation.reservation_id == transfer.parent_reservation.reservation_id
    assert denied.state == ReservationState.DENIED.value
    assert funding.state == ReservationState.SETTLED.value
    assert balance(ledger_conn, "branch-a").settled_micros == 315
    parent = balance(ledger_conn, "parent")
    assert parent.settled_micros == 315
    assert parent.reserved_micros == 0
    assert parent.available_micros == 685
    assert parent.conserved


def test_child_finalization_requires_no_live_work_and_closes_admission(ledger_conn):
    create_scope(ledger_conn, "parent-close", "calls", 10)
    split_scope(ledger_conn, "parent-close", "child-close", 5, "child")
    item = reserve(ledger_conn, "child-close", 1, "live")
    with pytest.raises(ValueError, match="live reservations"):
        finalize_child(ledger_conn, "child-close")
    release(ledger_conn, item.reservation_id)
    finalize_child(ledger_conn, "child-close")
    with pytest.raises(ValueError, match="finalized"):
        reserve(ledger_conn, "child-close", 1, "late")


def test_modes_publish_honest_containment_and_overrun(ledger_conn):
    create_scope(
        ledger_conn,
        "observe",
        "retries",
        3,
        mode="warn",
        max_overrun_micros=1,
    )
    create_scope(ledger_conn, "contain", "branches", 3, mode="deny")

    observed = containment_claim(ledger_conn, "observe")
    contained = containment_claim(ledger_conn, "contain")
    assert (observed.readiness, observed.enforced, observed.max_overrun_micros) == (
        "OBSERVED",
        False,
        1,
    )
    assert (contained.readiness, contained.enforced) == ("CONTAINED", True)
    assert observed.threat_model == "same_user_local"


def test_structural_loop_facts_do_not_require_content():
    facts = structural_loop_facts(
        [
            {"operation_signature": "tool", "error": True, "progress": False, "branch_id": "a"},
            {
                "operation_signature": "tool",
                "error": True,
                "progress": False,
                "retry": True,
                "branch_id": "b",
            },
            {"operation_signature": "agent", "error": False, "progress": True, "branch_id": "b"},
        ]
    )
    assert facts.repeated_operation_max == 2
    assert facts.error_streak == 2
    assert facts.no_progress_streak == 2
    assert facts.retry_count == 1
    assert facts.branch_count == 2


def test_120_cross_process_admissions_never_exceed_parent(tmp_path):
    path = tmp_path / "multiprocess-ledger.db"
    setup = get_ledger_db(path)
    create_scope(setup, "process-parallel", "concurrency", 73, mode="deny")
    with ProcessPoolExecutor(max_workers=12) as pool:
        states = list(pool.map(_process_admit, [(str(path), index) for index in range(120)]))

    assert states.count(ReservationState.LIVE.value) == 73
    assert states.count(ReservationState.DENIED.value) == 47
    result = balance(setup, "process-parallel")
    assert result.reserved_micros == 73
    assert result.available_micros == 0
    assert result.conserved
    setup.close()


def test_120_cross_process_child_splits_never_overallocate_parent(tmp_path):
    path = tmp_path / "multiprocess-splits.db"
    setup = get_ledger_db(path)
    create_scope(setup, "split-parent", "branches", 67, mode="deny")
    with ProcessPoolExecutor(max_workers=12) as pool:
        granted = list(pool.map(_process_split, [(str(path), index) for index in range(120)]))

    assert granted.count(True) == 67
    assert granted.count(False) == 53
    result = balance(setup, "split-parent")
    assert result.reserved_micros == 67
    assert result.available_micros == 0
    assert result.conserved
    assert (
        setup.execute(
            "SELECT COUNT(*) FROM resource_scopes WHERE parent_scope_id=?", (result.scope_id,)
        ).fetchone()[0]
        == 67
    )
    setup.close()
