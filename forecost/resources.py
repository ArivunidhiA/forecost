"""Transactional, single-host resource envelopes for agent-run admission."""

from __future__ import annotations

import sqlite3
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from enum import Enum

from forecost.ledger.contracts import canonical_json, opaque_id


class ResourceDimension(str, Enum):
    MONEY_USD = "money_usd"
    TOKENS = "tokens"
    CALLS = "calls"
    TOOL_UNITS = "tool_units"
    WALL_MICROS = "wall_micros"
    STEPS = "steps"
    RETRIES = "retries"
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
    available_micros: int
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


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _scope_id(value: str) -> str:
    return opaque_id("resource-scope", value)


def _reservation_id(scope_id: str, idempotency_key: str) -> str:
    return opaque_id("reservation", f"{scope_id}|{idempotency_key}")


def _validate_amount(value: int, name: str) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"{name} must be a non-negative integer")


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
        available_micros=available,
        conserved=available >= 0,
    )


def create_scope(
    conn: sqlite3.Connection,
    scope: str,
    dimension: ResourceDimension | str,
    capacity_micros: int,
    *,
    parent_scope: str | None = None,
    mode: AdmissionMode | str = AdmissionMode.SHADOW,
    metadata: Mapping[str, object] | None = None,
) -> ScopeBalance:
    """Create an idempotent local scope with O(1) mutable counters."""
    _validate_amount(capacity_micros, "capacity_micros")
    dimension = ResourceDimension(dimension).value
    mode = AdmissionMode(mode).value
    scope_id = _scope_id(scope)
    parent_id = _scope_id(parent_scope) if parent_scope is not None else None
    now = _now().isoformat()
    conn.execute("BEGIN IMMEDIATE")
    try:
        conn.execute(
            """
            INSERT OR IGNORE INTO resource_scopes(
                scope_id, parent_scope_id, dimension, capacity_micros, mode,
                created_at, metadata_json
            ) VALUES (?,?,?,?,?,?,?)
            """,
            (
                scope_id,
                parent_id,
                dimension,
                capacity_micros,
                mode,
                now,
                canonical_json(dict(metadata or {})),
            ),
        )
        row = conn.execute(
            "SELECT * FROM resource_scopes WHERE scope_id = ?", (scope_id,)
        ).fetchone()
        if row is None:  # pragma: no cover - insert/select invariant
            raise RuntimeError("resource scope insert did not yield a row")
        if row["dimension"] != dimension or row["capacity_micros"] != capacity_micros:
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


def reserve(
    conn: sqlite3.Connection,
    scope: str,
    requested_micros: int,
    idempotency_key: str,
    *,
    ttl_seconds: int | None = None,
    child_scope: str | None = None,
    provenance: Mapping[str, object] | None = None,
) -> Reservation:
    """Atomically reserve available capacity, or record a denied admission."""
    _validate_amount(requested_micros, "requested_micros")
    if not isinstance(idempotency_key, str) or not idempotency_key:
        raise ValueError("idempotency_key must be non-empty")
    if ttl_seconds is not None and ttl_seconds < 0:
        raise ValueError("ttl_seconds must be non-negative")
    scope_id = _scope_id(scope)
    key = opaque_id("reservation-key", idempotency_key)
    reservation_id = _reservation_id(scope_id, key)
    now = _now()
    expires = (
        (now + timedelta(seconds=ttl_seconds)).isoformat() if ttl_seconds is not None else None
    )
    conn.execute("BEGIN IMMEDIATE")
    try:
        existing = conn.execute(
            "SELECT * FROM resource_reservations WHERE scope_id = ? AND idempotency_key = ?",
            (scope_id, key),
        ).fetchone()
        if existing is not None:
            conn.commit()
            return _reservation_from_row(existing)
        row = conn.execute(
            "SELECT * FROM resource_scopes WHERE scope_id = ?", (scope_id,)
        ).fetchone()
        if row is None:
            raise ValueError("resource scope not found")
        state = ReservationState.LIVE.value
        granted = requested_micros
        available = _row_balance(row).available_micros
        if requested_micros > available:
            state = ReservationState.DENIED.value
            granted = 0
        token = int(
            conn.execute(
                "SELECT COALESCE(MAX(fencing_token), 0) + 1 FROM resource_reservations "
                "WHERE scope_id = ?",
                (scope_id,),
            ).fetchone()[0]
        )
        now_iso = now.isoformat()
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
                granted,
                state,
                key,
                expires,
                token,
                canonical_json(dict(provenance or {})),
                now_iso,
                now_iso,
            ),
        )
        if granted:
            conn.execute(
                "UPDATE resource_scopes SET reserved_micros = reserved_micros + "
                "? WHERE scope_id = ?",
                (granted, scope_id),
            )
        result = conn.execute(
            "SELECT * FROM resource_reservations WHERE reservation_id = ?", (reservation_id,)
        ).fetchone()
        conn.commit()
        if result is None:  # pragma: no cover - insert/select invariant
            raise RuntimeError("reservation insert did not yield a row")
        return _reservation_from_row(result)
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
