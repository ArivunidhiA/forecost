"""Bounded fsynced adapter outbox with idempotent replay and poison diagnostics."""

from __future__ import annotations

import contextlib
import hashlib
import json
import os
import tempfile
import threading
from collections.abc import Callable, Iterator
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path

from forecost.adapters.base import Money, UsageEvent, normalize_usage_event
from forecost.core.paths import chmod_private, ensure_private_dir, forecost_home

OUTBOX_SCHEMA_VERSION = 1


@contextlib.contextmanager
def _file_lock(path: Path) -> Iterator[None]:
    """Cross-process advisory lock on POSIX; process-local fallback elsewhere."""
    descriptor = os.open(path, os.O_CREAT | os.O_RDWR, 0o600)
    try:
        try:
            import fcntl

            fcntl.flock(descriptor, fcntl.LOCK_EX)
        except ImportError:  # pragma: no cover - Windows fallback
            pass
        yield
    finally:
        try:
            import fcntl

            fcntl.flock(descriptor, fcntl.LOCK_UN)
        except ImportError:  # pragma: no cover - Windows fallback
            pass
        os.close(descriptor)


def _event_dict(event: UsageEvent) -> dict[str, object]:
    normalized = normalize_usage_event(event)
    value = asdict(normalized)
    value["ts"] = normalized.ts.astimezone(timezone.utc).isoformat()
    return value


def _decode_event(value: object) -> UsageEvent:
    if not isinstance(value, dict):
        raise ValueError("outbox event must be an object")
    allowed = set(UsageEvent.__dataclass_fields__)
    if set(value) - allowed:
        raise ValueError("outbox event has unknown fields")
    decoded = dict(value)
    timestamp = decoded.get("ts")
    if not isinstance(timestamp, str):
        raise ValueError("outbox event needs a timestamp")
    decoded["ts"] = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
    money = decoded.get("reported_cost")
    if money is not None:
        if not isinstance(money, dict):
            raise ValueError("outbox money must be an object")
        decoded["reported_cost"] = Money(**money)
    return normalize_usage_event(UsageEvent(**decoded))


class DurableEventOutbox:
    """One-file queue optimized for gateway callback safety over throughput."""

    def __init__(
        self,
        path: Path,
        *,
        max_records: int = 10_000,
        max_bytes: int = 32 * 1024 * 1024,
        batch_size: int = 100,
    ) -> None:
        self.path = path
        self.lock_path = path.with_suffix(path.suffix + ".lock")
        self.poison_path = path.with_suffix(path.suffix + ".poison.jsonl")
        self.stats_path = path.with_suffix(path.suffix + ".stats.json")
        self.max_records = max_records
        self.max_bytes = max_bytes
        self.batch_size = batch_size
        self._thread: threading.Thread | None = None
        self._wake = threading.Event()
        self._stop = threading.Event()

    def _read_lines(self) -> list[str]:
        try:
            return [line for line in self.path.read_text(encoding="utf-8").splitlines() if line]
        except FileNotFoundError:
            return []

    def _write_lines(self, lines: list[str]) -> None:
        descriptor, temporary = tempfile.mkstemp(prefix=f".{self.path.name}.", dir=self.path.parent)
        try:
            with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
                if lines:
                    stream.write("\n".join(lines) + "\n")
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, self.path)
            chmod_private(self.path)
        except BaseException:
            with contextlib.suppress(OSError):
                os.unlink(temporary)
            raise

    def _stats(self) -> dict[str, int]:
        try:
            value = json.loads(self.stats_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            value = {}
        if not isinstance(value, dict):
            value = {}
        return {
            name: int(value.get(name, 0))
            for name in ("accepted", "delivered", "replayed", "poison", "dropped", "fail_open")
        }

    def _increment(self, name: str, amount: int = 1) -> None:
        stats = self._stats()
        stats[name] += amount
        descriptor, temporary = tempfile.mkstemp(
            prefix=f".{self.stats_path.name}.", dir=self.stats_path.parent
        )
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            json.dump(stats, stream, sort_keys=True, separators=(",", ":"))
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, self.stats_path)
        chmod_private(self.stats_path)

    def enqueue(self, event: UsageEvent) -> bool:
        with contextlib.suppress(ValueError):
            self.path.resolve().relative_to(forecost_home().resolve())
            ensure_private_dir(forecost_home())
        ensure_private_dir(self.path.parent)
        queued_at = datetime.now(timezone.utc).isoformat()
        line = json.dumps(
            {
                "schema_version": OUTBOX_SCHEMA_VERSION,
                "queued_at": queued_at,
                "attempt": 0,
                "event": _event_dict(event),
            },
            sort_keys=True,
            separators=(",", ":"),
        )
        with _file_lock(self.lock_path):
            lines = self._read_lines()
            size = self.path.stat().st_size if self.path.exists() else 0
            exceeds_bytes = size + len(line.encode("utf-8")) + 1 > self.max_bytes
            if len(lines) >= self.max_records or exceeds_bytes:
                self._increment("dropped")
                self._increment("fail_open")
                return False
            with self.path.open("a", encoding="utf-8") as stream:
                stream.write(line + "\n")
                stream.flush()
                os.fsync(stream.fileno())
            chmod_private(self.path)
            self._increment("accepted")
        self._wake.set()
        return True

    def _poison(self, line: str, error: Exception) -> None:
        diagnostic = {
            "schema_version": OUTBOX_SCHEMA_VERSION,
            "record_sha256": hashlib.sha256(line.encode("utf-8", errors="replace")).hexdigest(),
            "error_type": type(error).__name__,
            "observed_at": datetime.now(timezone.utc).isoformat(),
        }
        with self.poison_path.open("a", encoding="utf-8") as stream:
            stream.write(json.dumps(diagnostic, sort_keys=True, separators=(",", ":")) + "\n")
            stream.flush()
            os.fsync(stream.fileno())
        chmod_private(self.poison_path)
        self._increment("poison")

    def drain(self, emit: Callable[[UsageEvent], object]) -> int:
        delivered = 0
        if not self.path.exists():
            return delivered
        with _file_lock(self.lock_path):
            lines = self._read_lines()
            remaining: list[str] = []
            for index, line in enumerate(lines):
                if index >= self.batch_size:
                    remaining.extend(lines[index:])
                    break
                try:
                    record = json.loads(line)
                    valid_version = (
                        isinstance(record, dict)
                        and record.get("schema_version") == OUTBOX_SCHEMA_VERSION
                    )
                    if not valid_version:
                        raise ValueError("unsupported outbox record")
                    event = _decode_event(record.get("event"))
                except (TypeError, ValueError, json.JSONDecodeError) as error:
                    self._poison(line, error)
                    continue
                try:
                    emit(event)
                except Exception:
                    record["attempt"] = int(record.get("attempt", 0)) + 1
                    remaining.append(json.dumps(record, sort_keys=True, separators=(",", ":")))
                    remaining.extend(lines[index + 1 :])
                    self._increment("replayed")
                    self._increment("fail_open")
                    break
                delivered += 1
            self._write_lines(remaining)
            if delivered:
                self._increment("delivered", delivered)
        return delivered

    def status(self) -> dict[str, object]:
        if not self.path.exists():
            return {"depth": 0, "oldest_age_seconds": None, **self._stats()}
        with _file_lock(self.lock_path):
            lines = self._read_lines()
        oldest_age_seconds: int | None = None
        if lines:
            try:
                record = json.loads(lines[0])
                queued = datetime.fromisoformat(str(record["queued_at"]).replace("Z", "+00:00"))
                oldest_age_seconds = max(
                    0, int((datetime.now(timezone.utc) - queued).total_seconds())
                )
            except (KeyError, TypeError, ValueError, json.JSONDecodeError):
                oldest_age_seconds = None
        return {"depth": len(lines), "oldest_age_seconds": oldest_age_seconds, **self._stats()}

    def start(self, emit: Callable[[UsageEvent], object]) -> None:
        if self._thread is not None and self._thread.is_alive():
            self._wake.set()
            return

        def worker() -> None:
            while not self._stop.is_set():
                self._wake.wait(timeout=1.0)
                self._wake.clear()
                while not self._stop.is_set() and self.drain(emit):
                    pass

        self._thread = threading.Thread(target=worker, name="forecost-litellm-outbox", daemon=True)
        self._thread.start()
        self._wake.set()

    def stop(self, timeout: float = 2.0) -> None:
        self._stop.set()
        self._wake.set()
        if self._thread is not None:
            self._thread.join(timeout)
