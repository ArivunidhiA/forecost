"""Tiny durable Claude hook state, separate from transcript reconciliation."""

from __future__ import annotations

import contextlib
import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from forecost.core.paths import chmod_private, ensure_private_dir, forecost_home
from forecost.ledger.contracts import opaque_id

HOOK_PROTOCOL_VERSION = 1


def _state_dir() -> Path:
    return forecost_home() / "hooks"


def _ensure_state_dir() -> Path:
    home = ensure_private_dir(forecost_home())
    return ensure_private_dir(home / "hooks")


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
    except BaseException:
        with contextlib.suppress(OSError):
            os.unlink(temporary)
        raise


def record_heartbeat(event: str, *, state: str = "healthy", detail: str | None = None) -> None:
    value: dict[str, object] = {
        "protocol_version": HOOK_PROTOCOL_VERSION,
        "event": event,
        "state": state,
        "observed_at": _now(),
        "readiness": "OBSERVED",
    }
    if detail is not None:
        value["detail"] = detail
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
    _ensure_state_dir()
    path = settlement_path()
    encoded = json.dumps(marker, sort_keys=True, separators=(",", ":")) + "\n"
    with path.open("a", encoding="utf-8") as stream:
        stream.write(encoded)
        stream.flush()
        os.fsync(stream.fileno())
    chmod_private(path)


def pending_settlements() -> int:
    try:
        with settlement_path().open(encoding="utf-8") as stream:
            return sum(1 for line in stream if line.strip())
    except OSError:
        return 0


def clear_settlements() -> None:
    path = settlement_path()
    with contextlib.suppress(FileNotFoundError):
        path.unlink()


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
