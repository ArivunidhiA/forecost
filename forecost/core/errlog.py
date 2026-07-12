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

from forecost.core.paths import forecost_home

_MAX_LOG_BYTES = 1_000_000
_MAX_MESSAGE_CHARS = 400


def _log_path():
    # Computed per-write so $FORECOST_HOME is always honored (BASEMENT.md: one
    # source of truth for where forecost keeps its data).
    return forecost_home() / "error.log"


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


def _ensure_dir(log_path) -> None:
    log_path.parent.mkdir(parents=True, exist_ok=True)


def _rotate_if_large(log_path) -> None:
    try:
        if log_path.exists() and log_path.stat().st_size > _MAX_LOG_BYTES:
            lines = log_path.read_text(encoding="utf-8", errors="replace").splitlines()
            log_path.write_text("\n".join(lines[-2000:]) + "\n", encoding="utf-8")
    except OSError:
        pass


def log_error(component: str, message: str) -> None:
    """Append a redacted, bounded error line to $FORECOST_HOME/error.log.

    Never raises. Intended to be the only write path to error.log across the
    codebase so redaction and rotation are applied exactly once, everywhere.

    Args:
        component: Short tag identifying the subsystem (e.g. "hooks.gate").
        message: Human-readable error description; may include an exception
            repr, which will be redacted before it is written.
    """
    try:
        log_path = _log_path()
        _ensure_dir(log_path)
        _rotate_if_large(log_path)
        safe = redact(message)
        with open(log_path, "a", encoding="utf-8") as f:
            f.write(f"[{component}] {safe}\n")
    except OSError:
        pass


def log_exception(component: str, exc: BaseException) -> None:
    """Convenience wrapper: log a caught exception's repr, redacted."""
    log_error(component, repr(exc))
