"""Content-minimizing, fail-open diagnostics under ``FORECOST_HOME``.

Only reviewed component labels and finite error codes reach disk.  Arbitrary
messages, exception representations, paths, and provider payload fragments are
used only as input to an installation-keyed HMAC.  This keeps errors
correlatable on one installation without turning ``error.log`` into a second
content store.
"""

from __future__ import annotations

import os
import re
import stat
from contextlib import suppress
from typing import cast

from forecost.core.local_identity import keyed_fingerprint
from forecost.core.paths import ensure_private_dir, forecost_home, validate_private_file

_MAX_LOG_BYTES = 1_000_000
_MAX_FINGERPRINT_INPUT_BYTES = 8_192
_LOG_LINE = re.compile(
    r"^\[(?P<component>[a-z0-9_.-]+)\] code=(?P<code>[A-Z0-9_]+) "
    r"fingerprint=hmac-sha256:[0-9a-f]{64}\n$"
)

# This vocabulary is intentionally finite.  Additions require a code review
# because both labels are durable disclosure surfaces.
ERROR_CODES = frozenset(
    {
        "CLAUDE_CAUSAL_RECORD_INVALID",
        "CLAUDE_RECORD_INVALID",
        "CLAUDE_TRANSCRIPT_READ_FAILED",
        "HOOK_HANDLER_FAILED",
        "HOOK_POLICY_IGNORED",
        "HOOK_SHADOW_GUARD_FAILED",
        "INTERCEPTOR_FAILED",
        "INTERNAL_ERROR",
        "LEDGER_DURABILITY_FAILED",
        "LEDGER_ENQUEUE_FAILED",
        "LEDGER_FLUSH_RETRY",
        "LEDGER_QUEUE_FULL",
        "LEDGER_SPILL_STARTED",
        "LEDGER_STARTUP_FAILED",
        "LEDGER_WRITER_UNAVAILABLE",
        "LEGACY_DB_WRITE_FAILED",
        "LITELLM_GATE_FAILED_OPEN",
        "LITELLM_GATE_FAILED_CLOSED",
        "LITELLM_INGEST_FAILED",
        "LITELLM_OUTBOX_FULL",
        "POLICY_EVALUATION_FAILED",
        "PRICING_MODEL_UNKNOWN",
        "RECOVERY_ARCHIVE_FAILED",
        "RECOVERY_FLUSH_FAILED",
        "RECOVERY_RECORD_REJECTED",
        "RECOVERY_RETAIN_FAILED",
        "RECOVERY_QUEUE_UNLINK_FAILED",
        "RECOVERY_QUEUE_UNLINK_SYNC_FAILED",
        "SINK_EMIT_FAILED",
    }
)

_COMPONENTS = frozenset(
    {
        "adapters.claude_code",
        "adapters.claude_code.causal",
        "adapters.litellm.pre_call",
        "adapters.litellm.success",
        "commands.recover",
        "core.unknown",
        "hooks.guard",
        "hooks.lifecycle",
        "hooks.policy",
        "hooks.pre-tool",
        "hooks.prompt-submit",
        "hooks.session-end",
        "hooks.session-start",
        "hooks.stop",
        "interceptor",
        "ledger.writer",
        "legacy-db",
        "policy.engine",
        "pricing",
        "test",
    }
)


def _log_path():
    return forecost_home() / "error.log"


# Kept as a public in-memory helper for compatibility.  The durable logger no
# longer persists even redacted free text.
_REDACT_PATTERNS = [
    re.compile(r"sk-(?:proj-|svcacct-|ant-[A-Za-z0-9-]*-)?[A-Za-z0-9_-]{16,}"),
    re.compile(r"(?:gh[pousr]_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,})"),
    re.compile(r"xox[bpars]-[A-Za-z0-9-]{10,}"),
    re.compile(r"AKIA[0-9A-Z]{16}"),
    re.compile(r"AIza[0-9A-Za-z_-]{30,}"),
    re.compile(r"hf_[A-Za-z0-9]{20,}"),
    re.compile(r"\bBearer\s+[A-Za-z0-9._~+/=-]{16,}", re.IGNORECASE),
    re.compile(r"eyJ[A-Za-z0-9_-]{20,}(?:\.[A-Za-z0-9_-]{10,}){1,2}"),
    re.compile(r"[A-Za-z0-9+/]{40,}={0,2}"),
]


def redact(text: str) -> str:
    """Redact common secret shapes for callers that need an in-memory string."""
    out = text
    for pattern in _REDACT_PATTERNS:
        out = pattern.sub("[REDACTED]", out)
    return out[:400] + ("...[truncated]" if len(out) > 400 else "")


def _bounded_text(value: str, maximum: int = 2_048) -> str:
    if len(value) <= maximum:
        return value
    half = maximum // 2
    return f"{value[:half]}<length:{len(value)}>{value[-half:]}"


def _bounded_bytes(value: bytes) -> str:
    bounded = value if len(value) <= 2_048 else value[:1_024] + value[-1_024:]
    return f"bytes:length={len(value)}:{bounded.hex()}"


def _bounded_int(value: int) -> str:
    if value.bit_length() > 4_096:
        return f"int:bits={value.bit_length()}:low64={value & ((1 << 64) - 1)}"
    return f"int:{value}"


def _bounded_scalar(value: object, value_type: type[object], type_name: str) -> str | None:
    if value is None or value_type is bool:
        return f"{type_name}:{value}"
    if value_type is str:
        return f"str:{_bounded_text(cast(str, value))}"
    if value_type is bytes:
        return _bounded_bytes(cast(bytes, value))
    if value_type is int:
        return _bounded_int(cast(int, value))
    if value_type is float:
        return f"float:{cast(float, value).hex()}"
    return None


def _bounded_items(
    type_name: str,
    sequence: tuple[object, ...] | list[object],
    depth: int,
) -> str:
    parts = [_bounded_part(item, depth + 1) for item in sequence[:8]]
    return f"{type_name}:items={len(sequence)}:" + "|".join(parts)


def _bounded_part(value: object, depth: int = 0) -> str:
    """Avoid arbitrary ``repr`` methods and bound large exception arguments."""
    value_type = type(value)
    type_name = f"{value_type.__module__}.{value_type.__qualname__}"
    scalar = _bounded_scalar(value, value_type, type_name)
    if scalar is not None:
        return scalar
    if depth >= 2:
        return type_name
    if isinstance(value, BaseException):
        parts = [_bounded_part(arg, depth + 1) for arg in value.args[:8]]
        return f"exception:{type_name}:args={len(value.args)}:" + "|".join(parts)
    if value_type in (tuple, list):
        return _bounded_items(type_name, cast(tuple[object, ...] | list[object], value), depth)
    # Custom repr/str methods may leak data, allocate without bound, or raise.
    # Their reviewed type identity still makes the diagnostic correlatable.
    return type_name


def _bounded_material(value: object) -> str:
    """Represent arbitrary input only long enough to HMAC it; never persist it."""
    raw = _bounded_part(value)
    encoded = raw.encode("utf-8", errors="replace")[:_MAX_FINGERPRINT_INPUT_BYTES]
    return encoded.decode("utf-8", errors="replace")


def _safe_labels(component: str, code: str) -> tuple[str, str, bool]:
    labels_are_known = component in _COMPONENTS and code in ERROR_CODES
    if labels_are_known:
        return component, code, True
    return (component if component in _COMPONENTS else "core.unknown"), "INTERNAL_ERROR", False


def _canonical_log(content: bytes) -> bool:
    try:
        decoded = content.decode("ascii")
    except UnicodeDecodeError:
        return False
    for line in decoded.splitlines(keepends=True):
        match = _LOG_LINE.fullmatch(line)
        if (
            match is None
            or match.group("component") not in _COMPONENTS
            or match.group("code") not in ERROR_CODES
        ):
            return False
    return not decoded or decoded.endswith("\n")


def _append_line(line: str) -> None:
    log_path = _log_path()
    ensure_private_dir(log_path.parent)
    validate_private_file(log_path)
    flags = os.O_RDWR | os.O_APPEND | os.O_CREAT | getattr(os, "O_NOFOLLOW", 0)
    descriptor = os.open(log_path, flags, 0o600)
    try:
        metadata = os.fstat(descriptor)
        if not stat.S_ISREG(metadata.st_mode):
            return
        with suppress(OSError):
            os.fchmod(descriptor, 0o600)
        existing = b""
        if metadata.st_size <= _MAX_LOG_BYTES:
            os.lseek(descriptor, 0, os.SEEK_SET)
            existing = os.read(descriptor, metadata.st_size + 1)
        if metadata.st_size > _MAX_LOG_BYTES or not _canonical_log(existing):
            # Remove any legacy free-text log on the first post-upgrade write;
            # preserving it would defeat the new finite-code boundary.
            os.ftruncate(descriptor, 0)
        encoded = line.encode("ascii")
        written = 0
        while written < len(encoded):
            count = os.write(descriptor, encoded[written:])
            if count <= 0:  # pragma: no cover - OS write contract
                raise OSError("error log write made no progress")
            written += count
    finally:
        os.close(descriptor)


def log_error(
    component: str,
    code: str,
    *,
    fingerprint_source: object | None = None,
) -> None:
    """Append one finite diagnostic code plus a keyed, bounded fingerprint.

    ``code`` remains backward-compatible with legacy free-form callers: an
    unknown value is never written and instead becomes ``INTERNAL_ERROR`` with
    the original value folded into the HMAC input.  The function never raises.
    """
    try:
        safe_component, safe_code, known = _safe_labels(component, code)
        material: object = fingerprint_source
        if not known:
            material = (component, code, fingerprint_source)
        fingerprint = keyed_fingerprint(
            "forecost-error-v1",
            safe_component,
            safe_code,
            _bounded_material(material),
        )
        _append_line(f"[{safe_component}] code={safe_code} fingerprint=hmac-sha256:{fingerprint}\n")
    # Diagnostics are deliberately fail-open and must never break the host.
    except Exception:  # noqa: S110  # nosec B110
        pass


def log_exception(
    component: str,
    exc: BaseException,
    code: str = "INTERNAL_ERROR",
) -> None:
    """Log an exception without persisting its type, message, or arguments."""
    log_error(component, code, fingerprint_source=exc)
