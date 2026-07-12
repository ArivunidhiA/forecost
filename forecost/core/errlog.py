"""Canonical error logger: never crash the host, log to ~/.forecost/error.log.

Consolidates the pattern previously duplicated in db.py, interceptor.py, and
pricing.py, and adds secret redaction before anything is written to disk —
closing a real leak: exception reprs (``{e!r}``) can embed API-response
fragments, bearer tokens, or other secrets from the calling application.

Iron Rule #6 (never `except Exception: pass` — always log) and Iron Rule #1
(the interceptor/hooks must never break the host) both route through here.
"""

from __future__ import annotations

import re
from pathlib import Path

_LOG_PATH = Path.home() / ".forecost" / "error.log"
_MAX_LOG_BYTES = 1_000_000
_MAX_MESSAGE_CHARS = 400

_REDACT_PATTERNS = [
    re.compile(r"sk-[A-Za-z0-9]{20,}"),
    re.compile(r"ghp_[A-Za-z0-9]{36}"),
    re.compile(r"xox[bpars]-[A-Za-z0-9-]{10,}"),
    re.compile(r"AKIA[0-9A-Z]{16}"),
    re.compile(r"eyJ[A-Za-z0-9_-]{20,}(?:\.[A-Za-z0-9_-]{10,}){1,2}"),  # JWT-shaped
    re.compile(r"[A-Za-z0-9+/]{40,}={0,2}"),  # generic long base64 runs
]


def redact(text: str) -> str:
    """Strip common secret shapes from a string before it is logged or persisted.

    Args:
        text: Raw text that may contain API keys, tokens, or other secrets.

    Returns:
        str: The text with matched secret-shaped substrings replaced by
            ``[REDACTED]``, truncated to a bounded length.
    """
    out = text
    for pattern in _REDACT_PATTERNS:
        out = pattern.sub("[REDACTED]", out)
    if len(out) > _MAX_MESSAGE_CHARS:
        out = out[:_MAX_MESSAGE_CHARS] + "...[truncated]"
    return out


def _ensure_dir() -> None:
    _LOG_PATH.parent.mkdir(parents=True, exist_ok=True)


def _rotate_if_large() -> None:
    try:
        if _LOG_PATH.exists() and _LOG_PATH.stat().st_size > _MAX_LOG_BYTES:
            lines = _LOG_PATH.read_text(encoding="utf-8", errors="replace").splitlines()
            _LOG_PATH.write_text("\n".join(lines[-2000:]) + "\n", encoding="utf-8")
    except OSError:
        pass


def log_error(component: str, message: str) -> None:
    """Append a redacted, bounded error line to ~/.forecost/error.log.

    Never raises. Intended to be the only write path to error.log across the
    codebase so redaction and rotation are applied exactly once, everywhere.

    Args:
        component: Short tag identifying the subsystem (e.g. "hooks.gate").
        message: Human-readable error description; may include an exception
            repr, which will be redacted before it is written.
    """
    try:
        _ensure_dir()
        _rotate_if_large()
        safe = redact(message)
        with open(_LOG_PATH, "a", encoding="utf-8") as f:
            f.write(f"[{component}] {safe}\n")
    except OSError:
        pass


def log_exception(component: str, exc: BaseException) -> None:
    """Convenience wrapper: log a caught exception's repr, redacted."""
    log_error(component, repr(exc))
