"""Transactional, single-host resource envelopes for agent-run admission."""

from __future__ import annotations

import sqlite3
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from enum import Enum

from forecost.ledger.contracts import Authority, canonical_json, opaque_id


class ResourceDimension(str, Enum):
    MONEY_USD = "money_usd"
    TOKENS = "tokens"
    CALLS = "calls"
    TOOL_UNITS = "tool_units"
    WALL_MICROS = "wall_micros"
    STEPS = "steps"
    RETRIES = "retries"
    BRANCHES = "branches"
    CONCURRENCY = "concurrency"


class AdmissionMode(str, Enum):
    SHADOW = "shadow"
    WARN = "warn"
    ASK = "ask"
    DENY = "deny"
    CI_FAIL_CLOSED = "ci_fail_closed"


class ReservationState(str, Enum):
    LIVE = "live"
    DENIED = "denied"
    SETTLED = "settled"
    RELEASED = "released"
    EXPIRED = "expired"


@dataclass(frozen=True)
class ScopeBalance:
    scope_id: str
    dimension: str
    capacity_micros: int
    settled_micros: int
    reserved_micros: int
    returned_micros: int
    adjustment_micros: int
    finalization_reserve_micros: int
    available_micros: int
    normal_available_micros: int
    conserved: bool


@dataclass(frozen=True)
class Reservation:
    reservation_id: str
    scope_id: str
    requested_micros: int
    granted_micros: int
    state: str
    fencing_token: int
    lease_expires_at: str | None


@dataclass(frozen=True)
class ScopeTransfer:
    parent_reservation: Reservation
    child_balance: ScopeBalance


@dataclass(frozen=True)
class ContainmentClaim:
    mode: str
    readiness: str
    enforced: bool
    threat_model: str
    max_overrun_micros: int


@dataclass(frozen=True)
class LoopFacts:
    repeated_operation_max: int
    error_streak: int
    no_progress_streak: int
    retry_count: int
    branch_count: int


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _scope_id(value: str) -> str:
    return opaque_id("resource-scope", value)


def _reservation_id(scope_id: str, idempotency_key: str) -> str:
    return opaque_id("reservation", f"{scope_id}|{idempotency_key}")


def _validate_amount(value: int, name: str) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"{name} must be a non-negative integer")


def _normalize_dimension(
    dimension: ResourceDimension | str, authority: Authority | str | None = None
) -> str:
    raw = dimension.value if isinstance(dimension, ResourceDimension) else dimension
    # A money scope may be partitioned by valuation authority. Legacy callers
    # without an authority retain their old key rather than silently changing it.
    if raw == ResourceDimension.MONEY_USD.value and authority is not None:
        return f"{raw}:{Authority(authority).value}"
    if raw.startswith(f"{ResourceDimension.MONEY_USD.value}:"):
        Authority(raw.split(":", 1)[1])
        return raw
    return ResourceDimension(raw).value


def _row_balance(row: sqlite3.Row) -> ScopeBalance:
    available = (
        int(row["capacity_micros"])
        + int(row["adjustment_micros"])
        - int(row["settled_micros"])
        - int(row["reserved_micros"])
    )
    return ScopeBalance(
        scope_id=row["scope_id"],
        dimension=row["dimension"],
        capacity_micros=int(row["capacity_micros"]),
        settled_micros=int(row["settled_micros"]),
        reserved_micros=int(row["reserved_micros"]),
        returned_micros=int(row["returned_micros"]),
        adjustment_micros=int(row["adjustment_micros"]),
        finalization_reserve_micros=int(row["finalization_reserve_micros"]),
        available_micros=available,
        normal_available_micros=max(0, available - int(row["finalization_reserve_micros"])),
        conserved=(
            available >= 0
            and int(row["settled_micros"]) + int(row["reserved_micros"]) + available
            == int(row["capacity_micros"]) + int(row["adjustment_micros"])
        ),
    )


def _validate_scope_amounts(
    capacity_micros: int,
    finalization_reserve_micros: int,
    max_overrun_micros: int,
) -> None:
    _validate_amount(capacity_micros, "capacity_micros")
    _validate_amount(finalization_reserve_micros, "finalization_reserve_micros")
    _validate_amount(max_overrun_micros, "max_overrun_micros")
    if finalization_reserve_micros > capacity_micros:
        raise ValueError("finalization reserve cannot exceed capacity")


def _scope_contract(
    row: sqlite3.Row,
    dimension: str,
    capacity_micros: int,
    mode: str,
    finalization_reserve_micros: int,
    max_overrun_micros: int,
) -> bool:
    actual = (
        row["dimension"],
        int(row["capacity_micros"]),
        row["mode"],
        int(row["finalization_reserve_micros"]),
        int(row["max_overrun_micros"]),
    )
    expected = (
        dimension,
        capacity_micros,
        mode,
        finalization_reserve_micros,
        max_overrun_micros,
    )
    return actual == expected


def _insert_root_scope(
    conn: sqlite3.Connection,
    scope_id: str,
    dimension: str,
    capacity_micros: int,
    mode: str,
    finalization_reserve_micros: int,
    max_overrun_micros: int,
    metadata: Mapping[str, object] | None,
) -> sqlite3.Row:
    conn.execute(
        """
        INSERT OR IGNORE INTO resource_scopes(
            scope_id, parent_scope_id, dimension, capacity_micros, mode,
            finalization_reserve_micros, max_overrun_micros,
            created_at, metadata_json
        ) VALUES (?,?,?,?,?,?,?,?,?)
        """,
        (
            scope_id,
            None,
            dimension,
            capacity_micros,
            mode,
            finalization_reserve_micros,
            max_overrun_micros,
            _now().isoformat(),
            canonical_json(dict(metadata or {})),
        ),
    )
    row: sqlite3.Row | None = conn.execute(
        "SELECT * FROM resource_scopes WHERE scope_id = ?", (scope_id,)
    ).fetchone()
    if row is None:  # pragma: no cover - insert/select invariant
        raise RuntimeError("resource scope insert did not yield a row")
    return row


def create_scope(
    conn: sqlite3.Connection,
    scope: str,
    dimension: ResourceDimension | str,
    capacity_micros: int,
    *,
    parent_scope: str | None = None,
    mode: AdmissionMode | str = AdmissionMode.SHADOW,
    authority: Authority | str | None = None,
    finalization_reserve_micros: int = 0,
    max_overrun_micros: int = 0,
    metadata: Mapping[str, object] | None = None,
) -> ScopeBalance:
    """Create an idempotent local scope with O(1) mutable counters."""
    _validate_scope_amounts(capacity_micros, finalization_reserve_micros, max_overrun_micros)
    dimension = _normalize_dimension(dimension, authority)
    mode = AdmissionMode(mode).value
    if parent_scope is not None:
        return split_scope(
            conn,
            parent_scope,
            scope,
            capacity_micros,
            f"create-child:{scope}",
            finalization_reserve_micros=finalization_reserve_micros,
            max_overrun_micros=max_overrun_micros,
            mode=mode,
            metadata=metadata,
            expected_dimension=dimension,
        ).child_balance
    scope_id = _scope_id(scope)
    conn.execute("BEGIN IMMEDIATE")
    try:
        row = _insert_root_scope(
            conn,
            scope_id,
            dimension,
            capacity_micros,
            mode,
            finalization_reserve_micros,
            max_overrun_micros,
            metadata,
        )
        if not _scope_contract(
            row,
            dimension,
            capacity_micros,
            mode,
            finalization_reserve_micros,
            max_overrun_micros,
        ):
            raise ValueError("resource scope already exists with different contract")
        conn.commit()
        return _row_balance(row)
    except BaseException:
        conn.rollback()
        raise


def balance(conn: sqlite3.Connection, scope: str) -> ScopeBalance:
    row = conn.execute(
        "SELECT * FROM resource_scopes WHERE scope_id = ?", (_scope_id(scope),)
    ).fetchone()
    if row is None:
        raise ValueError("resource scope not found")
    result = _row_balance(row)
    if not result.conserved:
        raise RuntimeError("resource scope conservation invariant is broken")
    return result


def containment_claim(conn: sqlite3.Connection, scope: str) -> ContainmentClaim:
    """Describe exactly what a local admission mode can and cannot contain."""
    row = conn.execute(
        "SELECT mode,threat_model,max_overrun_micros FROM resource_scopes WHERE scope_id=?",
        (_scope_id(scope),),
    ).fetchone()
    if row is None:
        raise ValueError("resource scope not found")
    enforced = row["mode"] in {AdmissionMode.DENY.value, AdmissionMode.CI_FAIL_CLOSED.value}
    return ContainmentClaim(
        mode=str(row["mode"]),
        readiness="CONTAINED" if enforced else "OBSERVED",
        enforced=enforced,
        threat_model=str(row["threat_model"]),
        max_overrun_micros=int(row["max_overrun_micros"]),
    )


def _existing_transfer(
    conn: sqlite3.Connection,
    *,
    parent_id: str,
    child_id: str,
    reservation_id: str,
    capacity_micros: int,
    finalization_reserve_micros: int,
    max_overrun_micros: int,
    child_mode: str,
) -> ScopeTransfer | None:
    child: sqlite3.Row | None = conn.execute(
        "SELECT * FROM resource_scopes WHERE scope_id=?", (child_id,)
    ).fetchone()
    reservation: sqlite3.Row | None = conn.execute(
        "SELECT * FROM resource_reservations WHERE reservation_id=?", (reservation_id,)
    ).fetchone()
    if child is None and reservation is None:
        return None
    if child is None or reservation is None:
        raise ValueError("child scope or idempotency key already has a different contract")
    actual = (
        child["parent_scope_id"],
        int(child["capacity_micros"]),
        reservation["child_scope_id"],
        int(child["finalization_reserve_micros"]),
        int(child["max_overrun_micros"]),
        child["mode"],
    )
    expected = (
        parent_id,
        capacity_micros,
        child_id,
        finalization_reserve_micros,
        max_overrun_micros,
        child_mode,
    )
    if actual != expected:
        raise ValueError("child scope or idempotency key already has a different contract")
    return ScopeTransfer(_reservation_from_row(reservation), _row_balance(child))


def _validate_parent_transfer(
    parent: sqlite3.Row,
    capacity_micros: int,
    expected_dimension: str | None,
) -> None:
    if expected_dimension is not None and parent["dimension"] != expected_dimension:
        raise ValueError("child dimension must match its parent")
    if parent["closed_at"] is not None:
        raise ValueError("parent resource scope is finalized")
    if capacity_micros > _row_balance(parent).normal_available_micros:
        raise ValueError("parent scope has insufficient transferable capacity")


def _next_fencing_token(conn: sqlite3.Connection, scope_id: str) -> int:
    row = conn.execute(
        "UPDATE resource_scopes SET next_fencing_token=next_fencing_token+1 "
        "WHERE scope_id=? RETURNING next_fencing_token-1",
        (scope_id,),
    ).fetchone()
    if row is None:  # pragma: no cover - caller selected the scope
        raise RuntimeError("scope fencing counter was not updated")
    return int(row[0])


def _insert_transfer(
    conn: sqlite3.Connection,
    *,
    parent: sqlite3.Row,
    parent_id: str,
    child_id: str,
    reservation_id: str,
    key: str,
    capacity_micros: int,
    child_mode: str,
    finalization_reserve_micros: int,
    max_overrun_micros: int,
    metadata: Mapping[str, object] | None,
) -> ScopeTransfer:
    token = _next_fencing_token(conn, parent_id)
    now = _now().isoformat()
    conn.execute(
        """
        INSERT INTO resource_reservations(
            reservation_id,scope_id,child_scope_id,dimension,requested_micros,
            granted_micros,state,idempotency_key,fencing_token,provenance_json,
            created_at,updated_at
        ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)
        """,
        (
            reservation_id,
            parent_id,
            child_id,
            parent["dimension"],
            capacity_micros,
            capacity_micros,
            ReservationState.LIVE.value,
            key,
            token,
            canonical_json({"purpose": "child_transfer"}),
            now,
            now,
        ),
    )
    conn.execute(
        """
        INSERT INTO resource_scopes(
            scope_id,parent_scope_id,dimension,capacity_micros,mode,
            finalization_reserve_micros,max_overrun_micros,threat_model,
            created_at,metadata_json
        ) VALUES (?,?,?,?,?,?,?,?,?,?)
        """,
        (
            child_id,
            parent_id,
            parent["dimension"],
            capacity_micros,
            child_mode,
            finalization_reserve_micros,
            max_overrun_micros,
            parent["threat_model"],
            now,
            canonical_json(dict(metadata or {})),
        ),
    )
    conn.execute(
        "UPDATE resource_scopes SET reserved_micros=reserved_micros+? WHERE scope_id=?",
        (capacity_micros, parent_id),
    )
    child: sqlite3.Row | None = conn.execute(
        "SELECT * FROM resource_scopes WHERE scope_id=?", (child_id,)
    ).fetchone()
    reservation: sqlite3.Row | None = conn.execute(
        "SELECT * FROM resource_reservations WHERE reservation_id=?", (reservation_id,)
    ).fetchone()
    if child is None or reservation is None:  # pragma: no cover - insert invariant
        raise RuntimeError("child transfer insert did not yield rows")
    return ScopeTransfer(_reservation_from_row(reservation), _row_balance(child))


def split_scope(
    conn: sqlite3.Connection,
    parent_scope: str,
    child_scope: str,
    capacity_micros: int,
    idempotency_key: str,
    *,
    finalization_reserve_micros: int = 0,
    max_overrun_micros: int = 0,
    mode: AdmissionMode | str | None = None,
    metadata: Mapping[str, object] | None = None,
    expected_dimension: str | None = None,
) -> ScopeTransfer:
    """Atomically fund a child by reserving exactly its cap from its parent."""
    _validate_scope_amounts(capacity_micros, finalization_reserve_micros, max_overrun_micros)
    if not idempotency_key:
        raise ValueError("idempotency_key must be non-empty")
    parent_id = _scope_id(parent_scope)
    child_id = _scope_id(child_scope)
    key = opaque_id("reservation-key", idempotency_key)
    reservation_id = _reservation_id(parent_id, key)
    conn.execute("BEGIN IMMEDIATE")
    try:
        parent: sqlite3.Row | None = conn.execute(
            "SELECT * FROM resource_scopes WHERE scope_id=?", (parent_id,)
        ).fetchone()
        if parent is None:
            raise ValueError("parent resource scope not found")
        child_mode = AdmissionMode(mode or parent["mode"]).value
        existing = _existing_transfer(
            conn,
            parent_id=parent_id,
            child_id=child_id,
            reservation_id=reservation_id,
            capacity_micros=capacity_micros,
            finalization_reserve_micros=finalization_reserve_micros,
            max_overrun_micros=max_overrun_micros,
            child_mode=child_mode,
        )
        if existing is not None:
            conn.commit()
            return existing
        _validate_parent_transfer(parent, capacity_micros, expected_dimension)
        result = _insert_transfer(
            conn,
            parent=parent,
            parent_id=parent_id,
            child_id=child_id,
            reservation_id=reservation_id,
            key=key,
            capacity_micros=capacity_micros,
            child_mode=child_mode,
            finalization_reserve_micros=finalization_reserve_micros,
            max_overrun_micros=max_overrun_micros,
            metadata=metadata,
        )
        conn.commit()
        return result
    except BaseException:
        conn.rollback()
        raise


def finalize_child(conn: sqlite3.Connection, child_scope: str) -> Reservation:
    """Close a child and settle its actual consumption into its parent once."""
    child_id = _scope_id(child_scope)
    conn.execute("BEGIN IMMEDIATE")
    try:
        child = conn.execute(
            "SELECT * FROM resource_scopes WHERE scope_id=?", (child_id,)
        ).fetchone()
        if child is None or child["parent_scope_id"] is None:
            raise ValueError("funded child resource scope not found")
        parent_reservation = conn.execute(
            "SELECT * FROM resource_reservations WHERE child_scope_id=? "
            "ORDER BY created_at LIMIT 1",
            (child_id,),
        ).fetchone()
        if parent_reservation is None:  # pragma: no cover - split invariant
            raise RuntimeError("child funding reservation is missing")
        if parent_reservation["state"] != ReservationState.LIVE.value:
            conn.commit()
            return _reservation_from_row(parent_reservation)
        live = int(
            conn.execute(
                "SELECT COUNT(*) FROM resource_reservations WHERE scope_id=? AND state=?",
                (child_id, ReservationState.LIVE.value),
            ).fetchone()[0]
        )
        if live:
            raise ValueError("cannot finalize a child with live reservations")
        used = int(child["settled_micros"])
        granted = int(parent_reservation["granted_micros"])
        returned = granted - used
        now = _now().isoformat()
        conn.execute(
            "UPDATE resource_reservations SET state=?,settled_micros=?,updated_at=? "
            "WHERE reservation_id=?",
            (ReservationState.SETTLED.value, used, now, parent_reservation["reservation_id"]),
        )
        conn.execute(
            "UPDATE resource_scopes SET reserved_micros=reserved_micros-?, "
            "settled_micros=settled_micros+?, returned_micros=returned_micros+? "
            "WHERE scope_id=?",
            (granted, used, returned, child["parent_scope_id"]),
        )
        conn.execute("UPDATE resource_scopes SET closed_at=? WHERE scope_id=?", (now, child_id))
        result = conn.execute(
            "SELECT * FROM resource_reservations WHERE reservation_id=?",
            (parent_reservation["reservation_id"],),
        ).fetchone()
        conn.commit()
        if result is None:  # pragma: no cover
            raise RuntimeError("child finalization did not yield a reservation")
        return _reservation_from_row(result)
    except BaseException:
        conn.rollback()
        raise


def structural_loop_facts(events: Iterable[Mapping[str, object]]) -> LoopFacts:
    """Compute content-free loop signals from bounded structural event codes."""
    counts: dict[str, int] = {}
    error_streak = no_progress_streak = retry_count = 0
    current_error = current_no_progress = 0
    branches: set[str] = set()
    for event in events:
        signature = event.get("operation_signature")
        if isinstance(signature, str):
            signature = opaque_id("operation", signature)
            counts[signature] = counts.get(signature, 0) + 1
        current_error = current_error + 1 if event.get("error") is True else 0
        current_no_progress = current_no_progress + 1 if event.get("progress") is False else 0
        error_streak = max(error_streak, current_error)
        no_progress_streak = max(no_progress_streak, current_no_progress)
        retry_count += int(event.get("retry") is True)
        branch = event.get("branch_id")
        if isinstance(branch, str):
            branches.add(opaque_id("branch", branch))
    return LoopFacts(
        repeated_operation_max=max(counts.values(), default=0),
        error_streak=error_streak,
        no_progress_streak=no_progress_streak,
        retry_count=retry_count,
        branch_count=len(branches),
    )


def _validate_reservation_request(
    requested_micros: int,
    idempotency_key: str,
    ttl_seconds: int | None,
    purpose: str,
) -> None:
    _validate_amount(requested_micros, "requested_micros")
    if not isinstance(idempotency_key, str) or not idempotency_key:
        raise ValueError("idempotency_key must be non-empty")
    if ttl_seconds is not None and ttl_seconds < 0:
        raise ValueError("ttl_seconds must be non-negative")
    if purpose not in {"normal", "finalization"}:
        raise ValueError("purpose must be normal or finalization")


def _existing_reservation(
    conn: sqlite3.Connection,
    scope_id: str,
    key: str,
    requested_micros: int,
    child_scope: str | None,
) -> Reservation | None:
    row: sqlite3.Row | None = conn.execute(
        "SELECT * FROM resource_reservations WHERE scope_id = ? AND idempotency_key = ?",
        (scope_id, key),
    ).fetchone()
    if row is None:
        return None
    expected = (requested_micros, _scope_id(child_scope) if child_scope is not None else None)
    actual = (int(row["requested_micros"]), row["child_scope_id"])
    if actual != expected:
        raise ValueError("idempotency key already belongs to a different reservation")
    return _reservation_from_row(row)


def _open_scope(conn: sqlite3.Connection, scope_id: str) -> sqlite3.Row:
    row: sqlite3.Row | None = conn.execute(
        "SELECT * FROM resource_scopes WHERE scope_id = ?", (scope_id,)
    ).fetchone()
    if row is None:
        raise ValueError("resource scope not found")
    if row["closed_at"] is not None:
        raise ValueError("resource scope is finalized")
    return row


def _grant(row: sqlite3.Row, requested_micros: int, purpose: str) -> tuple[str, int]:
    scope_balance = _row_balance(row)
    available = (
        scope_balance.available_micros
        if purpose == "finalization"
        else scope_balance.normal_available_micros
    )
    if requested_micros > available:
        return ReservationState.DENIED.value, 0
    return ReservationState.LIVE.value, requested_micros


def _insert_reservation(
    conn: sqlite3.Connection,
    *,
    reservation_id: str,
    scope_id: str,
    child_scope: str | None,
    row: sqlite3.Row,
    requested_micros: int,
    granted_micros: int,
    state: str,
    key: str,
    expires: str | None,
    provenance: Mapping[str, object] | None,
    purpose: str,
    now_iso: str,
) -> Reservation:
    conn.execute(
        """
        INSERT INTO resource_reservations(
            reservation_id, scope_id, child_scope_id, dimension, requested_micros,
            granted_micros, state, idempotency_key, lease_expires_at, fencing_token,
            provenance_json, created_at, updated_at
        ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)
        """,
        (
            reservation_id,
            scope_id,
            _scope_id(child_scope) if child_scope is not None else None,
            row["dimension"],
            requested_micros,
            granted_micros,
            state,
            key,
            expires,
            _next_fencing_token(conn, scope_id),
            canonical_json({**dict(provenance or {}), "purpose": purpose}),
            now_iso,
            now_iso,
        ),
    )
    if granted_micros:
        conn.execute(
            "UPDATE resource_scopes SET reserved_micros = reserved_micros + ? WHERE scope_id = ?",
            (granted_micros, scope_id),
        )
    result: sqlite3.Row | None = conn.execute(
        "SELECT * FROM resource_reservations WHERE reservation_id = ?", (reservation_id,)
    ).fetchone()
    if result is None:  # pragma: no cover - insert/select invariant
        raise RuntimeError("reservation insert did not yield a row")
    return _reservation_from_row(result)


def reserve(
    conn: sqlite3.Connection,
    scope: str,
    requested_micros: int,
    idempotency_key: str,
    *,
    ttl_seconds: int | None = None,
    child_scope: str | None = None,
    purpose: str = "normal",
    provenance: Mapping[str, object] | None = None,
) -> Reservation:
    """Atomically reserve available capacity, or record a denied admission."""
    _validate_reservation_request(requested_micros, idempotency_key, ttl_seconds, purpose)
    scope_id = _scope_id(scope)
    key = opaque_id("reservation-key", idempotency_key)
    reservation_id = _reservation_id(scope_id, key)
    now = _now()
    expires = (
        (now + timedelta(seconds=ttl_seconds)).isoformat() if ttl_seconds is not None else None
    )
    conn.execute("BEGIN IMMEDIATE")
    try:
        existing = _existing_reservation(conn, scope_id, key, requested_micros, child_scope)
        if existing is not None:
            conn.commit()
            return existing
        row = _open_scope(conn, scope_id)
        state, granted = _grant(row, requested_micros, purpose)
        result = _insert_reservation(
            conn,
            reservation_id=reservation_id,
            scope_id=scope_id,
            child_scope=child_scope,
            row=row,
            requested_micros=requested_micros,
            granted_micros=granted,
            state=state,
            key=key,
            expires=expires,
            provenance=provenance,
            purpose=purpose,
            now_iso=now.isoformat(),
        )
        conn.commit()
        return result
    except BaseException:
        conn.rollback()
        raise


def settle(conn: sqlite3.Connection, reservation_id: str, used_micros: int) -> Reservation:
    """Commit consumption once and return unused capacity to the parent scope."""
    _validate_amount(used_micros, "used_micros")
    return _close_reservation(conn, reservation_id, ReservationState.SETTLED, used_micros)


def release(conn: sqlite3.Connection, reservation_id: str) -> Reservation:
    """Return an unspent live reservation without recording consumption."""
    return _close_reservation(conn, reservation_id, ReservationState.RELEASED, 0)


def _close_reservation(
    conn: sqlite3.Connection,
    reservation_id: str,
    target: ReservationState,
    used_micros: int,
) -> Reservation:
    conn.execute("BEGIN IMMEDIATE")
    try:
        row = conn.execute(
            "SELECT * FROM resource_reservations WHERE reservation_id = ?",
            (opaque_id("reservation", reservation_id),),
        ).fetchone()
        if row is None:
            raise ValueError("reservation not found")
        existing = _reservation_from_row(row)
        if existing.state != ReservationState.LIVE.value:
            conn.commit()
            return existing
        granted = int(row["granted_micros"])
        if used_micros > granted:
            raise ValueError("cannot settle more than granted capacity")
        returned = granted - used_micros
        now = _now().isoformat()
        conn.execute(
            """
            UPDATE resource_reservations
            SET state = ?, settled_micros = ?, updated_at = ?
            WHERE reservation_id = ?
            """,
            (target.value, used_micros, now, row["reservation_id"]),
        )
        conn.execute(
            """
            UPDATE resource_scopes
            SET reserved_micros = reserved_micros - ?,
                settled_micros = settled_micros + ?,
                returned_micros = returned_micros + ?
            WHERE scope_id = ?
            """,
            (granted, used_micros, returned, row["scope_id"]),
        )
        result = conn.execute(
            "SELECT * FROM resource_reservations WHERE reservation_id = ?", (row["reservation_id"],)
        ).fetchone()
        conn.commit()
        if result is None:  # pragma: no cover - update/select invariant
            raise RuntimeError("reservation update did not yield a row")
        return _reservation_from_row(result)
    except BaseException:
        conn.rollback()
        raise


def expire(conn: sqlite3.Connection, now: datetime | None = None) -> list[Reservation]:
    """Expire every live lease that is due; safe to repeat after crashes."""
    cutoff = (now or _now()).astimezone(timezone.utc).isoformat()
    rows = conn.execute(
        "SELECT reservation_id FROM resource_reservations "
        "WHERE state = ? AND lease_expires_at IS NOT NULL AND lease_expires_at <= ? "
        "ORDER BY reservation_id",
        (ReservationState.LIVE.value, cutoff),
    ).fetchall()
    expired: list[Reservation] = []
    for row in rows:
        result = _close_reservation(conn, row["reservation_id"], ReservationState.EXPIRED, 0)
        expired.append(result)
    return expired


def recover(conn: sqlite3.Connection) -> list[Reservation]:
    """Crash recovery is lease expiration; no unbounded stale reservation survives."""
    return expire(conn)


def _reservation_from_row(row: sqlite3.Row) -> Reservation:
    return Reservation(
        reservation_id=row["reservation_id"],
        scope_id=row["scope_id"],
        requested_micros=int(row["requested_micros"]),
        granted_micros=int(row["granted_micros"]),
        state=row["state"],
        fencing_token=int(row["fencing_token"]),
        lease_expires_at=row["lease_expires_at"],
    )
