"""Tiny durable Claude hook state, separate from transcript reconciliation."""

from __future__ import annotations

import contextlib
import hashlib
import json
import os
import tempfile
import threading
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from forecost.core.local_identity import keyed_fingerprint
from forecost.core.paths import (
    OWNERSHIP_MARKER,
    chmod_private,
    ensure_private_dir,
    forecost_home,
    open_private_file_descriptor,
)
from forecost.ledger.contracts import opaque_id

HOOK_PROTOCOL_VERSION = 1
_HOOK_EVENTS = frozenset(
    {
        "PostToolUse",
        "PostToolUseFailure",
        "PreToolUse",
        "SessionEnd",
        "SessionStart",
        "Stop",
        "StopFailure",
        "SubagentStart",
        "SubagentStop",
        "UserPromptSubmit",
    }
)
_HOOK_STATES = frozenset({"degraded", "healthy", "unknown"})
_SETTLEMENT_THREAD_LOCK = threading.Lock()


@dataclass(frozen=True)
class SettlementSnapshot:
    """An immutable acknowledgement token for complete markers seen together."""

    pending: int
    prefix_bytes: int
    prefix_sha256: str


def _lock_descriptor(descriptor: int) -> None:
    if os.name == "nt":  # pragma: no cover - exercised on Windows CI
        import msvcrt

        if os.fstat(descriptor).st_size == 0:
            os.write(descriptor, b"\0")
            os.fsync(descriptor)
        os.lseek(descriptor, 0, os.SEEK_SET)
        msvcrt.locking(descriptor, msvcrt.LK_LOCK, 1)  # type: ignore[attr-defined]
        return
    import fcntl

    fcntl.flock(descriptor, fcntl.LOCK_EX)


def _unlock_descriptor(descriptor: int) -> None:
    if os.name == "nt":  # pragma: no cover - exercised on Windows CI
        import msvcrt

        os.lseek(descriptor, 0, os.SEEK_SET)
        msvcrt.locking(descriptor, msvcrt.LK_UNLCK, 1)  # type: ignore[attr-defined]
        return
    import fcntl

    fcntl.flock(descriptor, fcntl.LOCK_UN)


def _fsync_directory(path: Path) -> None:
    """Persist directory-entry changes where the platform supports it."""
    if os.name == "nt":  # Windows does not support opening directories this way.
        return
    flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0)
    descriptor = os.open(path, flags)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _ensure_durable_private_dir(path: Path) -> Path:
    """Create a private directory and persist each newly created name."""
    missing: list[Path] = []
    candidate = path
    while not candidate.exists():
        missing.append(candidate)
        if candidate == candidate.parent:  # pragma: no cover - filesystem root exists
            break
        candidate = candidate.parent
    result = ensure_private_dir(path)
    for created in reversed(missing):
        _fsync_directory(created.parent)
    return result


def _open_append(path: Path) -> tuple[int, bool]:
    """Open an append target and report whether this call created its name."""
    flags = os.O_WRONLY | os.O_APPEND
    try:
        return open_private_file_descriptor(path, flags | os.O_CREAT | os.O_EXCL), True
    except FileExistsError:
        return open_private_file_descriptor(path, flags), False


def _state_dir() -> Path:
    return forecost_home() / "hooks"


def _ensure_state_dir() -> Path:
    home = _ensure_durable_private_dir(forecost_home())
    return _ensure_durable_private_dir(home / "hooks")


@contextmanager
def _settlement_lock(*, create: bool) -> Iterator[bool]:
    """Lock the stable hook ownership marker, optionally without creating state."""
    state_dir = _state_dir()
    if not create and not state_dir.is_dir():
        yield False
        return
    with _SETTLEMENT_THREAD_LOCK:
        state_dir = _ensure_state_dir()
        descriptor = open_private_file_descriptor(state_dir / OWNERSHIP_MARKER, os.O_RDWR)
        try:
            _lock_descriptor(descriptor)
            yield True
        finally:
            with contextlib.suppress(OSError):
                _unlock_descriptor(descriptor)
            os.close(descriptor)


def heartbeat_path() -> Path:
    return _state_dir() / "heartbeat.json"


def settlement_path() -> Path:
    return _state_dir() / "settlement-required.jsonl"


def summary_path() -> Path:
    return _state_dir() / "last-summary.json"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _atomic_json(path: Path, value: dict[str, object]) -> None:
    parent = _ensure_state_dir()
    descriptor, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=parent)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            json.dump(value, stream, sort_keys=True, separators=(",", ":"))
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
        chmod_private(path)
        _fsync_directory(path.parent)
    except BaseException:
        with contextlib.suppress(OSError):
            os.unlink(temporary)
        raise


def record_heartbeat(event: str, *, state: str = "healthy", detail: str | None = None) -> None:
    safe_event = event if event in _HOOK_EVENTS else "Unknown"
    safe_state = state if state in _HOOK_STATES else "unknown"
    value: dict[str, object] = {
        "protocol_version": HOOK_PROTOCOL_VERSION,
        "event": safe_event,
        "state": safe_state,
        "observed_at": _now(),
        "readiness": "OBSERVED",
    }
    if safe_event == "Unknown":
        value["event_fingerprint"] = keyed_fingerprint("hook-event-v1", event)
    if safe_state == "unknown" and state != "unknown":
        value["state_fingerprint"] = keyed_fingerprint("hook-state-v1", state)
    if detail is not None:
        value["detail_fingerprint"] = keyed_fingerprint("hook-detail-v1", detail)
    _atomic_json(heartbeat_path(), value)


def read_heartbeat() -> dict[str, object] | None:
    try:
        value = json.loads(heartbeat_path().read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return value if isinstance(value, dict) else None


def append_settlement_marker(payload: dict[str, object]) -> None:
    """Fsync one content-free marker; no transcript path or host payload persists."""
    session = payload.get("session_id") or payload.get("sessionId") or "unknown"
    marker = {
        "protocol_version": HOOK_PROTOCOL_VERSION,
        "session": opaque_id("session", str(session)),
        "required_at": _now(),
    }
    path = settlement_path()
    encoded = json.dumps(marker, sort_keys=True, separators=(",", ":")) + "\n"
    with _settlement_lock(create=True):
        descriptor, created = _open_append(path)
        with os.fdopen(descriptor, "a", encoding="utf-8") as stream:
            stream.write(encoded)
            stream.flush()
            os.fsync(stream.fileno())
        chmod_private(path)
        if created:
            _fsync_directory(path.parent)


def _read_settlement_bytes() -> bytes:
    descriptor = open_private_file_descriptor(settlement_path(), os.O_RDONLY)
    with os.fdopen(descriptor, "rb") as stream:
        return stream.read()


def _snapshot_from(data: bytes) -> SettlementSnapshot:
    final_newline = data.rfind(b"\n")
    prefix = data[: final_newline + 1] if final_newline >= 0 else b""
    return SettlementSnapshot(
        pending=sum(1 for line in prefix.splitlines() if line.strip()),
        prefix_bytes=len(prefix),
        prefix_sha256=hashlib.sha256(prefix).hexdigest(),
    )


def snapshot_settlements() -> SettlementSnapshot:
    """Snapshot complete markers for processing without claiming later appends."""
    with _settlement_lock(create=False) as available:
        if not available:
            return _snapshot_from(b"")
        try:
            data = _read_settlement_bytes()
        except FileNotFoundError:
            data = b""
        return _snapshot_from(data)


def pending_settlements() -> int:
    try:
        return snapshot_settlements().pending
    except OSError:
        return 0


def _rewrite_settlements(data: bytes) -> None:
    path = settlement_path()
    if data:
        descriptor, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
        try:
            with os.fdopen(descriptor, "wb") as stream:
                stream.write(data)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, path)
            chmod_private(path)
            _fsync_directory(path.parent)
        except BaseException:
            with contextlib.suppress(OSError):
                os.unlink(temporary)
            raise
        return
    try:
        path.unlink()
    except FileNotFoundError:
        return
    _fsync_directory(path.parent)


def clear_settlements(snapshot: SettlementSnapshot) -> bool:
    """Acknowledge only the exact marker prefix represented by ``snapshot``.

    A concurrent append is outside the snapshotted prefix and survives the
    atomic rewrite. A second reconciler holding a stale snapshot cannot clear
    markers that moved into the front of the queue after an earlier ack.
    """
    if snapshot.pending == 0 or snapshot.prefix_bytes == 0:
        return False
    with _settlement_lock(create=False) as available:
        if not available:
            return False
        try:
            current = _read_settlement_bytes()
        except FileNotFoundError:
            return False
        prefix = current[: snapshot.prefix_bytes]
        matches = len(prefix) == snapshot.prefix_bytes and (
            hashlib.sha256(prefix).hexdigest() == snapshot.prefix_sha256
        )
        if not matches:
            return False
        _rewrite_settlements(current[snapshot.prefix_bytes :])
        return True


def write_summary(*, ingested: int, reconciled: int) -> None:
    _atomic_json(
        summary_path(),
        {
            "protocol_version": HOOK_PROTOCOL_VERSION,
            "ingested": ingested,
            "estimates_reconciled": reconciled,
            "observed_at": _now(),
            "next_command": "forecost-runs-list",
        },
    )


def read_summary() -> dict[str, object] | None:
    try:
        value = json.loads(summary_path().read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return value if isinstance(value, dict) else None
